"""
Routers para el módulo de Innovación.
"""

import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.dependencies import get_db, get_empresa_activa, get_empresa_cuit, require_submodulo
from backend.modules.innovacion.models import TECNOLOGIAS_SUGERIDAS, TEMATICAS_SUGERIDAS, TIPOS_CERTIFICACION
from backend.modules.innovacion.schemas import (
    CertificacionCreate,
    CertificacionList,
    CertificacionMiPathUpdate,
    CertificacionResponse,
    CertificacionUpdate,
    EventoAsistenciaRequest,
    EventoCreate,
    EventoList,
    EventoResponse,
    EventoUpdate,
    MiEventoResponse,
)
from backend.modules.innovacion.services import CertificacionService, EventoService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/innovacion", tags=["Innovación"])

# Shortcuts de submódulo
require_resumen = Depends(require_submodulo("innovacion", "resumen"))
require_mi_path = Depends(require_submodulo("innovacion", "mi_path"))
require_admin_cert = Depends(require_submodulo("innovacion", "admin_certificaciones"))
require_admin_eventos = Depends(require_submodulo("innovacion", "admin_eventos"))

# Configuración de archivos de certificados
CERTS_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
CERTS_MAX_SIZE = 5 * 1024 * 1024  # 5MB
CAMPOS_IMAGEN_VALIDOS = {
    "cert_noncode_imagen",
    "cert_n8n_imagen",
    "cert_ruta1_imagen",
    "cert_ruta2_imagen",
    "cert_ruta3_imagen",
    "cert_noncode_plan",
    "cert_n8n_plan",
}


def _obtener_empleado(db: Session, current_user: Usuario, empresa_id: uuid.UUID):
    """Busca el empleado vinculado al usuario actual por DNI y empresa."""
    from backend.modules.nomina.models import Empleado

    if not current_user.dni:
        raise HTTPException(404, "Tu usuario no tiene DNI cargado, no se puede vincular con un empleado")
    empleado = (
        db.query(Empleado)
        .filter(Empleado.dni == current_user.dni, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
        .first()
    )
    if not empleado:
        raise HTTPException(404, "No se encontró un empleado vinculado a tu usuario")
    return empleado


# ============ TIPOS (estáticos) ============


@router.get("/tipos")
async def listar_tipos(current_user=require_mi_path):
    """Devuelve los tipos de certificación disponibles (estáticos)."""
    return [{"key": k, **v} for k, v in TIPOS_CERTIFICACION.items()]


@router.get("/tecnologias")
async def listar_tecnologias(current_user=require_mi_path):
    """Devuelve la lista de tecnologías sugeridas para autocompletado."""
    return sorted(TECNOLOGIAS_SUGERIDAS)


@router.get("/tematicas")
async def listar_tematicas(current_user=require_mi_path):
    """Devuelve la lista de temáticas sugeridas para autocompletado."""
    return sorted(TEMATICAS_SUGERIDAS)


# ============ RESUMEN / DASHBOARD ============


@router.get("/resumen")
async def obtener_resumen(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_resumen
):
    """Obtiene métricas del dashboard de innovación."""
    return CertificacionService.obtener_resumen(db, empresa_id)


# ============ CERTIFICACIONES ============


@router.get("/certificaciones", response_model=CertificacionList)
async def listar_certificaciones(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    estado: Optional[str] = None,
    tipo_certificacion: Optional[str] = None,
    equipo_id: Optional[str] = None,
    sin_equipo: Optional[bool] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_resumen,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if estado:
        filtros["estado"] = estado
    if tipo_certificacion:
        filtros["tipo_certificacion"] = tipo_certificacion
    if equipo_id:
        filtros["equipo_id"] = equipo_id
    if sin_equipo:
        filtros["sin_equipo"] = True
    resultado = CertificacionService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return CertificacionList(
        items=[CertificacionResponse.from_model(c) for c in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@router.get("/certificaciones/mi-path")
async def obtener_mi_path(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    """Obtiene la certificación del empleado actual (o null si no tiene)."""
    empleado = _obtener_empleado(db, current_user, empresa_id)
    cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(empleado.id))
    if not cert:
        return None
    return CertificacionResponse.from_model(cert)


@router.put("/certificaciones/mi-path", response_model=CertificacionResponse)
async def actualizar_mi_path(
    datos: CertificacionMiPathUpdate,
    finalizar: bool = True,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    """Actualiza la certificación del empleado actual (schema restringido, sin estado ni fecha_aprobacion).

    `finalizar=false` => guardado de borrador: persiste los campos pero no pasa a
    'en_revision' aunque esté todo completo (el wizard usa esto en Siguiente/Guardar).
    """
    empleado = _obtener_empleado(db, current_user, empresa_id)
    cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(empleado.id))
    if not cert:
        raise HTTPException(404, "No tenés una certificación activa")
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        if finalizar:
            cert = CertificacionService.actualizar(
                db, empresa_id, str(cert.id), datos_dict, usuario=current_user.email, finalizar=True
            )
        else:
            cert = CertificacionService.actualizar_sin_finalizar(
                db, empresa_id, str(cert.id), datos_dict, usuario=current_user.email
            )
        return CertificacionResponse.from_model(cert)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar mi-path: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar la certificación")


@router.post("/certificaciones/mi-path/volver-edicion", response_model=CertificacionResponse)
async def volver_edicion_mi_path(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    """Devuelve la certificación del empleado actual a estado editable (en_progreso)."""
    empleado = _obtener_empleado(db, current_user, empresa_id)
    cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(empleado.id))
    if not cert:
        raise HTTPException(404, "No tenés una certificación activa")
    try:
        cert = CertificacionService.volver_a_edicion(db, empresa_id, str(cert.id), usuario=current_user.email)
        return CertificacionResponse.from_model(cert)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/certificaciones/mi-path/certificado/{campo}")
async def subir_certificado_mi_path(
    campo: str,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user: Usuario = require_mi_path,
):
    """Sube una imagen de certificado para la certificación del empleado actual."""
    from backend.core.storage import cloud_storage

    if campo not in CAMPOS_IMAGEN_VALIDOS:
        raise HTTPException(400, f"Campo inválido: {campo}")

    empleado = _obtener_empleado(db, current_user, empresa_id)
    cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(empleado.id))
    if not cert:
        raise HTTPException(404, "No tenés una certificación activa")

    ext = Path(archivo.filename).suffix.lower()
    if ext not in CERTS_ALLOWED_EXT:
        raise HTTPException(400, f"Formato no permitido. Use: {', '.join(CERTS_ALLOWED_EXT)}")

    content = await archivo.read()
    if len(content) > CERTS_MAX_SIZE:
        raise HTTPException(400, "El archivo excede el tamaño máximo de 5MB")

    # Eliminar archivo anterior del storage si existe
    old_url = getattr(cert, campo, None)
    if old_url:
        cloud_storage.delete(old_url)

    # Subir nuevo archivo al storage
    folder = f"certificaciones-{empresa_cuit}/{empleado.id}"
    key = cloud_storage.build_key(folder, content, ext=ext)
    cloud_storage.upload(key, content, archivo.content_type or "application/octet-stream")

    # Actualizar campo en la certificación + auto-setear fecha si está vacía
    datos_update = {campo: key}

    # Mapeo imagen -> fecha correspondiente
    campo_fecha_map = {
        "cert_noncode_imagen": "cert_noncode_fecha",
        "cert_n8n_imagen": "cert_n8n_fecha",
        "cert_ruta1_imagen": "cert_ruta1_fecha",
        "cert_ruta2_imagen": "cert_ruta2_fecha",
        "cert_ruta3_imagen": "cert_ruta3_fecha",
    }
    campo_fecha = campo_fecha_map.get(campo)
    if campo_fecha and not getattr(cert, campo_fecha, None):
        from datetime import date

        datos_update[campo_fecha] = date.today()

    try:
        cert = CertificacionService.actualizar(db, empresa_id, str(cert.id), datos_update, usuario=current_user.email)
        return {
            "campo": campo,
            "url": cloud_storage.get_url(key),
            "key": key,
            "fecha_auto": campo_fecha if campo_fecha in datos_update else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al guardar certificado: {e}", exc_info=True)
        raise HTTPException(500, "Error al guardar el certificado")


@router.delete("/certificaciones/mi-path/certificado/{campo}")
async def eliminar_certificado_mi_path(
    campo: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    """Elimina una imagen de certificado de la certificación del empleado actual."""
    if campo not in CAMPOS_IMAGEN_VALIDOS:
        raise HTTPException(400, f"Campo inválido: {campo}")

    empleado = _obtener_empleado(db, current_user, empresa_id)
    cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(empleado.id))
    if not cert:
        raise HTTPException(404, "No tenés una certificación activa")

    old_url = getattr(cert, campo, None)
    if old_url:
        old_path = Path("/data") / old_url.lstrip("/")
        if old_path.exists():
            old_path.unlink()

    try:
        cert = CertificacionService.actualizar(db, empresa_id, str(cert.id), {campo: None}, usuario=current_user.email)
        return {"campo": campo, "url": None}
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al eliminar certificado: {e}", exc_info=True)
        raise HTTPException(500, "Error al eliminar el certificado")


@router.get("/certificaciones/{id}", response_model=CertificacionResponse)
async def obtener_certificacion(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_cert,
):
    cert = CertificacionService.obtener(db, empresa_id, id)
    if not cert:
        raise HTTPException(404, "Certificación no encontrada")
    return CertificacionResponse.from_model(cert)


@router.get("/certificaciones/{id}/perfil-logros")
async def obtener_perfil_logros(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_resumen,
):
    """Obtiene perfil de logros: datos del empleado + certificación + eventos + equipo."""
    resultado = CertificacionService.obtener_perfil_logros(db, empresa_id, id)
    if not resultado:
        raise HTTPException(404, "Certificación no encontrada")
    return resultado


@router.get("/empleados/{empleado_id}/perfil-logros")
async def obtener_perfil_logros_empleado(
    empleado_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_resumen,
):
    """Perfil de logros por id de EMPLEADO. Funciona aunque no tenga certificación."""
    resultado = CertificacionService.obtener_perfil_logros_por_empleado(db, empresa_id, empleado_id)
    if not resultado:
        raise HTTPException(404, "Empleado no encontrado")
    return resultado


@router.post("/certificaciones", response_model=CertificacionResponse, status_code=201)
async def crear_certificacion(
    datos: CertificacionCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    try:
        empleado = _obtener_empleado(db, current_user, empresa_id)
        datos_dict = datos.model_dump()
        datos_dict["empleado_id"] = str(empleado.id)
        cert = CertificacionService.crear(db, empresa_id, datos_dict, usuario=current_user.email)
        return CertificacionResponse.from_model(cert)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear certificación: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear la certificación")


@router.put("/certificaciones/{id}", response_model=CertificacionResponse)
async def actualizar_certificacion(
    id: str,
    datos: CertificacionUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_cert,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        cert = CertificacionService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
        if not cert:
            raise HTTPException(404, "Certificación no encontrada")
        return CertificacionResponse.from_model(cert)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar certificación: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar la certificación")


@router.delete("/certificaciones/{id}")
async def eliminar_certificacion(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_cert,
):
    if not CertificacionService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Certificación no encontrada")
    return {"message": "Certificación eliminada"}


# ============ EVENTOS ============


@router.get("/eventos/empleados")
async def listar_empleados_eventos(
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_eventos,
):
    """Lista empleados activos para el selector de asistentes de eventos."""
    empleados = EventoService.listar_empleados(db, empresa_id, buscar)
    return [
        {
            "id": str(e.id),
            "apellido": e.apellido,
            "nombre": e.nombre,
            "email_corporativo": e.email_corporativo or "",
            "display": f"{e.apellido}, {e.nombre}",
        }
        for e in empleados
    ]


@router.get("/eventos/asistentes-ranking")
async def ranking_asistentes_eventos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=100),
    buscar: Optional[str] = None,
    equipo_id: Optional[str] = None,
    evento_id: Optional[str] = None,
    sin_participacion: bool = False,
    tag: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_resumen,
):
    """Lista asistentes ordenados por mayor participación en eventos."""
    return EventoService.ranking_asistentes(
        db,
        empresa_id,
        pagina,
        por_pagina,
        buscar,
        equipo_id=equipo_id,
        evento_id=evento_id,
        sin_participacion=sin_participacion,
        tag=tag,
    )


@router.get("/eventos/asistentes-por-equipo")
async def asistentes_por_equipo(
    equipo_id: Optional[str] = None,
    evento_id: Optional[str] = None,
    tag: Optional[str] = None,
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_resumen,
):
    """Agrupa métricas de asistencia por equipo."""
    return EventoService.resumen_asistentes_por_equipo(
        db, empresa_id, equipo_id=equipo_id, evento_id=evento_id, tag=tag, buscar=buscar
    )


@router.get("/eventos/tags-opciones")
async def opciones_tags_eventos(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_resumen
):
    """Lista de tags disponibles para filtrar el dashboard de Innovación."""
    return EventoService.tags_disponibles(db, empresa_id)


@router.get("/eventos/opciones")
async def opciones_eventos(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_resumen
):
    """Lista eventos para filtros del dashboard de Innovación."""
    eventos = EventoService.listar(db, empresa_id, pagina=1, por_pagina=100, filtros={})["items"]
    return [
        {
            "id": str(evento.id),
            "nombre": evento.nombre,
            "fecha": evento.fecha,
        }
        for evento in eventos
    ]


@router.get("/eventos/mis-eventos", response_model=List[MiEventoResponse])
async def mis_eventos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mi_path,
):
    """Obtiene los eventos a los que asistió el empleado vinculado al usuario actual."""
    empleado = _obtener_empleado(db, current_user, empresa_id)
    eventos = EventoService.obtener_eventos_empleado(db, empresa_id, str(empleado.id))
    return [MiEventoResponse.model_validate(e) for e in eventos]


@router.get("/eventos", response_model=EventoList)
async def listar_eventos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_eventos,
):
    filtros = {"buscar": buscar} if buscar else {}
    resultado = EventoService.listar(db, empresa_id, pagina, por_pagina, filtros)
    items_response = []
    for e in resultado["items"]:
        resp = EventoResponse(
            id=str(e.id),
            nombre=e.nombre,
            fecha=e.fecha,
            duenio=e.duenio,
            tags=e.tags or [],
            cantidad_asistentes=len(e.asistentes),
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
        items_response.append(resp)
    return EventoList(
        items=items_response,
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@router.get("/eventos/{id}", response_model=EventoResponse)
async def obtener_evento(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_eventos,
):
    evento = EventoService.obtener(db, empresa_id, id)
    if not evento:
        raise HTTPException(404, "Evento no encontrado")
    return EventoResponse(
        id=str(evento.id),
        nombre=evento.nombre,
        fecha=evento.fecha,
        duenio=evento.duenio,
        tags=evento.tags or [],
        cantidad_asistentes=len(evento.asistentes),
        created_at=evento.created_at,
        updated_at=evento.updated_at,
    )


@router.post("/eventos", response_model=EventoResponse, status_code=201)
async def crear_evento(
    datos: EventoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_eventos,
):
    try:
        evento = EventoService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return EventoResponse(
            id=str(evento.id),
            nombre=evento.nombre,
            fecha=evento.fecha,
            duenio=evento.duenio,
            tags=evento.tags or [],
            cantidad_asistentes=len(evento.asistentes),
            created_at=evento.created_at,
            updated_at=evento.updated_at,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear evento: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el evento")


@router.put("/eventos/{id}", response_model=EventoResponse)
async def actualizar_evento(
    id: str,
    datos: EventoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_eventos,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        evento = EventoService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
        if not evento:
            raise HTTPException(404, "Evento no encontrado")
        return EventoResponse(
            id=str(evento.id),
            nombre=evento.nombre,
            fecha=evento.fecha,
            duenio=evento.duenio,
            tags=evento.tags or [],
            cantidad_asistentes=len(evento.asistentes),
            created_at=evento.created_at,
            updated_at=evento.updated_at,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar evento: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar el evento")


@router.delete("/eventos/{id}")
async def eliminar_evento(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_eventos,
):
    if not EventoService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Evento no encontrado")
    return {"message": "Evento eliminado"}


@router.put("/eventos/{id}/asistentes")
async def asignar_asistentes(
    id: str,
    datos: EventoAsistenciaRequest,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_eventos,
):
    """Asigna asistentes (empleados) a un evento (reemplaza los existentes)."""
    try:
        evento = EventoService.asignar_asistentes(db, empresa_id, id, datos.empleado_ids)
        return {"message": f"Se asignaron {len(evento.asistentes)} asistentes al evento"}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al asignar asistentes: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al asignar asistentes")


@router.get("/eventos/{id}/asistentes")
async def obtener_asistentes(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_eventos,
):
    """Obtiene la lista de asistentes (empleados) de un evento."""
    evento = EventoService.obtener(db, empresa_id, id)
    if not evento:
        raise HTTPException(404, "Evento no encontrado")
    return [
        {
            "id": str(e.id),
            "apellido": e.apellido,
            "nombre": e.nombre,
            "email_corporativo": e.email_corporativo or "",
            "display": f"{e.apellido}, {e.nombre}",
        }
        for e in evento.asistentes
    ]


# === ROUTER PÚBLICO (sin autenticación) ===
public_router = APIRouter(prefix="/innovacion", tags=["Innovación Pública"])


@public_router.get("/certificaciones/{id}/public", response_model=CertificacionResponse)
async def obtener_certificacion_publica(id: str, db: Session = Depends(get_db)):
    """Endpoint público para verificar un certificado por UUID."""
    cert = CertificacionService.obtener_publico(db, id)
    if not cert or cert.estado != "completada":
        raise HTTPException(404, "Certificación no encontrada")
    return CertificacionResponse.from_model(cert)


@public_router.get("/certificaciones/{id}/og-image.png")
async def og_image_certificacion(id: str, verify: Optional[str] = None, db: Session = Depends(get_db)):
    """Banner og:image (1200x627) del certificado para redes sociales.

    Genera-si-no-existe y cachea en disco (volumen OG_CACHE_DIR). El frontend
    lo proxea. `verify` es la URL pública del certificado (para el QR / ID).
    """
    import glob
    import os
    import re as _re

    from fastapi.responses import FileResponse

    from backend.modules.innovacion.og_image import (
        DESIGN_VERSION,
        GENERIC_PATH,
        generate_og_image,
        slugify_name,
    )

    cert = CertificacionService.obtener_publico(db, id)
    if not cert:
        raise HTTPException(404, "Certificación no encontrada")

    resp = CertificacionResponse.from_model(cert)
    name = resp.empleado_nombre or ""
    slug = slugify_name(name)
    verify_url = verify or f"/certificates/{id}"

    # Versión de cache: DESIGN_VERSION (diseño) + updated_at (datos del cert).
    ver = "d{}-{}".format(
        DESIGN_VERSION,
        _re.sub(r"\D", "", str(resp.updated_at or ""))[:14] or "0",
    )
    cache_base = os.getenv("OG_CACHE_DIR", "/data/innovacion/certificados")
    cache_dir = os.path.join(cache_base, id)
    out_path = os.path.join(cache_dir, f"{slug}.{ver}.png")

    if not os.path.exists(out_path):
        try:
            # Limpiar versiones previas de este certificado (dir es por id).
            if os.path.isdir(cache_dir):
                for old in glob.glob(os.path.join(cache_dir, "*.png")):
                    try:
                        os.remove(old)
                    except OSError:
                        pass
            generate_og_image(name, verify_url, out_path)
        except Exception as e:
            logging.getLogger(__name__).error(
                "og:image: no se pudo generar/escribir en '%s' (%s). "
                "Verificar que el volumen OG_CACHE_DIR sea escribible. "
                "Sirviendo imagen genérica.",
                cache_dir,
                e,
            )
            return FileResponse(GENERIC_PATH, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})

    return FileResponse(out_path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
