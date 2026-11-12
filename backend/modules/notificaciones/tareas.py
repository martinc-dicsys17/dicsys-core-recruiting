"""
Tareas programadas de Notificaciones (F19-P06): las corre el motor de tareas.

- Saludos de cumpleaños: el proceso de siempre (contexto, saludo con Gemini, card
  en Webex, espera al azar entre personas). Si algún saludo del día queda en error,
  la corrida falla y sale la alerta.
- Refresco del token de la cuenta lectora de Webex: mantiene viva la ventana del
  refresh token (~90 días) aunque no haya cumpleaños.

Horario y activación: Parámetros → «Tareas programadas» (hora Argentina).
"""

from datetime import date

from sqlalchemy.orm import Session

from backend.modules.notificaciones import services
from backend.modules.notificaciones.models import NotificacionLog
from backend.modules.tareas.registro import FalloTarea, registrar_tarea

USUARIO = "programador@sistema"


def saludos_de_cumpleanos(db: Session) -> str:
    if not services._proceso_lock.acquire(blocking=False):
        return "Ya había un envío de cumpleaños en curso (pedido a mano): se omite"
    hoy = date.today()  # la misma fecha que usa el proceso
    services.NotificacionService._procesar_cumpleanos(USUARIO)  # libera _proceso_lock al terminar
    logs = (
        db.query(NotificacionLog)
        .filter(
            NotificacionLog.tipo == services.TIPO_CUMPLEANOS,
            NotificacionLog.fecha_evento == hoy,
            NotificacionLog.deleted_at.is_(None),
        )
        .all()
    )
    errores = [log for log in logs if log.estado == "error"]
    if errores:
        detalle = "; ".join(f"{log.empleado_nombre}: {log.error_detalle or 'sin detalle'}" for log in errores[:10])
        raise FalloTarea(f"{len(errores)} saludo(s) no salieron: {detalle}")
    enviados = sum(1 for log in logs if log.estado == "enviado")
    return f"{enviados} saludo(s) enviado(s) hoy" if enviados else "Sin cumpleañeros hoy"


def refrescar_token_lector(db: Session) -> str:
    from backend.core import webex_oauth

    if not webex_oauth.estado(db)["conectado"]:
        return "No hay cuenta lectora de Webex conectada: se omite"
    try:
        fila = webex_oauth.refresh(db)
    except webex_oauth.WebexOAuthError as exc:
        raise FalloTarea(f"No se pudo refrescar el token lector de Webex: {exc}")
    return f"Token refrescado (vence el {fila.expires_at:%d/%m/%Y %H:%M} UTC)"


registrar_tarea(
    codigo="cumpleanos",
    nombre="Saludos de cumpleaños",
    modulo="Notificaciones",
    funcion=saludos_de_cumpleanos,
    descripcion="Manda la card de cumpleaños al room de Webex configurado.",
    horario_default="09:00",
    activa_default=True,
)
registrar_tarea(
    codigo="webex_refresh_token_lector",
    nombre="Refresco del token lector de Webex",
    modulo="Notificaciones",
    funcion=refrescar_token_lector,
    descripcion="Refresca el token de la cuenta lectora de Webex.",
    horario_default="05:00",
    activa_default=True,
)
