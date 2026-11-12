"""
Aplicación principal FastAPI.
"""

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as FastResponse
from fastapi.staticfiles import StaticFiles
from scalar_fastapi import AgentScalarConfig, get_scalar_api_reference

# Se importan por lo que hacen al cargarse: models_registry trae todos los modelos (las relaciones se resuelven por
# nombre y necesitan todas las clases cargadas) y cada `tareas` registra las tareas programadas de su módulo (las
# corre el motor de tareas, F19)
import backend.models_registry  # noqa: F401
import backend.modules.administracion.evaluacion_proveedores_tareas  # noqa: F401
import backend.modules.notificaciones.tareas  # noqa: F401
import backend.modules.sincronizacion.tareas  # noqa: F401
from backend.core import errores
from backend.core.config import settings
from backend.core.descargas import FirmaDeDescarga
from backend.core.files import init_directories
from backend.core.limites import Limitador
from backend.core.logging_config import configurar_logging
from backend.core.pedido import IdDePedido
from backend.core.storage import cloud_storage
from backend.dependencies import get_current_user, require_modulo, require_submodulo
from backend.modules.administracion.clientes_routers import router as clientes_router
from backend.modules.administracion.evaluacion_proveedores_routers import router as evaluacion_proveedores_router
from backend.modules.administracion.export_recibos_routers import router as export_recibos_router
from backend.modules.administracion.proveedores_routers import router as proveedores_router
from backend.modules.auditoria.routers import public_router as auditoria_public_router, router as auditoria_router
from backend.modules.auth.google_routers import router as google_router
from backend.modules.auth.routers import router as auth_router
from backend.modules.empresa.routers import router as empresa_router
from backend.modules.hrbp.routers import router as hrbp_router
from backend.modules.innovacion.licencias_routers import router as licencias_router
from backend.modules.innovacion.routers import public_router as innovacion_public_router, router as innovacion_router
from backend.modules.llm.routers import router as llm_router
from backend.modules.nomina.routers import public_router as nomina_public_router, router as nomina_router
from backend.modules.notificaciones.routers import router as notificaciones_router
from backend.modules.notificaciones_internas.routers import router as notificaciones_internas_router
from backend.modules.oidc.routers import router as oidc_router
from backend.modules.operaciones.routers import router as operaciones_router
from backend.modules.parametros.routers import router as parametros_router
from backend.modules.permisos.menu_routers import router as menus_router
from backend.modules.permisos.routers import public_router as permisos_public_router, router as permisos_router
from backend.modules.recibos.routers import (
    nomina_router as recibos_nomina_router,
    public_router as recibos_public_router,
    router as recibos_router,
)
from backend.modules.recruiting.routers import router as recruiting_router
from backend.modules.sincronizacion.routers import router as sincronizacion_router
from backend.modules.soporte.routers import router as soporte_router
from backend.modules.starmiles.routers import public_router as starmiles_public_router, router as starmiles_router
from backend.modules.tareas.routers import router as tareas_router
from backend.modules.usuarios.routers import public_router as usuarios_public_router, router as usuarios_router

# Se configura al importar el módulo (uvicorn importa `main:app` al arrancar),
# antes de que cualquier logger de la aplicación emita su primera línea.
configurar_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eventos de ciclo de vida de la aplicación."""
    if settings.environment == "testing":
        yield
        return

    from backend.core.email import init_email_service
    from backend.core.webex import init_webex_service

    print("🚀 Iniciando aplicación FastAPI...")
    print(f"📍 Modo: {'desarrollo' if settings.debug else 'producción'}")

    # El esquema no se toca acá: lo migra el paso de release (`alembic upgrade head`, el servicio migraciones del
    # compose) antes de que arranque el backend (F04, docs/Migraciones.md).

    # Inicializar directorios de archivos
    init_directories()
    from backend.core.llm import init_directories as init_llm_directories

    init_llm_directories()
    print("📁 Directorios de archivos inicializados")

    # Inicializar servicio de email
    init_email_service()
    if settings.sendgrid_api_key:
        print("📧 Servicio de email configurado con SendGrid")
    else:
        print("⚠️ SENDGRID_API_KEY no configurada - emails deshabilitados")

    # Inicializar servicio de Webex
    init_webex_service()
    if settings.webex_bot_token:
        print("💬 Servicio de Webex configurado")
    else:
        print("⚠️ WEBEX_BOT_TOKEN no configurada - Webex deshabilitado")

    # Crear usuario admin por defecto si no hay usuarios
    # Solo el primer worker que obtenga el lock corre los seeds; los demás
    # los saltean para evitar duplicar logs y trabajo (los seeds son idempotentes
    # pero correr 5 veces lo mismo ensucia los logs).
    if settings.environment == "development":
        _seeds_de_desarrollo()

    # Motor de tareas programadas (F19): un solo programador para cumpleaños, Actualización de Datos y avisos de
    # proveedores, con cola de envíos y alertas de fallo por Webex. Corre en el servicio scheduler del compose
    # (CRON_ENABLED=true, una réplica); el backend que atiende la API lo tiene apagado, así reiniciarlo o escalarlo no
    # arranca tareas (F06-P01, D-10). Antes estaba detrás del corte de desarrollo y fuera de él no corría (F19-P10).
    if settings.cron_enabled:
        _arrancar_programador()
    else:
        print("⏰ Programador apagado en este proceso (CRON_ENABLED=false): corre en el servicio scheduler")

    yield

    print("🛑 Cerrando aplicación...")


LOCK_SEEDS = 4242421337 + 1  # advisory lock de Postgres de los seeds, arbitrario pero estable


def _seeds_de_desarrollo() -> None:
    """Seeds del arranque, solo en desarrollo: admin por defecto, datos de ejemplo, parámetros, procesos de
    sincronización y datos maestros de soporte. Solo el primer worker que obtiene el candado los corre; los demás los
    saltean para no duplicar logs y trabajo (los seeds son idempotentes, pero correr 5 veces lo mismo ensucia los
    logs)."""
    from sqlalchemy import text

    from backend.database import SessionLocal
    from backend.modules.usuarios.services import UsuarioService

    db = SessionLocal()
    is_seed_leader = False
    try:
        result = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_SEEDS}).scalar()
        db.commit()
        is_seed_leader = bool(result)

        if not is_seed_leader:
            print("⏭️  Worker secundario: omitiendo seeds (los corre el worker líder)")
        else:
            admin = UsuarioService.crear_usuario_admin_default(db)
            if admin:
                origen = (
                    "la de SEED_ADMIN_PASSWORD"
                    if settings.seed_admin_password
                    else "aleatoria, sin mostrar: definí SEED_ADMIN_PASSWORD en el .env"
                )
                print(f"👤 Usuario admin creado: {admin.email} (contraseña {origen})")
            else:
                print("👤 Usuarios existentes, no se creó admin por defecto")

            # Mostrar módulos registrados
            from backend.core.registry import obtener_modulos

            modulos = obtener_modulos()
            print(f"📋 Registry: {len(modulos)} módulos registrados: {', '.join(m['codigo'] for m in modulos)}")

            # Seed de datos de ejemplo (solo desarrollo)
            from backend.core.seed_data import ejecutar_seed

            if ejecutar_seed(db):
                print("🌱 Datos de ejemplo insertados")

            # Seed de parámetros del sistema
            from backend.modules.parametros.seed_data import ejecutar_seed_parametros

            if ejecutar_seed_parametros(db):
                print("⚙️ Parámetros del sistema creados")

            # Parámetros de las tareas programadas y del room de alertas (migra los de los crons viejos)
            from backend.modules.tareas.parametros import asegurar_parametros

            if asegurar_parametros(db):
                print("⚙️ Parámetros de tareas programadas creados")

            # Crear procesos de sincronización por defecto
            from backend.modules.sincronizacion.services import SincronizacionService

            if SincronizacionService.crear_procesos_default(db):
                print("🔄 Procesos de sincronización creados")

            # Seed de soporte IT (v28.0)
            from backend.modules.soporte.seed_data import ejecutar_seed_marcas_todas_empresas, ejecutar_seed_soporte

            if ejecutar_seed_soporte(db, "admin@admin.com"):
                print("🌱 Datos maestros de Soporte IT actualizados")

            # Seed de marcas de activos
            try:
                resultados = ejecutar_seed_marcas_todas_empresas(db, "sistema@dicsys.com")
                total_creadas = sum(r["stats"]["creadas"] for r in resultados.values())
                if total_creadas > 0:
                    print(f"🏷️  Marcas de activos: {total_creadas} marcas creadas")
            except Exception as e:
                print(f"⚠️  Error al cargar marcas: {e}")

            # Proceso 'Crear Usuarios Faltantes' agregado
            if SincronizacionService.agregar_proceso_usuarios_faltantes(db):
                print("🔄 Proceso 'Crear Usuarios Faltantes' agregado")

            # Proceso 'Carga Masiva StarMiles' agregado
            if SincronizacionService.agregar_proceso_starmiles(db):
                print("🔄 Proceso 'Carga Masiva StarMiles' agregado")

            # Proceso 'Carga Charlas Innovación' agregado
            if SincronizacionService.agregar_proceso_charlas_innovacion(db):
                print("🔄 Proceso 'Carga Charlas Innovación' agregado")

            # Proceso 'Carga Administración Recibos Export' agregado
            if SincronizacionService.agregar_proceso_administracion_recibos(db):
                print("🔄 Proceso 'Carga Administración Recibos Export' agregado")

            # Proceso 'Sincronización de Membresías Webex' agregado
            if SincronizacionService.agregar_proceso_sync_webex(db):
                print("🔄 Proceso 'Sincronización de Membresías Webex' agregado")
    finally:
        if is_seed_leader:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_SEEDS})
                db.commit()
            except Exception:
                pass
        db.close()


def _arrancar_programador() -> None:
    """Asegura los parámetros de las tareas (tarea_*_activa y _horario, el room de alertas; sin ellos no corre ninguna
    tarea programada) y arranca el programador. Los parámetros los crea un solo proceso, con el candado de los seeds."""
    from sqlalchemy import text

    from backend.database import SessionLocal
    from backend.modules.tareas.parametros import asegurar_parametros
    from backend.modules.tareas.programador import iniciar_programador

    db = SessionLocal()
    try:
        if db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_SEEDS}).scalar():
            try:
                if asegurar_parametros(db):
                    print("⚙️ Parámetros de tareas programadas creados")
            finally:
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_SEEDS})
                db.commit()
    finally:
        db.close()
    iniciar_programador()
    print("⏰ Programador de tareas iniciado (CRON_ENABLED=true)")


# Crear aplicacion FastAPI
application_router = APIRouter()

# === Exception handler global para errores de validación de Pydantic ===
FIELD_LABELS = {
    "codigo": "Código",
    "cuil": "CUIL",
    "apellido": "Apellido",
    "nombre": "Nombre",
    "fecha_nacimiento": "Fecha de nacimiento",
    "dni": "DNI",
    "genero": "Género",
    "nacionalidad": "Nacionalidad",
    "estado_civil": "Estado civil",
    "nivel_estudio": "Nivel de estudio",
    "carrera_id": "Carrera",
    "telefono_personal": "Teléfono personal",
    "email_personal": "Email personal",
    "email_corporativo": "Email corporativo",
    "email_secundario": "Email secundario",
    "fecha_alta": "Fecha de alta",
    "fecha_baja": "Fecha de baja",
    "motivo_baja": "Motivo de baja",
    "departamento_id": "Departamento",
    "perfil_id": "Perfil",
    "hrbp_id": "HRBP",
    "seniority": "Seniority",
    "pais": "País",
    "provincia": "Provincia",
    "localidad": "Localidad",
    "codigo_postal": "Código postal",
    "barrio": "Barrio",
    "calle": "Calle",
    "numero": "Número",
    "piso": "Piso",
    "departamento": "Departamento (dirección)",
    "contacto_emergencia": "Contacto de emergencia",
    "numero_emergencia": "Número de emergencia",
    "parentesco": "Parentesco",
    "manager_id": "Manager",
    "descripcion": "Descripción",
    "email": "Email",
    "password": "Contraseña",
    "telefono": "Teléfono",
    "rol": "Rol",
    "herramienta": "Herramienta",
    "costo_mensual": "Costo mensual",
    "moneda": "Moneda",
    "stock_actual": "Stock actual",
    "stock_minimo": "Stock mínimo",
    "cantidad": "Cantidad",
    "star_miles": "Star Miles",
    "star_miles_costo": "Costo en Star Miles",
    "titulo": "Título",
    "contenido": "Contenido",
    "tipo": "Tipo",
    "foto": "Foto",
    "tipo_certificacion": "Tipo de Certificación",
    "estado": "Estado",
    "repo_presentacion": "Repositorio Git Presentación",
    "repo_demo": "Repositorio Git Demo/Código",
    "tematica": "Temática",
    "tecnologias": "Tecnologías",
    "fecha_presentacion": "Fecha de Presentación",
    "fecha_aprobacion": "Fecha de Aprobación",
    "evento_nombre": "Nombre del Evento",
    "evento_fecha": "Fecha del Evento",
    "usuario_ids": "Usuarios Asistentes",
    # Clientes
    "cuit": "CUIT",
    "razon_social": "Razón Social",
    "nombre_fantasia": "Nombre de Fantasía",
    "responsabilidad_afip": "Responsabilidad AFIP",
    "sitio_web": "Sitio Web",
    "observaciones": "Observaciones",
    "categoria_ids": "Categorías",
    # Proveedores y su evaluación
    "telefono_whatsapp": "WhatsApp",
    "pagina_web": "Página web",
    "nro_ingresos_brutos": "Nro. Ingresos Brutos",
    "acuerdo_servicio": "Acuerdo de servicio",
    "nombre_oficina": "Nombre de la oficina",
    "fecha_apertura": "Apertura",
    "fecha_cierre": "Cierre",
    "periodo": "Período",
    "webex_room_id": "ID del room de Webex",
    "email_cc": "CC",
    "recordar_cada_dias": "Recordar cada (días)",
    # Parámetros
    "categoria": "Categoría",
    "subcategoria": "Subcategoría",
    "key": "Key",
    "valor": "Valor",
    "valor_default": "Valor por defecto",
    # Auditoría
    "modulo": "Módulo",
    "ruta": "Ruta",
    "metodo": "Método",
    "email_usuario": "Email de usuario",
    "fecha_hora": "Fecha y hora",
}

ERROR_MESSAGES_ES = {
    "less_than_equal": "debe ser menor o igual a {le}",
    "greater_than_equal": "debe ser mayor o igual a {ge}",
    "less_than": "debe ser menor a {lt}",
    "greater_than": "debe ser mayor a {gt}",
    "string_too_short": "debe tener al menos {min_length} caracteres",
    "string_too_long": "no puede tener más de {max_length} caracteres",
    "missing": "es obligatorio",
    "value_error": "tiene un valor inválido",
    "int_parsing": "debe ser un número entero válido",
    "int_type": "debe ser un número entero",
    "float_parsing": "debe ser un número válido",
    "float_type": "debe ser un número",
    "string_type": "debe ser texto",
    "date_from_datetime_parsing": "formato de fecha inválido (usar AAAA-MM-DD)",
    "date_parsing": "formato de fecha inválido (usar AAAA-MM-DD)",
    "enum": "valor no permitido",
    "email_parsing": "formato de email inválido",
    "url_parsing": "formato de URL inválido",
    "string_pattern_mismatch": "formato inválido",
    "bool_type": "debe ser verdadero o falso",
    "bool_parsing": "debe ser verdadero o falso",
    "json_invalid": "formato JSON inválido",
    "uuid_parsing": "no es un identificador válido",
    "uuid_type": "no es un identificador válido",
}


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Intercepta errores de validación de Pydantic y los traduce al español. Forma: core/errores.ErrorDeValidacion,
    `detail` con todo en un texto y `errores` uno por campo (F07-P08)."""
    errores_traducidos = []
    por_campo = []
    for err in exc.errors():
        loc = err.get("loc", [])
        field = loc[-1] if loc else "campo"
        label = FIELD_LABELS.get(field, str(field).replace("_", " ").capitalize())
        campo = ".".join(str(parte) for parte in loc[1:])

        err_type = err.get("type", "")
        ctx = err.get("ctx", {})

        # ValueError de un validador propio: su mensaje ya está en español y dice qué corregir.
        # Sin etiqueta si el validador es de todo el modelo (loc = ('body',)) o si el mensaje
        # ya nombra el campo («CUIT inválido: …»).
        propio = ctx.get("error") if err_type == "value_error" else None
        if isinstance(propio, ValueError) and str(propio):
            mensaje = str(propio)
            sin_etiqueta = tuple(loc) == ("body",) or mensaje.lower().startswith(label.lower())
            errores_traducidos.append(mensaje if sin_etiqueta else f"{label}: {mensaje}")
            por_campo.append({"campo": campo, "mensaje": mensaje})
            continue

        if err_type in ERROR_MESSAGES_ES:
            try:
                msg = ERROR_MESSAGES_ES[err_type].format(**ctx)
            except KeyError, IndexError:
                msg = err.get("msg", "error de validación")
        else:
            msg = err.get("msg", "error de validación")

        errores_traducidos.append(f"{label}: {msg}")
        por_campo.append({"campo": campo, "mensaje": msg})

    return JSONResponse(
        status_code=422,
        content={
            "detail": "; ".join(errores_traducidos)
            if errores_traducidos
            else "Error de validación en los datos enviados",
            "errores": por_campo,
        },
    )


# Configurar CORS

# ─── Endpoint proxy para archivos en cloud storage ─────────────────────────


@application_router.get("/storage/thumbnail/{path:path}", tags=["Storage"])
async def serve_storage_thumbnail(path: str):
    """Genera y sirve un thumbnail del archivo. Si es PDF, renderiza la primera página como PNG."""
    import mimetypes

    try:
        content = cloud_storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"

    if content_type == "application/pdf":
        try:
            import pymupdf

            doc = pymupdf.open(stream=content, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
            png_bytes = pix.tobytes("png")
            doc.close()
            return FastResponse(content=png_bytes, media_type="image/png")
        except Exception:
            return FastResponse(content=content, media_type=content_type)
    else:
        return FastResponse(content=content, media_type=content_type)


@application_router.get("/storage/preview-pdf/{path:path}", tags=["Storage"])
async def serve_storage_preview_pdf(path: str):
    """Sirve un CV Word (.doc/.docx) convertido a PDF para la vista previa del modal de comparación (Recruiting)."""
    import asyncio
    import os

    from backend.core.cv_preview import ConversionNoDisponibleError, convertir_word_a_pdf, ruta_cv_convertible

    if not ruta_cv_convertible(path):
        raise HTTPException(status_code=400, detail="Archivo no admitido para vista previa")
    try:
        content = cloud_storage.download(path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    try:
        pdf = await asyncio.to_thread(convertir_word_a_pdf, content, os.path.splitext(path)[1].lower())
    except ConversionNoDisponibleError:
        raise HTTPException(status_code=503, detail="Vista previa no disponible")
    return FastResponse(content=pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@application_router.post("/storage/preview-pdf", tags=["Storage"], dependencies=[Depends(get_current_user)])
async def convertir_cv_word_a_pdf_subido(archivo: UploadFile = File(...)):
    """Convierte a PDF un CV Word subido (todavía no guardado) para la vista previa del modal de comparación."""
    import asyncio
    import os

    from backend.core.cv_preview import EXTENSIONES_WORD, ConversionNoDisponibleError, convertir_word_a_pdf

    extension = os.path.splitext((archivo.filename or "").lower())[1]
    if extension not in EXTENSIONES_WORD:
        raise HTTPException(status_code=400, detail="Solo se admiten archivos .doc y .docx")
    content = await archivo.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo permitido de 5 MB.")
    try:
        pdf = await asyncio.to_thread(convertir_word_a_pdf, content, extension)
    except ConversionNoDisponibleError:
        raise HTTPException(status_code=503, detail="Vista previa no disponible")
    return FastResponse(content=pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@application_router.get("/storage/{path:path}", tags=["Storage"])
async def serve_storage_file(path: str):
    """Sirve archivos desde cloud_storage (GCS o local fallback)."""
    import mimetypes

    try:
        content = cloud_storage.download(path)
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return FastResponse(content=content, media_type=content_type)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")


# Montar archivos estáticos (local storage: avatares, logos, imágenes CMS)
# ─── Registrar routers ─────────────────────────────────────────────

# Auth: rutas públicas (login, forgot-password, reset-password)
application_router.include_router(auth_router, prefix=settings.api_v1_prefix)
# Ingreso con Google (F22): las llama el frontend en el login
application_router.include_router(google_router, prefix=settings.api_v1_prefix)

# Usuarios públicos: magic link (sin autenticación)
application_router.include_router(usuarios_public_router, prefix=settings.api_v1_prefix)

# Permisos público ANTES del protegido (para que /permisos/usuario/{id} matchee primero)
application_router.include_router(
    permisos_public_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)]
)

# Usuarios y Permisos: rutas protegidas por módulo configuracion
application_router.include_router(
    usuarios_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("configuracion"))]
)
application_router.include_router(
    permisos_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("configuracion"))]
)

# Menús y datos públicos (solo JWT)
application_router.include_router(menus_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)])
application_router.include_router(
    nomina_public_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)]
)

# Star Miles público (empleado, solo JWT)
application_router.include_router(
    starmiles_public_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)]
)

# Módulos protegidos por permiso de grupo
application_router.include_router(
    nomina_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("nomina"))]
)
application_router.include_router(
    starmiles_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("starmiles"))]
)
application_router.include_router(
    sincronizacion_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("configuracion"))]
)
application_router.include_router(
    hrbp_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("hrbp"))]
)
application_router.include_router(
    clientes_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("admin_contable"))]
)
application_router.include_router(
    export_recibos_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("admin_contable"))]
)
# Proveedores (registro) y su evaluación por campañas (F18): cada endpoint exige su ítem
application_router.include_router(
    proveedores_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("admin_contable"))]
)
application_router.include_router(
    evaluacion_proveedores_router,
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(require_modulo("admin_contable"))],
)
application_router.include_router(
    operaciones_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("operaciones"))]
)
application_router.include_router(
    soporte_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("soporte"))]
)
application_router.include_router(
    innovacion_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("innovacion"))]
)
application_router.include_router(
    licencias_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("innovacion"))]
)
application_router.include_router(
    empresa_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("configuracion"))]
)

# LLM Usage: registro de uso de modelos de lenguaje (Configuración)
application_router.include_router(
    llm_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_submodulo("configuracion", "llm"))]
)

# Recruiting: el módulo exige 'recruiting' y cada endpoint, el permiso de su ítem ('recruiting.<codigo>')
application_router.include_router(
    recruiting_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("recruiting"))]
)

# Parámetros del sistema (Configuración)
application_router.include_router(
    parametros_router,
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(require_submodulo("configuracion", "parametros"))],
)

# Notificaciones (cumpleaños vía Webex + Gemini) (Configuración)
application_router.include_router(
    notificaciones_router,
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(require_submodulo("configuracion", "notificaciones"))],
)

# Proveedor OpenID Connect (F21): API interna que usa el frontend para publicar /.well-known/openid-configuration y
# /oidc/* en core.dicsys.ai. Sin dependencia global: autorizar pide la sesión de Core, token autentica al cliente.
application_router.include_router(oidc_router, prefix=settings.api_v1_prefix)

# Tareas programadas: estado, historial, corrida a mano y cola de envíos (Configuración, F19)
application_router.include_router(
    tareas_router,
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(require_submodulo("configuracion", "tareas_programadas"))],
)

# Bandeja personal de notificaciones internas: cualquier usuario autenticado.
application_router.include_router(
    notificaciones_internas_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)]
)

# Recibos de sueldo: admin (protegido por admin_contable) y público (empleado)
# IMPORTANTE: admin va primero para que sus rutas específicas (/lotes, etc.) matcheen
# La ruta /descargar existe en ambos routers pero el público valida ownership internamente
application_router.include_router(
    recibos_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("admin_contable"))]
)
application_router.include_router(
    recibos_nomina_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("nomina"))]
)
application_router.include_router(
    recibos_public_router,
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(get_current_user)],  # Solo JWT, el endpoint valida permisos internamente
)

# Auditoría: público para crear (cualquier user logueado con empresa activa),
# protegido por el módulo 'auditoria' para listar.
application_router.include_router(
    auditoria_public_router, prefix=settings.api_v1_prefix, dependencies=[Depends(get_current_user)]
)
application_router.include_router(
    auditoria_router, prefix=settings.api_v1_prefix, dependencies=[Depends(require_modulo("auditoria"))]
)

# Router público de innovación (sin autenticación, para verificar certificados)
application_router.include_router(innovacion_public_router, prefix=settings.api_v1_prefix)


@application_router.get("/", tags=["Sistema"])
async def root():
    """Endpoint raíz con información de la API."""
    return {
        "message": f"Bienvenido a {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
        "reference": "/reference",
        "status": "running",
    }


@application_router.get("/reference", include_in_schema=False)
async def referencia_de_la_api():
    """Referencia de la API con Scalar (F07-P01), en paralelo con Swagger (/docs) y ReDoc por un tiempo. Sin el proxy
    externo de Scalar, sin su agente y sin telemetría: la página solo le pide /openapi.json a este backend."""
    return get_scalar_api_reference(
        openapi_url="/openapi.json",
        title=f"{settings.app_name} · API",
        scalar_proxy_url="",
        agent=AgentScalarConfig(disabled=True),
        telemetry=False,
    )


@application_router.get("/health", tags=["Sistema"])
async def health_check():
    """Endpoint de health check para monitoreo."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "environment": "development" if settings.debug else "production",
    }


def create_app(*, testing: bool = False) -> FastAPI:
    """Construye una instancia aislada de la aplicacion."""
    is_testing = testing or settings.environment == "testing"
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=None if is_testing else lifespan,
        description=settings.description,
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
    )
    application.state.testing = is_testing
    # El 422 que responde el handler propio, declarado en el OpenAPI en lugar del de FastAPI (F07-P08, PG-14)
    application.openapi = lambda: errores.con_errores_propios(FastAPI.openapi(application))
    # Contadores del límite de intentos del ingreso (F07-P07): uno por app, en la memoria del proceso
    application.state.limitador = Limitador()
    application.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # el 429 del límite de intentos (F07-P07) y el id de pedido (F06-P06): la SPA en otro origen (Vite en
        # desarrollo) los puede leer
        expose_headers=["Retry-After", "X-Request-ID"],
    )
    # URLs firmadas de descarga (F07-P06): un GET con ?firma= válida pasa con el Bearer de quien la pidió
    application.add_middleware(FirmaDeDescarga)
    # Id de pedido (F06-P06), el último agregado y por eso el de más afuera: cubre también lo que respondan los otros
    application.add_middleware(IdDePedido)

    files_path = (
        Path(tempfile.gettempdir()) / "dicsys-core-test" / "files" if is_testing else Path(settings.storage_local_path)
    )
    files_path.mkdir(parents=True, exist_ok=True)
    (files_path / "clientes-logo").mkdir(parents=True, exist_ok=True)
    (files_path / "empresas-logo").mkdir(parents=True, exist_ok=True)
    application.mount("/files", StaticFiles(directory=str(files_path)), name="files")
    if settings.pagina_de_prueba_de_sesion:
        # DoD del gate de F07 (F07-P12): una página fuera de Flask que usa la API como la SPA, en el mismo origen
        application.mount("/prueba", StaticFiles(directory=str(Path(__file__).parent / "prueba")), name="prueba")
    application.include_router(application_router)
    return application


app = create_app()

if __name__ == "__main__":
    import uvicorn

    print(f"🚀 Iniciando servidor en http://{settings.host}:{settings.port}")
    print(f"📍 Modo: {'desarrollo' if settings.debug else 'producción'}")
    print(f"📚 Documentación: http://{settings.host}:{settings.port}/docs")

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info" if settings.debug else "warning",
    )
