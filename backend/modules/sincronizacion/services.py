"""
Servicios para Sincronización de Datos.
"""

import csv
import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session

from backend.core.utils import utc_now
from backend.modules.empresa.models import Empresa, core_usuario_empresa
from backend.modules.innovacion.models import Evento
from backend.modules.nomina.models import Empleado
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.sincronizacion.models import LogSincronizacion, ProcesoSincronizacion
from backend.modules.starmiles.models import CategoriaDesafio, Desafio, ItemCanje
from backend.modules.usuarios import emails_corporativos
from backend.modules.usuarios.models import Usuario

SYNC_NAMESPACE_UUID = uuid.UUID("a4a68db3-3d71-4657-b6fb-4edda2d72430")

# Timeout (segundos) de las llamadas a la API de Webex durante la sincronización.
WEBEX_SYNC_TIMEOUT = 15.0

EVENTOS_CHARLAS_INNOVACION = [
    {
        "codigo": "data_oracle_2026_01_06",
        "nombre": "AI + Data/Oracle",
        "csv_charla": "Data+Oracle",
        "fecha": "2026-01-06",
    },
    {
        "codigo": "data_sql_server_2026_01_13",
        "nombre": "AI + Data/SQL Server",
        "csv_charla": "Data+SQL Server",
        "fecha": "2026-01-13",
    },
    {"codigo": "data_cloud_2026_01_27", "nombre": "AI + Data/Cloud", "csv_charla": "Data+Cloud", "fecha": "2026-01-27"},
    {"codigo": "dev_2026_02_03", "nombre": "AI + Dev", "csv_charla": "Dev", "fecha": "2026-02-03"},
    {"codigo": "qa_2026_02_10", "nombre": "AI + QA", "csv_charla": "QA", "fecha": "2026-02-10"},
    {"codigo": "cobol_2026_05_14", "nombre": "AI + Cobol", "csv_charla": "Cobol", "fecha": "2026-05-14"},
]


class OdooService:
    """Servicio para conexión directa a PostgreSQL de Odoo."""

    @staticmethod
    def get_connection_url() -> str:
        """Construye la URL de conexión a PostgreSQL de Odoo."""
        host = os.getenv("ODOO_HOST", "localhost")
        port = os.getenv("ODOO_PORT", "5432")
        db = os.getenv("ODOO_DB", "postgres")
        user = os.getenv("ODOO_USER", "odoo")
        password = os.getenv("ODOO_PASSWORD", "")

        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @staticmethod
    def conectar():
        """Establece conexión directa a PostgreSQL de Odoo."""
        url = OdooService.get_connection_url()
        engine = create_engine(url, pool_pre_ping=True)
        return engine

    @staticmethod
    def ejecutar_query(engine, query: str) -> List[Dict]:
        """Ejecuta una consulta SQL y retorna los resultados como lista de dicts."""
        with engine.connect() as conn:
            result = conn.execute(text(query))
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    @staticmethod
    def extraer_valor(valor, idioma_preferido: str = "es_AR"):
        """
        Extrae el valor de un campo que puede ser string o dict de traducciones.
        Odoo 16+ guarda campos traducibles como JSONB: {'en_US': 'Value', 'es_AR': 'Valor'}
        """
        if valor is None:
            return None
        if isinstance(valor, str):
            return valor
        if isinstance(valor, dict):
            # Intentar idioma preferido, luego español, luego inglés, luego el primero disponible
            for lang in [idioma_preferido, "es_AR", "es_ES", "en_US", "en_GB"]:
                if lang in valor:
                    return valor[lang]
            # Si no hay ninguno de los preferidos, devolver el primer valor
            if valor:
                return list(valor.values())[0]
        return str(valor) if valor else None


class SincronizacionService:
    """Servicio para gestión de procesos de sincronización."""

    @staticmethod
    def _obtener_empresa_dicsys(db: Session) -> Empresa:
        """Obtiene la primera empresa activa (Dicsys). Lanza error si no existe."""
        empresa = (
            db.query(Empresa)
            .filter(Empresa.deleted_at.is_(None), Empresa.activo == True)
            .order_by(Empresa.created_at)
            .first()
        )
        if not empresa:
            raise ValueError("No se encontró ninguna empresa activa en el sistema")
        return empresa

    @staticmethod
    def crear_procesos_default(db: Session) -> bool:
        """Crea los procesos de sincronización por defecto."""
        if db.query(ProcesoSincronizacion).first():
            return False

        # Proceso de sincronización de nómina desde Odoo
        proceso_nomina = ProcesoSincronizacion(
            codigo="sync_nomina_odoo",
            nombre="Actualización de Nómina desde Odoo",
            descripcion="Sincroniza empleados, departamentos y puestos desde Odoo ERP",
            tipo_origen="odoo",
            configuracion=json.dumps(
                {
                    "modelo_empleado": "hr.employee",
                    "modelo_departamento": "hr.department",
                    "modelo_puesto": "hr.job",
                }
            ),
            query_sql="""
-- Query de referencia para hr.employee en Odoo
-- Campos principales: id, name, work_email, department_id, job_id, 
-- identification_id (DNI), birthday, gender, marital, mobile_phone
            """,
            activo=True,
        )
        db.add(proceso_nomina)

        # Proceso de creación de usuarios faltantes
        proceso_usuarios = ProcesoSincronizacion(
            codigo="crear_usuarios_faltantes",
            nombre="Crear Usuarios Faltantes",
            descripcion="Crea usuarios para empleados activos que no tienen cuenta en el sistema",
            tipo_origen="interno",
            configuracion=json.dumps(
                {
                    "enviar_email": True,
                    "solicitar_password": True,
                }
            ),
            activo=True,
        )
        db.add(proceso_usuarios)

        # Proceso de carga masiva de StarMiles
        proceso_starmiles = ProcesoSincronizacion(
            codigo="carga_masiva_starmiles",
            nombre="Carga Masiva StarMiles",
            descripcion="Carga categorías, desafíos e items de canje desde archivo CSV de seeds",
            tipo_origen="archivo",
            configuracion=json.dumps(
                {
                    "archivo_csv": "backend/seeds/star-miles-carga-masiva.csv",
                    "limpiar_datos": True,
                }
            ),
            activo=True,
        )
        db.add(proceso_starmiles)

        proceso_charlas = ProcesoSincronizacion(
            codigo="carga_charlas_innovacion",
            nombre="Carga Charlas Innovación",
            descripcion="Carga eventos de innovación y participantes desde CSV de charlas",
            tipo_origen="archivo",
            configuracion=json.dumps(
                {
                    "archivo_csv": "backend/seeds/data-charlas - Hoja 1.csv",
                }
            ),
            activo=True,
        )
        db.add(proceso_charlas)

        db.commit()
        return True

    @staticmethod
    def consulta(db: Session) -> Query:
        """Los procesos de sincronización, por nombre (el router la pagina)."""
        return (
            db.query(ProcesoSincronizacion)
            .filter(ProcesoSincronizacion.deleted_at.is_(None))
            .order_by(ProcesoSincronizacion.nombre)
        )

    @staticmethod
    def obtener(db: Session, id: str) -> Optional[ProcesoSincronizacion]:
        """Obtiene un proceso por ID."""
        return (
            db.query(ProcesoSincronizacion)
            .filter(ProcesoSincronizacion.id == uuid.UUID(id), ProcesoSincronizacion.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def obtener_por_codigo(db: Session, codigo: str) -> Optional[ProcesoSincronizacion]:
        """Obtiene un proceso por código."""
        return (
            db.query(ProcesoSincronizacion)
            .filter(ProcesoSincronizacion.codigo == codigo, ProcesoSincronizacion.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def actualizar(db: Session, id: str, datos: Dict) -> Optional[ProcesoSincronizacion]:
        """Actualiza un proceso."""
        proceso = SincronizacionService.obtener(db, id)
        if not proceso:
            return None

        for campo, valor in datos.items():
            if hasattr(proceso, campo) and campo != "id":
                setattr(proceso, campo, valor)

        proceso.updated_at = utc_now()
        db.commit()
        db.refresh(proceso)
        return proceso

    @staticmethod
    def ejecutar_sincronizacion(
        db: Session, proceso_id: str, usuario: str = None, empresa_id: uuid.UUID = None
    ) -> Dict:
        """Ejecuta un proceso de sincronización."""
        proceso = SincronizacionService.obtener(db, proceso_id)
        if not proceso:
            return {"exito": False, "mensaje": "Proceso no encontrado"}

        if not proceso.activo:
            return {"exito": False, "mensaje": "El proceso está desactivado"}

        # Crear log de ejecución
        log = LogSincronizacion(proceso_id=proceso.id, fecha_inicio=utc_now(), ejecutado_por=usuario)
        db.add(log)
        db.flush()

        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
        }

        try:
            if proceso.codigo == "sync_nomina_odoo":
                resultado = SincronizacionService._sync_nomina_odoo(db, proceso)
            elif proceso.codigo == "crear_usuarios_faltantes":
                resultado = SincronizacionService._crear_usuarios_faltantes(db, proceso)
            elif proceso.codigo == "carga_masiva_starmiles":
                if not empresa_id:
                    resultado["mensaje"] = "Se requiere empresa_id para carga masiva de StarMiles"
                else:
                    resultado = SincronizacionService._carga_masiva_starmiles(db, proceso, empresa_id)
            elif proceso.codigo == "carga_charlas_innovacion":
                if not empresa_id:
                    resultado["mensaje"] = "Se requiere empresa_id para carga de charlas de innovación"
                else:
                    resultado = SincronizacionService._carga_charlas_innovacion(db, proceso, empresa_id)
            elif proceso.codigo == "carga_administracion_recibos":
                resultado = SincronizacionService._carga_administracion_recibos(db, proceso)
            elif proceso.codigo == "sync_webex_membresias":
                resultado = SincronizacionService._sync_webex_membresias(db, proceso)
            else:
                resultado["mensaje"] = f"Proceso {proceso.codigo} no implementado"
        except Exception as e:
            resultado["mensaje"] = f"Error: {str(e)}"
            resultado["errores"].append(str(e))

        # Actualizar log
        log.fecha_fin = utc_now()
        log.resultado = resultado.get("resultado") or ("exitoso" if resultado["exito"] else "error")
        log.mensaje = resultado["mensaje"]
        log.registros_procesados = resultado["registros_procesados"]
        log.registros_actualizados = resultado["registros_actualizados"]
        log.registros_creados = resultado["registros_creados"]
        log.registros_errores = resultado["registros_errores"]
        detalle_errores = resultado.get("detalle_errores") or resultado.get("errores") or []
        actualizaciones = resultado.get("actualizaciones") or []
        info_log = {}
        if detalle_errores:
            info_log["errores"] = detalle_errores[:100]
        if actualizaciones:
            info_log["actualizaciones"] = actualizaciones[:200]

        if info_log:
            log.detalle_errores = json.dumps(info_log, ensure_ascii=False)

        # Actualizar proceso
        proceso.ultima_ejecucion = utc_now()
        proceso.ultimo_resultado = log.resultado
        proceso.ultimo_mensaje = resultado["mensaje"][:500] if resultado["mensaje"] else None
        proceso.registros_procesados = resultado["registros_procesados"]
        proceso.registros_actualizados = resultado["registros_actualizados"]
        proceso.registros_creados = resultado["registros_creados"]
        proceso.registros_errores = resultado["registros_errores"]

        db.commit()
        return resultado

    @staticmethod
    def _sync_nomina_odoo(db: Session, proceso: ProcesoSincronizacion) -> Dict:
        """Sincroniza nómina desde PostgreSQL de Odoo.
        Primero activos, luego inactivos descartando duplicados.
        Todos los empleados se asignan a la empresa Dicsys (primera empresa).
        """
        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
        }

        try:
            # Obtener empresa Dicsys
            empresa = SincronizacionService._obtener_empresa_dicsys(db)
            empresa_id = empresa.id
            # Solo se cargan emails corporativos de los dominios de la empresa (F22)
            dominios_corporativos = emails_corporativos.dominios_corporativos(db, empresa_id)

            engine = OdooService.conectar()

            # Mapeo de países
            paises_odoo = OdooService.ejecutar_query(engine, "SELECT id, name FROM res_country")
            pais_map = {p["id"]: OdooService.extraer_valor(p["name"]) for p in paises_odoo}

            empleados_map = {}  # odoo_id -> local_id
            dnis_procesados = set()
            emails_procesados = set()
            codigos_procesados = set()
            cuils_en_uso = set()

            # Cargar CUILs existentes en BD para evitar duplicados (filtrado por empresa)
            cuils_existentes = (
                db.query(Empleado.cuil).filter(Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id).all()
            )
            cuils_en_uso = {c.cuil for c in cuils_existentes if c.cuil}

            # PRIMERO: Empleados ACTIVOS
            empleados_activos = OdooService.ejecutar_query(
                engine,
                """
                SELECT e.id, e.name, e.work_email, e.identification_id, e.birthday,
                       e.gender, e.marital, e.mobile_phone, e.country_id, e.certificate,
                       e.study_field, e.emergency_contact, e.emergency_phone, e.parent_id,
                       e.first_contract_date, e.cuil, e.active
                FROM hr_employee e WHERE e.active = true ORDER BY e.id
            """,
            )

            # SEGUNDO: Empleados INACTIVOS
            empleados_inactivos = OdooService.ejecutar_query(
                engine,
                """
                SELECT e.id, e.name, e.work_email, e.identification_id, e.birthday,
                       e.gender, e.marital, e.mobile_phone, e.country_id, e.certificate,
                       e.study_field, e.emergency_contact, e.emergency_phone, e.parent_id,
                       e.first_contract_date, e.cuil, e.active
                FROM hr_employee e WHERE e.active = false ORDER BY e.id
            """,
            )

            todos_empleados = empleados_activos + empleados_inactivos

            for emp in todos_empleados:
                resultado["registros_procesados"] += 1

                try:
                    dni = emp.get("identification_id")
                    email = emp.get("work_email")
                    activo_odoo = emp.get("active", True)
                    codigo_odoo = f"ODOO-{emp['id']}"

                    # Parsear DNI
                    dni_int = None
                    if dni:
                        dni_str = str(dni).replace(".", "").replace("-", "").strip()
                        if dni_str.isdigit():
                            dni_int = int(dni_str)

                    # Si es inactivo, descartar si ya existe como activo
                    if not activo_odoo:
                        if dni_int and dni_int in dnis_procesados:
                            continue
                        if email and email in emails_procesados:
                            continue
                        if codigo_odoo in codigos_procesados:
                            continue

                    # Marcar como procesado
                    if dni_int:
                        dnis_procesados.add(dni_int)
                    if email:
                        emails_procesados.add(email)
                    codigos_procesados.add(codigo_odoo)

                    # Buscar existente en BD (filtrado por empresa) - PRIMERO por código ODOO, luego DNI, luego email
                    existente = (
                        db.query(Empleado)
                        .filter(
                            Empleado.codigo == codigo_odoo,
                            Empleado.deleted_at.is_(None),
                            Empleado.empresa_id == empresa_id,
                        )
                        .first()
                    )

                    if not existente and dni_int:
                        existente = (
                            db.query(Empleado)
                            .filter(
                                Empleado.dni == dni_int,
                                Empleado.deleted_at.is_(None),
                                Empleado.empresa_id == empresa_id,
                            )
                            .first()
                        )
                    if not existente and email:
                        # El de Odoo puede ser el principal o el secundario de la ficha (F22)
                        existente = next(
                            (
                                ficha
                                for ficha in emails_corporativos.fichas_con_email(db, email)
                                if ficha.empresa_id == empresa_id
                            ),
                            None,
                        )

                    # Un email de Odoo que no es de un dominio de la empresa no se carga (F22)
                    if email and emails_corporativos.dominio(email) not in dominios_corporativos:
                        resultado["errores"].append(
                            f"Empleado {emp.get('name', 'N/A')}: el email {email} no es de un dominio de la empresa "
                            f"({', '.join(dominios_corporativos)}); no se cargó"
                        )
                        email = None

                    # Parsear nombre
                    nombre_completo = OdooService.extraer_valor(emp.get("name")) or ""
                    if "," in nombre_completo:
                        partes = nombre_completo.split(",", 1)
                        apellido = partes[0].strip()
                        nombre = partes[1].strip() if len(partes) > 1 else apellido
                    else:
                        partes = nombre_completo.split(" ", 1)
                        nombre = partes[0].strip()
                        apellido = partes[1].strip() if len(partes) > 1 else nombre

                    nombre = nombre[:100] or "SIN NOMBRE"
                    apellido = apellido[:100] or "SIN APELLIDO"

                    # Mapeos
                    genero = {"male": "Masculino", "female": "Femenino", "other": "Otro"}.get(emp.get("gender"))
                    estado_civil = {
                        "single": "Soltero",
                        "married": "Casado",
                        "cohabitant": "Conviviente",
                        "widower": "Viudo",
                        "divorced": "Divorciado",
                    }.get(emp.get("marital"))
                    nivel_estudio = {
                        "graduate": "Universitario",
                        "bachelor": "Licenciatura",
                        "master": "Maestría",
                        "doctor": "Doctorado",
                        "other": "Otro",
                    }.get(emp.get("certificate"))

                    carrera_texto = OdooService.extraer_valor(emp.get("study_field"))
                    carrera_texto = carrera_texto[:150] if carrera_texto else None

                    # Buscar o crear carrera en la tabla de carreras (filtrado por empresa)
                    carrera_id_sync = None
                    if carrera_texto:
                        from backend.modules.nomina.models import Carrera

                        carrera_obj = (
                            db.query(Carrera)
                            .filter(
                                Carrera.nombre.ilike(carrera_texto),
                                Carrera.deleted_at.is_(None),
                                Carrera.empresa_id == empresa_id,
                            )
                            .first()
                        )
                        if not carrera_obj:
                            carrera_obj = Carrera(nombre=carrera_texto, empresa_id=empresa_id)
                            db.add(carrera_obj)
                            db.flush()
                        carrera_id_sync = carrera_obj.id

                    nacionalidad = pais_map.get(emp.get("country_id"))
                    nacionalidad = nacionalidad[:50] if nacionalidad else None

                    telefono = str(emp.get("mobile_phone"))[:30] if emp.get("mobile_phone") else None
                    contacto_emergencia = (
                        str(emp.get("emergency_contact"))[:100] if emp.get("emergency_contact") else None
                    )
                    numero_emergencia = str(emp.get("emergency_phone"))[:30] if emp.get("emergency_phone") else None
                    fecha_alta = emp.get("first_contract_date")
                    cuil_odoo_raw = str(emp.get("cuil"))[:13] if emp.get("cuil") else None
                    # Convertir CUIL a int: quitar guiones y caracteres no numéricos
                    cuil_odoo = (
                        int("".join(filter(str.isdigit, cuil_odoo_raw)))
                        if cuil_odoo_raw and "".join(filter(str.isdigit, cuil_odoo_raw))
                        else None
                    )

                    if existente:
                        campos_cambiados = {}

                        def registrar_cambio(campo, anterior, nuevo):
                            # Convertir dates a string para JSON serializable
                            ant_str = anterior.isoformat() if isinstance(anterior, (date, datetime)) else anterior
                            nue_str = nuevo.isoformat() if isinstance(nuevo, (date, datetime)) else nuevo
                            if ant_str != nue_str:
                                campos_cambiados[campo] = {"anterior": ant_str, "nuevo": nue_str}

                        registrar_cambio("nombre", existente.nombre, nombre)
                        existente.nombre = nombre

                        registrar_cambio("apellido", existente.apellido, apellido)
                        existente.apellido = apellido

                        # Una ficha con cuenta copia el email de la cuenta (más abajo); el de Odoo solo va a las fichas
                        # que todavía no tienen cuenta (F22)
                        if (
                            email
                            and emails_corporativos.cuenta_de_dni(db, existente.dni) is None
                            and emails_corporativos.normalizar(email)
                            != emails_corporativos.normalizar(existente.email_corporativo)
                        ):
                            registrar_cambio("email_corporativo", existente.email_corporativo, email)
                            existente.email_corporativo = email

                        registrar_cambio("telefono_personal", existente.telefono_personal, telefono)
                        existente.telefono_personal = telefono

                        registrar_cambio("genero", existente.genero, genero)
                        existente.genero = genero

                        registrar_cambio("estado_civil", existente.estado_civil, estado_civil)
                        existente.estado_civil = estado_civil

                        registrar_cambio("nacionalidad", existente.nacionalidad, nacionalidad)
                        existente.nacionalidad = nacionalidad

                        registrar_cambio("nivel_estudio", existente.nivel_estudio, nivel_estudio)
                        existente.nivel_estudio = nivel_estudio

                        registrar_cambio("carrera_id", existente.carrera_id, carrera_id_sync)
                        existente.carrera_id = carrera_id_sync

                        registrar_cambio("contacto_emergencia", existente.contacto_emergencia, contacto_emergencia)
                        existente.contacto_emergencia = contacto_emergencia

                        registrar_cambio("numero_emergencia", existente.numero_emergencia, numero_emergencia)
                        existente.numero_emergencia = numero_emergencia

                        if emp.get("birthday"):
                            registrar_cambio("fecha_nacimiento", existente.fecha_nacimiento, emp["birthday"])
                            existente.fecha_nacimiento = emp["birthday"]

                        if fecha_alta:
                            registrar_cambio("fecha_alta", existente.fecha_alta, fecha_alta)
                            existente.fecha_alta = fecha_alta

                        registrar_cambio("activo", existente.activo, activo_odoo)
                        existente.activo = activo_odoo
                        existente.updated_at = utc_now()

                        # Actualizar código si no lo tiene
                        registrar_cambio("codigo", existente.codigo, codigo_odoo)
                        if existente.codigo != codigo_odoo:
                            existente.codigo = codigo_odoo

                        # Guardar DNI anterior para buscar usuario asociado
                        antiguo_dni = existente.dni

                        # Actualizar DNI si viene de Odoo y es diferente
                        registrar_cambio("dni", existente.dni, dni_int)
                        if dni_int and existente.dni != dni_int:
                            existente.dni = dni_int

                        # Actualizar CUIL si viene de Odoo y es diferente
                        registrar_cambio("cuil", existente.cuil, cuil_odoo)
                        if cuil_odoo and existente.cuil != cuil_odoo:
                            existente.cuil = cuil_odoo

                        # Buscar y actualizar usuario asociado si existe
                        usuario_asoc = None
                        campos_usuario_cambiados = {}
                        if antiguo_dni:
                            usuario_asoc = (
                                db.query(Usuario)
                                .filter(Usuario.dni == antiguo_dni, Usuario.deleted_at.is_(None))
                                .first()
                            )
                        if not usuario_asoc and email:
                            usuario_asoc = (
                                db.query(Usuario).filter(Usuario.email == email, Usuario.deleted_at.is_(None)).first()
                            )

                        if usuario_asoc:

                            def registrar_cambio_usuario(campo, anterior, nuevo):
                                if anterior != nuevo:
                                    campos_usuario_cambiados[campo] = {"anterior": anterior, "nuevo": nuevo}

                            if dni_int:
                                registrar_cambio_usuario("dni", usuario_asoc.dni, dni_int)
                                if usuario_asoc.dni != dni_int:
                                    usuario_asoc.dni = dni_int
                            # Si el de Odoo ya es el email o el secundario de la cuenta no se toca: así no se deshace la
                            # mudanza a @dicsys.ai del primer ingreso con Google, con el @dicsys.com en Odoo (F22)
                            if email and emails_corporativos.normalizar(email) not in {
                                emails_corporativos.normalizar(usuario_asoc.email),
                                emails_corporativos.normalizar(usuario_asoc.email_secundario),
                            }:
                                registrar_cambio_usuario("email", usuario_asoc.email, email)
                                usuario_asoc.email = email
                            if nombre:
                                registrar_cambio_usuario("nombre", usuario_asoc.nombre, nombre)
                                if usuario_asoc.nombre != nombre:
                                    usuario_asoc.nombre = nombre
                            if apellido:
                                registrar_cambio_usuario("apellido", usuario_asoc.apellido, apellido)
                                if usuario_asoc.apellido != apellido:
                                    usuario_asoc.apellido = apellido
                            if telefono:
                                registrar_cambio_usuario("telefono", usuario_asoc.telefono, telefono)
                                if usuario_asoc.telefono != telefono:
                                    usuario_asoc.telefono = telefono
                            registrar_cambio_usuario("activo", usuario_asoc.activo, activo_odoo)
                            if usuario_asoc.activo != activo_odoo:
                                usuario_asoc.activo = activo_odoo

                            usuario_asoc.updated_at = utc_now()
                            usuario_asoc.updated_by = "sync_nomina_odoo"
                            # Sus fichas copian el email de la cuenta (F22)
                            emails_corporativos.copiar_a_fichas(db, usuario_asoc)

                        # Si hubo cambios, agregarlos al log
                        if campos_cambiados or campos_usuario_cambiados:
                            act_entry = {
                                "tipo": "nomina",
                                "codigo": codigo_odoo,
                                "empleado": f"{apellido}, {nombre}",
                                "campos_empleado": campos_cambiados,
                            }
                            if campos_usuario_cambiados:
                                act_entry["campos_usuario"] = campos_usuario_cambiados
                            resultado.setdefault("actualizaciones", []).append(act_entry)

                        empleados_map[emp["id"]] = existente.id
                        resultado["registros_actualizados"] += 1
                    else:
                        if not dni_int:
                            dni_int = emp["id"]

                        # Generar CUIL único
                        cuil = cuil_odoo
                        if not cuil:
                            # Generar CUIL ficticio basado en DNI
                            cuil_base = int(f"20{str(dni_int)[-8:].zfill(8)}0")
                            cuil = cuil_base
                            # Si ya existe, agregar sufijo incremental
                            sufijo = 1
                            while cuil in cuils_en_uso:
                                cuil = cuil_base + sufijo
                                sufijo += 1

                        cuils_en_uso.add(cuil)

                        nuevo = Empleado(
                            empresa_id=empresa_id,
                            codigo=codigo_odoo,
                            cuil=cuil,
                            nombre=nombre,
                            apellido=apellido,
                            dni=dni_int,
                            email_corporativo=email,
                            telefono_personal=telefono,
                            genero=genero,
                            estado_civil=estado_civil,
                            nacionalidad=nacionalidad,
                            nivel_estudio=nivel_estudio,
                            carrera_id=carrera_id_sync,
                            contacto_emergencia=contacto_emergencia,
                            numero_emergencia=numero_emergencia,
                            activo=activo_odoo,
                        )
                        if emp.get("birthday"):
                            nuevo.fecha_nacimiento = emp["birthday"]
                        if fecha_alta:
                            nuevo.fecha_alta = fecha_alta

                        # Con una cuenta de ese DNI, el email es copia del de la cuenta (F22)
                        emails_corporativos.copiar_desde_la_cuenta(db, nuevo)
                        db.add(nuevo)
                        db.flush()
                        empleados_map[emp["id"]] = nuevo.id
                        resultado["registros_creados"] += 1

                except Exception as e:
                    resultado["registros_errores"] += 1
                    resultado["errores"].append(f"Empleado {emp.get('name', 'N/A')}: {str(e)}")

            db.commit()

            # Nota: No asignamos lider_id desde Odoo, se asigna manualmente después

            resultado["exito"] = True
            resultado["mensaje"] = (
                f"Sincronización completada: {resultado['registros_creados']} creados, {resultado['registros_actualizados']} actualizados"
            )

        except Exception as e:
            db.rollback()
            resultado["mensaje"] = f"Error: {str(e)}"
            resultado["errores"].append(str(e))

        return resultado

    @staticmethod
    def consulta_logs(db: Session, proceso_id: str) -> Query:
        """Los logs de un proceso, del más nuevo al más viejo (el router la pagina)."""
        return (
            db.query(LogSincronizacion)
            .filter(LogSincronizacion.proceso_id == uuid.UUID(proceso_id))
            .order_by(LogSincronizacion.fecha_inicio.desc())
        )

    @staticmethod
    def _crear_usuarios_faltantes(db: Session, proceso: ProcesoSincronizacion) -> Dict:
        """Crea usuarios para empleados activos de Dicsys que no tienen cuenta.
        Vincula cada usuario creado a la empresa Dicsys en core_usuario_empresa.
        """
        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
        }

        try:
            # Obtener empresa Dicsys
            empresa = SincronizacionService._obtener_empresa_dicsys(db)
            empresa_id = empresa.id

            # Obtener grupo "Colaboradores" para asignar a cada usuario creado
            from backend.core.seed_data import GRUPO_COLABORADORES_SEED

            grupo_colaboradores = (
                db.query(Grupo)
                .filter(
                    Grupo.nombre == GRUPO_COLABORADORES_SEED["nombre"], Grupo.deleted_at.is_(None), Grupo.activo == True
                )
                .first()
            )

            # Obtener DNIs y emails existentes primero (queries livianas)
            dnis_con_usuario = set()
            for row in db.execute(text("SELECT dni FROM core_usuarios WHERE dni IS NOT NULL AND deleted_at IS NULL")):
                dnis_con_usuario.add(row[0])

            emails_en_uso = set()
            for row in db.execute(
                text("""
                SELECT email FROM core_usuarios WHERE deleted_at IS NULL
                UNION SELECT email_secundario FROM core_usuarios WHERE deleted_at IS NULL AND email_secundario IS NOT NULL
            """)
            ):
                emails_en_uso.add(row[0])

            # Query de empleados activos de Dicsys - solo campos necesarios
            empleados_query = text("""
                SELECT id, dni, nombre, apellido, email_corporativo, telefono_personal 
                FROM nomina_empleados 
                WHERE activo = true AND deleted_at IS NULL AND empresa_id = :empresa_id
            """)

            batch_count = 0

            for row in db.execute(empleados_query, {"empresa_id": empresa_id}):
                emp_id, emp_dni, emp_nombre, emp_apellido, emp_email, emp_telefono = row
                resultado["registros_procesados"] += 1

                # Verificar si ya tiene usuario por DNI
                if emp_dni in dnis_con_usuario:
                    continue

                # Validar que tenga email corporativo
                if not emp_email:
                    resultado["registros_errores"] += 1
                    continue

                # Verificar que el email no esté en uso
                if emp_email in emails_en_uso:
                    resultado["registros_errores"] += 1
                    continue

                try:
                    # Crear usuario
                    usuario = Usuario(
                        email=emp_email,
                        nombre=emp_nombre,
                        apellido=emp_apellido,
                        dni=emp_dni,
                        telefono=emp_telefono,
                        rol="usuario",
                        activo=True,
                        totp_required=True,
                        updated_by="sync_usuarios",
                    )

                    password_raw = str(emp_dni)
                    usuario.set_password(password_raw)

                    db.add(usuario)
                    db.flush()  # Flush para obtener el usuario.id

                    # Vincular usuario a empresa Dicsys en core_usuario_empresa
                    db.execute(
                        core_usuario_empresa.insert().values(
                            usuario_id=usuario.id, empresa_id=empresa_id, created_at=utc_now()
                        )
                    )

                    # Asignar grupo Colaboradores
                    if grupo_colaboradores:
                        db.execute(
                            usuario_grupo.insert().values(
                                usuario_id=usuario.id,
                                grupo_id=grupo_colaboradores.id,
                                empresa_id=empresa_id,
                                created_at=utc_now(),
                            )
                        )

                    resultado.setdefault("actualizaciones", []).append(
                        {
                            "tipo": "crear_usuario",
                            "usuario": f"{emp_apellido}, {emp_nombre}",
                            "email": emp_email,
                            "dni": emp_dni,
                        }
                    )

                    dnis_con_usuario.add(emp_dni)
                    emails_en_uso.add(emp_email)
                    resultado["registros_creados"] += 1
                    batch_count += 1

                    # Commit cada 25 registros
                    if batch_count >= 25:
                        db.commit()
                        batch_count = 0

                except Exception:
                    db.rollback()
                    resultado["registros_errores"] += 1
                    dnis_con_usuario.add(emp_dni)
                    emails_en_uso.add(emp_email)

            # Commit final
            if batch_count > 0:
                db.commit()

            resultado["exito"] = True
            resultado["mensaje"] = f"Completado: {resultado['registros_creados']} usuarios creados"

        except Exception as e:
            db.rollback()
            resultado["mensaje"] = f"Error: {str(e)}"
            resultado["errores"].append(str(e))

        return resultado

    @staticmethod
    def agregar_proceso_usuarios_faltantes(db: Session) -> bool:
        """Agrega el proceso de crear usuarios faltantes si no existe."""
        if db.query(ProcesoSincronizacion).filter(ProcesoSincronizacion.codigo == "crear_usuarios_faltantes").first():
            return False

        proceso = ProcesoSincronizacion(
            codigo="crear_usuarios_faltantes",
            nombre="Crear Usuarios Faltantes",
            descripcion="Crea usuarios para empleados activos que no tienen cuenta en el sistema",
            tipo_origen="interno",
            configuracion=json.dumps(
                {
                    "enviar_email": True,
                    "solicitar_password": True,
                }
            ),
            activo=True,
        )
        db.add(proceso)
        db.commit()
        return True

    @staticmethod
    def agregar_proceso_starmiles(db: Session) -> bool:
        """Agrega el proceso de carga masiva de StarMiles si no existe."""
        if db.query(ProcesoSincronizacion).filter(ProcesoSincronizacion.codigo == "carga_masiva_starmiles").first():
            return False

        proceso = ProcesoSincronizacion(
            codigo="carga_masiva_starmiles",
            nombre="Carga Masiva StarMiles",
            descripcion="Carga categorías, desafíos e items de canje desde archivo CSV de seeds",
            tipo_origen="archivo",
            configuracion=json.dumps(
                {
                    "archivo_csv": "backend/seeds/star-miles-carga-masiva.csv",
                    "limpiar_datos": True,
                }
            ),
            activo=True,
        )
        db.add(proceso)
        db.commit()
        return True

    @staticmethod
    def agregar_proceso_charlas_innovacion(db: Session) -> bool:
        """Agrega el proceso de carga de charlas de Innovación si no existe."""
        if db.query(ProcesoSincronizacion).filter(ProcesoSincronizacion.codigo == "carga_charlas_innovacion").first():
            return False

        proceso = ProcesoSincronizacion(
            codigo="carga_charlas_innovacion",
            nombre="Carga Charlas Innovación",
            descripcion="Carga eventos de innovación y participantes desde CSV de charlas",
            tipo_origen="archivo",
            configuracion=json.dumps(
                {
                    "archivo_csv": "backend/seeds/data-charlas - Hoja 1.csv",
                }
            ),
            activo=True,
        )
        db.add(proceso)
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def agregar_proceso_sync_webex(db: Session) -> bool:
        """Agrega el proceso de sincronización de membresías de Webex si no existe."""
        if db.query(ProcesoSincronizacion).filter(ProcesoSincronizacion.codigo == "sync_webex_membresias").first():
            return False

        proceso = ProcesoSincronizacion(
            codigo="sync_webex_membresias",
            nombre="Sincronización de Membresías Webex",
            descripcion=(
                "Verifica que los empleados activos estén en el team Dicsys y en cada "
                "espacio del team (innovación, presentaciones, tech-learning, off-topic, "
                "soporte-it); invita a los que falten."
            ),
            tipo_origen="api",
            configuracion=json.dumps(
                {
                    "team_param": "webex_team_dicsys_id",
                    "espacios_param": "webex_sync_espacios",
                }
            ),
            activo=True,
        )
        db.add(proceso)
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    # ── Configuración de la sincronización de Webex ───────────────────────────

    @staticmethod
    def _cargar_espacios_webex(db: Session) -> List[Dict]:
        """Lee la selección de espacios [{id, nombre}] desde webex_sync_espacios."""
        from backend.core import config as core_config

        raw = core_config.get_parameter("webex_sync_espacios", "[]", db=db)
        try:
            data = json.loads(raw) if raw else []
        except json.JSONDecodeError, TypeError:
            return []
        return [e for e in data if isinstance(e, dict) and e.get("id")]

    @staticmethod
    def _sync_webex_membresias(db: Session, proceso: ProcesoSincronizacion) -> Dict:
        """
        Asegura que los empleados activos de Dicsys estén en el team de Webex y
        en los espacios seleccionados (parámetro webex_sync_espacios, editado
        desde Configuración → Parámetros con un selector que trae los nombres
        de la API y guarda los IDs).
        Usa diff (lista miembros y agrega sólo los que faltan) para minimizar
        llamadas y evitar 409 masivos.
        """
        from backend.core import config as core_config
        from backend.core.webex import webex_service

        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
            "actualizaciones": [],
        }

        if not webex_service.is_configured:
            resultado["mensaje"] = "Webex no está configurado (falta WEBEX_BOT_TOKEN)"
            return resultado

        team_id = core_config.get_parameter("webex_team_dicsys_id", "", db=db)
        if not team_id:
            resultado["mensaje"] = "Falta configurar el Team ID de Webex (parámetro webex_team_dicsys_id)"
            return resultado

        # 1. Espacios a sincronizar = selección guardada en webex_sync_espacios.
        espacios = SincronizacionService._cargar_espacios_webex(db)

        # 2. Empleados activos de Dicsys con email corporativo. Cada persona con sus
        #    emails, el principal primero y el secundario de su cuenta: en Webex
        #    está con uno de los dos (F22).
        empresa = SincronizacionService._obtener_empresa_dicsys(db)
        filas = db.execute(
            text("""
            SELECT e.nombre, e.apellido, e.email_corporativo, u.email_secundario
            FROM nomina_empleados e
            LEFT JOIN core_usuarios u ON u.dni = e.dni AND u.deleted_at IS NULL
            WHERE e.activo = true AND e.deleted_at IS NULL AND e.empresa_id = :empresa_id
              AND e.email_corporativo IS NOT NULL AND e.email_corporativo <> ''
        """),
            {"empresa_id": empresa.id},
        ).fetchall()

        personas = []
        for f in filas:
            emails = []
            for email in (f[2], f[3]):
                email = (email or "").strip().lower()
                if email and email not in emails:
                    emails.append(email)
            if emails:
                personas.append(emails)
        emails_objetivo = {email for emails in personas for email in emails}

        # Filtro de dominios permitidos (WEBEX_SYNC_ALLOWED_DOMAINS): excluye
        # cuentas con dominios no corporativos (ej. example.com, dicsys.odoo.com,
        # typos como dicsy.com) y cuentas de sistema/prueba.
        from backend.core.config import settings

        dominios = {
            d.strip().lower().lstrip("@") for d in (settings.webex_sync_allowed_domains or "").split(",") if d.strip()
        }
        if dominios:
            descartados = {e for e in emails_objetivo if e.rsplit("@", 1)[-1] not in dominios}
            if descartados:
                resultado["errores"].append(
                    f"{len(descartados)} email(s) excluidos por dominio no permitido: "
                    + ", ".join(sorted(descartados)[:20])
                )
            emails_objetivo = emails_objetivo - descartados
            personas = [p for p in ([e for e in emails if e not in descartados] for emails in personas) if p]

        resultado["registros_procesados"] = len(personas)

        # A quien no está (con ninguno de sus emails) se lo agrega con el de su cuenta de
        # Webex: el principal si existe en Webex y si no el secundario (F22).
        from backend.core.webex import email_de_persona

        email_webex = {}

        def faltantes(miembros: set) -> List[str]:
            faltan = set()
            for emails in personas:
                if not any(email in miembros for email in emails):
                    if tuple(emails) not in email_webex:
                        email_webex[tuple(emails)] = email_de_persona(emails)
                    faltan.add(email_webex[tuple(emails)])
            return sorted(faltan)

        if not personas:
            resultado["exito"] = True
            resultado["resultado"] = "exitoso"
            resultado["mensaje"] = "No hay empleados activos con email corporativo para sincronizar"
            return resultado

        agregados = 0
        quitados = 0
        errores = 0

        # Pausa entre altas para no exceder los rate limits de la API de Webex
        # (parametrizable; importante al sincronizar muchos espacios/personas).
        import time

        try:
            sleep_seg = float(core_config.get_parameter("webex_sync_sleep_segundos", "0.3", db=db))
        except TypeError, ValueError:
            sleep_seg = 0.3
        sleep_seg = max(0.0, min(sleep_seg, 10.0))

        # 3. Membresía del team (diff: listar miembros y agregar sólo los faltantes).
        team_miembros = webex_service.list_team_member_emails(team_id, timeout=WEBEX_SYNC_TIMEOUT)
        faltan_team = faltantes(team_miembros.get("emails", set()) if team_miembros.get("success") else set())
        for email in faltan_team:
            r = webex_service.ensure_team_membership(team_id, email)
            if r.get("success") and r.get("added"):
                agregados += 1
                resultado["actualizaciones"].append(f"{email} → agregado al team Dicsys")
            elif not r.get("success"):
                errores += 1
                resultado["errores"].append(f"Team Dicsys: {email} - {r.get('error')}")
            if sleep_seg:
                time.sleep(sleep_seg)

        # 4. Membresía por cada espacio del team (mismo diff).
        for esp in espacios:
            room_id = esp["id"]
            nombre = esp.get("nombre") or room_id
            miembros = webex_service.list_room_member_emails(room_id, timeout=WEBEX_SYNC_TIMEOUT)
            faltan = faltantes(miembros.get("emails", set()) if miembros.get("success") else set())
            for email in faltan:
                r = webex_service.ensure_membership(room_id, email)
                if r.get("success") and r.get("added"):
                    agregados += 1
                    resultado["actualizaciones"].append(f"{email} → agregado a «{nombre}»")
                elif not r.get("success"):
                    errores += 1
                    resultado["errores"].append(f"{nombre}: {email} - {r.get('error')}")
                if sleep_seg:
                    time.sleep(sleep_seg)

        # 5. Offboarding (regla 3): General es la lista maestra. Quita de TODOS
        #    los espacios del team a los @dicsys que NO están en General. "Activo
        #    gana": el set a conservar = miembros de General ∪ activos @dicsys, así
        #    un activo nunca se quita (ni con lag de propagación). No toca General,
        #    ni a externos, ni al bot. Fail-safe: si no puede leer General, omite.
        general_room_id = core_config.get_parameter("webex_general_room_id", "", db=db)
        if not general_room_id:
            resultado["errores"].append(
                "Offboarding omitido: falta configurar webex_general_room_id (espacio General)."
            )
        elif not dominios:
            resultado["errores"].append("Offboarding omitido: no hay dominios permitidos configurados.")
        else:
            general = webex_service.list_room_member_emails(general_room_id, timeout=WEBEX_SYNC_TIMEOUT)
            todos_rooms = webex_service.list_rooms_by_team(team_id, timeout=WEBEX_SYNC_TIMEOUT)
            if not general.get("success"):
                resultado["errores"].append(f"Offboarding omitido: no se pudo leer General ({general.get('error')}).")
            elif not todos_rooms.get("success"):
                resultado["errores"].append(
                    f"Offboarding omitido: no se pudieron listar los espacios ({todos_rooms.get('error')})."
                )
            else:
                keep = general.get("emails", set()) | emails_objetivo  # activo gana (con cualquiera de sus emails)
                for room in todos_rooms.get("rooms", []):
                    room_id = room["id"]
                    nombre = room.get("nombre") or room_id
                    if room_id == general_room_id:
                        continue  # no se toca el espacio General (lista maestra)
                    miembros = webex_service.list_room_member_emails(room_id, timeout=WEBEX_SYNC_TIMEOUT)
                    if not miembros.get("success"):
                        resultado["errores"].append(
                            f"Offboarding «{nombre}»: no se pudo leer ({miembros.get('error')})"
                        )
                        continue
                    a_quitar = sorted(
                        e for e in miembros["emails"] if e.rsplit("@", 1)[-1] in dominios and e not in keep
                    )
                    for email in a_quitar:
                        r = webex_service.remove_membership(room_id, email)
                        if r.get("success") and r.get("removed"):
                            quitados += 1
                            resultado["actualizaciones"].append(f"{email} → quitado de «{nombre}» (no está en General)")
                        elif not r.get("success"):
                            errores += 1
                            resultado["errores"].append(f"Offboarding «{nombre}»: {email} - {r.get('error')}")
                        if sleep_seg:
                            time.sleep(sleep_seg)

        resultado["registros_creados"] = agregados
        resultado["registros_actualizados"] = quitados
        resultado["registros_errores"] = errores
        resultado["exito"] = errores == 0
        resultado["resultado"] = "exitoso" if errores == 0 else "parcial"
        resultado["mensaje"] = (
            f"{len(personas)} activos @dicsys · +{agregados} altas · "
            f"-{quitados} bajas (offboarding) · {errores} errores · {len(espacios)} espacios configurados."
        )
        return resultado

    @staticmethod
    def _evento_charla_id(empresa_id: uuid.UUID, codigo: str) -> uuid.UUID:
        """Genera un UUID estable para cada evento fijo por empresa."""
        return uuid.uuid5(SYNC_NAMESPACE_UUID, f"innovacion:evento:{empresa_id}:{codigo}")

    @staticmethod
    def _parse_fecha_creacion_charla(valor: str) -> Optional[datetime]:
        """Parsea fechas como '6 de enero de 2026 16:54'."""
        if not valor:
            return None

        valor = valor.strip()
        meses = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }
        match = re.match(r"^(\d{1,2}) de ([a-záéíóúñ]+) de (\d{4}) (\d{1,2}):(\d{2})$", valor.lower())
        if not match:
            return None

        dia, mes_nombre, anio, hora, minuto = match.groups()
        mes = meses.get(mes_nombre)
        if not mes:
            return None

        try:
            return datetime(int(anio), mes, int(dia), int(hora), int(minuto))
        except ValueError:
            return None

    @staticmethod
    def _obtener_o_crear_eventos_charlas(db: Session, empresa_id: uuid.UUID) -> Dict:
        """Crea o reutiliza la lista fija de eventos de charlas de Innovación."""
        eventos = {}
        creados = 0
        actualizados = 0

        for item in EVENTOS_CHARLAS_INNOVACION:
            fecha_evento = datetime.strptime(item["fecha"], "%Y-%m-%d").date()
            evento_id = SincronizacionService._evento_charla_id(empresa_id, item["codigo"])

            evento = db.query(Evento).filter(Evento.id == evento_id, Evento.empresa_id == empresa_id).first()

            if not evento:
                evento = (
                    db.query(Evento)
                    .filter(
                        Evento.empresa_id == empresa_id,
                        Evento.nombre == item["nombre"],
                        Evento.fecha == fecha_evento,
                        Evento.deleted_at.is_(None),
                    )
                    .first()
                )

            if evento:
                cambios = False
                if evento.deleted_at is not None:
                    evento.deleted_at = None
                    cambios = True
                if evento.nombre != item["nombre"]:
                    evento.nombre = item["nombre"]
                    cambios = True
                if evento.fecha != fecha_evento:
                    evento.fecha = fecha_evento
                    cambios = True
                if cambios:
                    evento.updated_at = utc_now()
                    actualizados += 1
            else:
                evento = Evento(
                    id=evento_id,
                    empresa_id=empresa_id,
                    nombre=item["nombre"],
                    fecha=fecha_evento,
                    tags=["AI", "Innovación"],
                    updated_by="sync_charlas_innovacion",
                )
                db.add(evento)
                creados += 1

            eventos[(item["csv_charla"], item["fecha"])] = evento

        db.flush()
        return {"eventos": eventos, "creados": creados, "actualizados": actualizados}

    @staticmethod
    def _carga_charlas_innovacion(db: Session, proceso: ProcesoSincronizacion, empresa_id: uuid.UUID) -> Dict:
        """Carga eventos fijos de Innovación y asistentes desde CSV."""
        resultado = {
            "exito": False,
            "resultado": "error",
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
            "detalle_errores": [],
        }

        try:
            config = json.loads(proceso.configuracion or "{}")
            archivo_csv = config.get("archivo_csv", "backend/seeds/data-charlas - Hoja 1.csv")

            if not Path(archivo_csv).exists():
                resultado["mensaje"] = f"Archivo CSV no encontrado: {archivo_csv}"
                resultado["errores"].append(resultado["mensaje"])
                return resultado

            eventos_info = SincronizacionService._obtener_o_crear_eventos_charlas(db, empresa_id)
            eventos_por_csv = eventos_info["eventos"]
            eventos_creados = eventos_info["creados"]
            eventos_actualizados = eventos_info["actualizados"]

            asistencias_creadas = 0
            asistencias_existentes = 0
            filas_duplicadas = 0
            filas_vistas = set()

            with open(archivo_csv, "r", encoding="utf-8-sig", newline="") as file:
                reader = csv.DictReader(file)
                for numero_fila, fila in enumerate(reader, start=2):
                    resultado["registros_procesados"] += 1

                    dni_raw = (fila.get("DNI") or "").strip()
                    charla = (fila.get("Charla") or "").strip()
                    fecha_raw = (fila.get("Fecha") or "").strip()
                    fecha_creacion_raw = (fila.get("Fecha de creación") or "").strip()
                    fila_key = (dni_raw, charla, fecha_raw)

                    if fila_key in filas_vistas:
                        filas_duplicadas += 1
                        continue
                    filas_vistas.add(fila_key)

                    contexto = {
                        "fila": numero_fila,
                        "dni": dni_raw,
                        "charla": charla,
                        "fecha": fecha_raw,
                    }

                    if not dni_raw.isdigit():
                        resultado["registros_errores"] += 1
                        resultado["detalle_errores"].append({"tipo": "dni_invalido", **contexto})
                        continue

                    try:
                        fecha_evento = datetime.strptime(fecha_raw, "%Y-%m-%d").date()
                    except ValueError:
                        resultado["registros_errores"] += 1
                        resultado["detalle_errores"].append({"tipo": "fecha_invalida", **contexto})
                        continue

                    evento = eventos_por_csv.get((charla, fecha_evento.isoformat()))
                    if not evento:
                        resultado["registros_errores"] += 1
                        resultado["detalle_errores"].append({"tipo": "evento_no_permitido", **contexto})
                        continue

                    empleados = (
                        db.query(Empleado)
                        .filter(
                            Empleado.empresa_id == empresa_id,
                            Empleado.dni == int(dni_raw),
                            Empleado.deleted_at.is_(None),
                        )
                        .all()
                    )

                    if not empleados:
                        resultado["registros_errores"] += 1
                        resultado["detalle_errores"].append({"tipo": "empleado_no_encontrado", **contexto})
                        continue

                    if len(empleados) > 1:
                        resultado["registros_errores"] += 1
                        resultado["detalle_errores"].append(
                            {
                                "tipo": "dni_duplicado_en_empleados",
                                **contexto,
                                "empleado_ids": [str(e.id) for e in empleados],
                            }
                        )
                        continue

                    empleado = empleados[0]
                    created_at = SincronizacionService._parse_fecha_creacion_charla(fecha_creacion_raw) or utc_now()
                    insert_result = db.execute(
                        text("""
                            INSERT INTO innovacion_evento_asistencia (evento_id, empleado_id, created_at)
                            VALUES (:evento_id, :empleado_id, :created_at)
                            ON CONFLICT (evento_id, empleado_id) DO NOTHING
                        """),
                        {"evento_id": evento.id, "empleado_id": empleado.id, "created_at": created_at},
                    )

                    if insert_result.rowcount:
                        asistencias_creadas += 1
                    else:
                        asistencias_existentes += 1

            resultado["registros_creados"] = eventos_creados + asistencias_creadas
            resultado["registros_actualizados"] = eventos_actualizados + asistencias_existentes
            resultado["errores"] = [
                f"{e['tipo']}: DNI={e.get('dni')} charla={e.get('charla')} fecha={e.get('fecha')}"
                for e in resultado["detalle_errores"]
            ]

            if resultado["registros_errores"] == 0:
                resultado["exito"] = True
                resultado["resultado"] = "exitoso"
            elif asistencias_creadas > 0 or asistencias_existentes > 0 or eventos_creados > 0:
                resultado["exito"] = True
                resultado["resultado"] = "parcial"
            else:
                resultado["resultado"] = "error"

            resultado["mensaje"] = (
                f"Charlas Innovación: {eventos_creados} eventos creados, "
                f"{eventos_actualizados} eventos actualizados, "
                f"{asistencias_creadas} participantes creados, "
                f"{asistencias_existentes} participantes ya existentes, "
                f"{filas_duplicadas} filas duplicadas ignoradas, "
                f"{resultado['registros_errores']} errores"
            )
            db.commit()

        except Exception as e:
            db.rollback()
            resultado["mensaje"] = f"Error en carga de charlas de innovación: {str(e)}"
            resultado["errores"].append(str(e))
            resultado["detalle_errores"].append({"tipo": "error_general", "mensaje": str(e)})

        return resultado

    @staticmethod
    def _carga_masiva_starmiles(db: Session, proceso: ProcesoSincronizacion, empresa_id: uuid.UUID) -> Dict:
        """Carga masiva de datos de StarMiles desde CSV."""
        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
        }

        try:
            config = json.loads(proceso.configuracion)
            archivo_csv = config.get("archivo_csv", "backend/seeds/star-miles-carga-masiva.csv")
            limpiar_datos = config.get("limpiar_datos", True)

            # Verificar que existe el archivo
            if not Path(archivo_csv).exists():
                resultado["mensaje"] = f"Archivo CSV no encontrado: {archivo_csv}"
                return resultado

            # Limpiar datos existentes si está configurado (solo de esta empresa)
            if limpiar_datos:
                db.query(Desafio).filter(Desafio.empresa_id == empresa_id).delete()
                db.query(CategoriaDesafio).filter(CategoriaDesafio.empresa_id == empresa_id).delete()
                db.query(ItemCanje).filter(ItemCanje.empresa_id == empresa_id).delete()
                db.commit()

            # Leer y procesar el CSV
            with open(archivo_csv, "r", encoding="utf-8") as file:
                contenido = file.read()

            # Procesar secciones del CSV
            secciones = contenido.split("--- ")

            for seccion in secciones:
                if not seccion.strip():
                    continue

                lineas = seccion.strip().split("\n")
                if not lineas:
                    continue

                titulo = lineas[0].strip()

                if titulo == "CATEGORIAS ---":
                    try:
                        resultado_cat = SincronizacionService._procesar_categorias(db, lineas[1:], empresa_id)
                        resultado["registros_creados"] += resultado_cat["creados"]
                        resultado["registros_errores"] += resultado_cat["errores"]
                        resultado["errores"].extend(resultado_cat["lista_errores"])
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        resultado["errores"].append(f"Error procesando categorías: {str(e)}")
                        resultado["registros_errores"] += 1

                elif titulo == "DESAFIOS ---":
                    try:
                        resultado_des = SincronizacionService._procesar_desafios(db, lineas[1:], empresa_id)
                        resultado["registros_creados"] += resultado_des["creados"]
                        resultado["registros_errores"] += resultado_des["errores"]
                        resultado["errores"].extend(resultado_des["lista_errores"])
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        resultado["errores"].append(f"Error procesando desafíos: {str(e)}")
                        resultado["registros_errores"] += 1

                elif titulo == "ITEMS CANJE ---":
                    try:
                        resultado_items = SincronizacionService._procesar_items_canje(db, lineas[1:], empresa_id)
                        resultado["registros_creados"] += resultado_items["creados"]
                        resultado["registros_errores"] += resultado_items["errores"]
                        resultado["errores"].extend(resultado_items["lista_errores"])
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        resultado["errores"].append(f"Error procesando items de canje: {str(e)}")
                        resultado["registros_errores"] += 1

            resultado["registros_procesados"] = resultado["registros_creados"] + resultado["registros_errores"]

            if resultado["registros_errores"] == 0:
                resultado["exito"] = True
                resultado["mensaje"] = f"Carga masiva completada: {resultado['registros_creados']} registros creados"
            else:
                resultado["mensaje"] = (
                    f"Carga completada con errores: {resultado['registros_creados']} creados, {resultado['registros_errores']} errores"
                )

        except Exception as e:
            db.rollback()
            resultado["mensaje"] = f"Error en carga masiva: {str(e)}"
            resultado["errores"].append(str(e))

        return resultado

    @staticmethod
    def _procesar_categorias(db: Session, lineas: List[str], empresa_id: uuid.UUID) -> Dict:
        """Procesa las categorías del CSV."""
        resultado = {"creados": 0, "errores": 0, "lista_errores": []}

        if not lineas:
            return resultado

        headers = [h.strip() for h in lineas[0].split(",")]

        for i, linea in enumerate(lineas[1:], 2):
            if not linea.strip():
                continue

            try:
                import io

                reader = csv.reader(io.StringIO(linea))
                valores = next(reader)

                if len(valores) != len(headers):
                    resultado["errores"] += 1
                    resultado["lista_errores"].append(f"Categoría línea {i}: número incorrecto de columnas")
                    continue

                datos = dict(zip(headers, [v.strip() for v in valores]))

                categoria = CategoriaDesafio(
                    empresa_id=empresa_id,
                    nombre=datos.get("nombre", ""),
                    descripcion=datos.get("descripcion", ""),
                    color=datos.get("color", "#3B82F6"),
                    icono=datos.get("icono", "star"),
                )

                db.add(categoria)
                resultado["creados"] += 1

            except Exception as e:
                resultado["errores"] += 1
                resultado["lista_errores"].append(f"Categoría línea {i}: {str(e)}")

        db.flush()
        return resultado

    @staticmethod
    def _procesar_desafios(db: Session, lineas: List[str], empresa_id: uuid.UUID) -> Dict:
        """Procesa los desafíos del CSV."""
        resultado = {"creados": 0, "errores": 0, "lista_errores": []}

        if not lineas:
            return resultado

        headers = [h.strip() for h in lineas[0].split(",")]

        db.flush()
        categorias = {cat.nombre: cat.id for cat in db.query(CategoriaDesafio).all()}

        for i, linea in enumerate(lineas[1:], 2):
            if not linea.strip():
                continue

            try:
                import io

                reader = csv.reader(io.StringIO(linea))
                valores = next(reader)
                if len(valores) != len(headers):
                    resultado["errores"] += 1
                    resultado["lista_errores"].append(
                        f"Desafío línea {i}: número incorrecto de columnas ({len(valores)} vs {len(headers)})"
                    )
                    continue

                datos = dict(zip(headers, [v.strip() for v in valores]))

                categoria_id = None
                categoria_nombre = datos.get("categoria_nombre", "")
                if categoria_nombre in categorias:
                    categoria_id = categorias[categoria_nombre]

                fecha_inicio = None
                fecha_vencimiento = None
                try:
                    if datos.get("fecha_inicio"):
                        fecha_inicio = datetime.strptime(datos["fecha_inicio"], "%Y-%m-%d").date()
                    if datos.get("fecha_vencimiento"):
                        fecha_vencimiento = datetime.strptime(datos["fecha_vencimiento"], "%Y-%m-%d").date()
                except ValueError:
                    pass

                desafio = Desafio(
                    empresa_id=empresa_id,
                    categoria_id=categoria_id,
                    nombre=datos.get("nombre", ""),
                    descripcion=datos.get("descripcion", ""),
                    alcance=datos.get("alcance", ""),
                    star_miles=int(datos.get("star_miles", 0)),
                    fecha_inicio=fecha_inicio,
                    fecha_vencimiento=fecha_vencimiento,
                    activo=datos.get("activo", "SI").upper() == "SI",
                )

                db.add(desafio)
                resultado["creados"] += 1

            except Exception as e:
                resultado["errores"] += 1
                resultado["lista_errores"].append(f"Desafío línea {i}: {str(e)}")

        db.flush()
        return resultado

    @staticmethod
    def _procesar_items_canje(db: Session, lineas: List[str], empresa_id: uuid.UUID) -> Dict:
        """Procesa los items de canje del CSV."""
        resultado = {"creados": 0, "errores": 0, "lista_errores": []}

        if not lineas:
            return resultado

        headers = [h.strip() for h in lineas[0].split(",")]

        for i, linea in enumerate(lineas[1:], 2):
            if not linea.strip():
                continue

            try:
                import io

                reader = csv.reader(io.StringIO(linea))
                valores = next(reader)
                if len(valores) != len(headers):
                    resultado["errores"] += 1
                    resultado["lista_errores"].append(
                        f"Item canje línea {i}: número incorrecto de columnas ({len(valores)} vs {len(headers)})"
                    )
                    continue

                datos = dict(zip(headers, [v.strip() for v in valores]))

                star_miles_costo = None
                if datos.get("star_miles_costo") and datos["star_miles_costo"].strip():
                    try:
                        star_miles_costo = int(datos["star_miles_costo"])
                    except ValueError:
                        pass

                stock = None
                if datos.get("stock") and datos["stock"].strip():
                    try:
                        stock = int(datos["stock"])
                    except ValueError:
                        pass

                tipo_raw = datos.get("tipo", "producto").lower().replace(" ", "")
                item = ItemCanje(
                    empresa_id=empresa_id,
                    tipo=tipo_raw if tipo_raw in ("producto", "mercadolibre") else "producto",
                    nombre=datos.get("nombre", ""),
                    descripcion=datos.get("descripcion", ""),
                    star_miles_costo=star_miles_costo,
                    stock=stock,
                    imagen_url=datos.get("imagen_url", "") if datos.get("imagen_url") else None,
                    activo=datos.get("activo", "SI").upper() == "SI",
                )

                db.add(item)
                resultado["creados"] += 1

            except Exception as e:
                resultado["errores"] += 1
                resultado["lista_errores"].append(f"Item canje línea {i}: {str(e)}")

        db.flush()
        return resultado

    @staticmethod
    def agregar_proceso_administracion_recibos(db: Session) -> bool:
        """Agrega el proceso de carga de administracion_recibos_export si no existe."""
        if (
            db.query(ProcesoSincronizacion)
            .filter(ProcesoSincronizacion.codigo == "carga_administracion_recibos")
            .first()
        ):
            return False

        proceso = ProcesoSincronizacion(
            codigo="carga_administracion_recibos",
            nombre="Carga Administración Recibos Export",
            descripcion="Carga el CSV administracion_export.csv en la tabla administracion_recibos_export (TRUNCATE + INSERT).",
            tipo_origen="archivo",
            configuracion=json.dumps(
                {
                    "archivo_csv": "backend/seeds/administracion_export.csv",
                    "tabla_destino": "administracion_recibos_export",
                }
            ),
            activo=True,
        )
        db.add(proceso)
        try:
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False

    @staticmethod
    def _carga_administracion_recibos(db: Session, proceso: ProcesoSincronizacion) -> Dict:
        """Carga el CSV administracion_export.csv en administracion_recibos_export.

        Estrategia: DELETE (soft truncate via ORM) + bulk insert.
        La tabla es parte del esquema que crean las migraciones de Alembic.
        """
        from backend.modules.administracion.export_recibos_models import AdministracionReciboExport

        resultado = {
            "exito": False,
            "mensaje": "",
            "registros_procesados": 0,
            "registros_actualizados": 0,
            "registros_creados": 0,
            "registros_errores": 0,
            "errores": [],
            "detalle_errores": [],
        }

        try:
            config = json.loads(proceso.configuracion or "{}")
            archivo_csv = config.get("archivo_csv", "backend/seeds/administracion_export.csv")

            ruta = Path(archivo_csv)
            if not ruta.exists():
                resultado["mensaje"] = f"Archivo CSV no encontrado: {archivo_csv}"
                return resultado

            # Reemplazar contenido completo
            db.query(AdministracionReciboExport).delete(synchronize_session=False)

            filas_a_insertar = []
            with open(ruta, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                campos_requeridos = {"colaborador", "cliente", "apellido", "nombre", "dni"}
                if not campos_requeridos.issubset({c.strip().lower() for c in (reader.fieldnames or [])}):
                    db.rollback()
                    resultado["mensaje"] = f"Encabezado inválido. Se esperaban columnas: {sorted(campos_requeridos)}"
                    return resultado

                for i, fila in enumerate(reader, start=2):
                    resultado["registros_procesados"] += 1
                    try:

                        def limpiar(v):
                            if v is None:
                                return None
                            v = str(v).strip()
                            return v if v else None

                        dni_raw = limpiar(fila.get("dni"))
                        dni_int = None
                        if dni_raw:
                            dni_str = dni_raw.replace(".", "").replace("-", "").replace(" ", "")
                            if dni_str.isdigit():
                                dni_int = int(dni_str)
                            else:
                                raise ValueError(f"DNI no numérico: {dni_raw}")

                        filas_a_insertar.append(
                            {
                                "id": uuid.uuid4(),
                                "colaborador": limpiar(fila.get("colaborador")),
                                "cliente": limpiar(fila.get("cliente")),
                                "apellido": limpiar(fila.get("apellido")),
                                "nombre": limpiar(fila.get("nombre")),
                                "dni": dni_int,
                                "created_at": utc_now(),
                            }
                        )
                    except Exception as e:
                        resultado["registros_errores"] += 1
                        msg = f"Línea {i}: {str(e)}"
                        resultado["errores"].append(msg)
                        resultado["detalle_errores"].append({"linea": i, "error": str(e), "fila": fila})

            if filas_a_insertar:
                db.bulk_insert_mappings(AdministracionReciboExport, filas_a_insertar)

            db.commit()
            insertados = len(filas_a_insertar)
            resultado["registros_creados"] = insertados
            resultado["exito"] = resultado["registros_errores"] == 0
            resultado["resultado"] = "exitoso" if resultado["exito"] else "parcial"
            resultado["mensaje"] = (
                f"Carga completada en administracion_recibos_export: "
                f"{insertados} insertados, {resultado['registros_errores']} errores"
            )

        except Exception as e:
            db.rollback()
            resultado["mensaje"] = f"Error en carga administracion_recibos: {str(e)}"
            resultado["errores"].append(str(e))
            resultado["detalle_errores"].append({"tipo": "error_general", "mensaje": str(e)})

        return resultado
