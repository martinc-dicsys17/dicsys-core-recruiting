"""
Tareas programadas de Actualización de Datos (F19-P03, F19-P08).

Cada proceso de Configuración → Actualización de Datos se puede programar: lo corre
el motor de tareas con el horario de Parámetros → «Tareas programadas» (hora
Argentina). Arrancan apagados, salvo lo que ya venía andando (membresías de Webex
conserva su configuración vieja, migrada sin cambiar el horario real). Si el proceso
termina con error, la corrida falla y sale la alerta.
"""

from sqlalchemy.orm import Session

from backend.modules.sincronizacion.services import SincronizacionService
from backend.modules.tareas.registro import FalloTarea, registrar_tarea

USUARIO = "programador@sistema"
CON_EMPRESA = ("carga_masiva_starmiles", "carga_charlas_innovacion")  # piden la empresa


def _correr_proceso(codigo: str):
    def correr(db: Session) -> str:
        proceso = SincronizacionService.obtener_por_codigo(db, codigo)
        if proceso is None:
            raise FalloTarea(f"El proceso «{codigo}» no existe en Actualización de Datos")
        if not proceso.activo:
            return "El proceso está desactivado en Actualización de Datos: se omite"
        empresa_id = SincronizacionService._obtener_empresa_dicsys(db).id if codigo in CON_EMPRESA else None
        resultado = SincronizacionService.ejecutar_sincronizacion(
            db, str(proceso.id), usuario=USUARIO, empresa_id=empresa_id
        )
        if not resultado.get("exito"):
            raise FalloTarea(resultado.get("mensaje") or "El proceso terminó con error")
        return (
            f"{resultado.get('mensaje') or 'OK'} · {resultado.get('registros_procesados', 0)} procesados, "
            f"{resultado.get('registros_creados', 0)} creados, {resultado.get('registros_actualizados', 0)} "
            f"actualizados, {resultado.get('registros_errores', 0)} con error"
        )

    return correr


PROCESOS = (
    ("sync_nomina_odoo", "Nómina desde Odoo", "Trae la nómina desde la base de Odoo."),
    ("crear_usuarios_faltantes", "Usuarios faltantes", "Crea la cuenta de los empleados activos que no tienen."),
    ("carga_masiva_starmiles", "Carga masiva de StarMiles", "Carga el CSV de StarMiles."),
    ("carga_charlas_innovacion", "Charlas de innovación", "Carga el CSV de charlas y asistentes."),
    ("carga_administracion_recibos", "Recibos de administración", "Carga el CSV de recibos de administración."),
    (
        "sync_webex_membresias",
        "Membresías de Webex",
        "Sincroniza el team Dicsys y sus espacios (agrega y quita gente de Webex: activar a conciencia).",
    ),
)

for codigo, nombre, descripcion in PROCESOS:
    registrar_tarea(
        codigo=codigo,
        nombre=nombre,
        modulo="Actualización de Datos",
        funcion=_correr_proceso(codigo),
        descripcion=descripcion,
        horario_default="08:00",
        activa_default=False,
    )
