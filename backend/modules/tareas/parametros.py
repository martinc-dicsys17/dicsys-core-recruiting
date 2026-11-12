"""
Parámetros del motor de tareas (F19-P03, D-99), en Configuración → Parámetros.

- `alertas_webex_room_id`: el room de Webex donde caen las alertas de fallo.
- Por cada tarea registrada (no continua): `tarea_<codigo>_activa` y `tarea_<codigo>_horario`,
  en la categoría «Tareas programadas», con el horario en hora Argentina.

Migración (una sola vez, sin cambiar el horario real): los crons viejos guardaban la
hora del servidor, que en Docker es UTC. Si existe el parámetro viejo, el nuevo nace
con su valor pasado a hora Argentina (UTC − 3) y el viejo se da de baja.
"""

import logging
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.parametros.models import Parametro
from backend.modules.tareas.alertas import CLAVE_ROOM
from backend.modules.tareas.registro import TAREAS, clave_activa, clave_horario

logger = logging.getLogger(__name__)

CATEGORIA = "Tareas programadas"
USUARIO = "sistema@dicsys.com"

# tarea → (parámetro viejo de «activo», parámetro viejo de hora en UTC)
MIGRACIONES: Dict[str, Tuple[Optional[str], str]] = {
    "cumpleanos": ("notificaciones_cron_activo", "notificaciones_cron_hora"),
    "webex_refresh_token_lector": (None, "notificaciones_refresh_token_hora"),
    "sync_webex_membresias": ("sync_webex_cron_activo", "sync_webex_cron_hora"),
}


def _vigente(db: Session, key: str) -> Optional[Parametro]:
    return db.query(Parametro).filter(Parametro.key == key, Parametro.deleted_at.is_(None)).first()


def _existe(db: Session, key: str) -> bool:
    # Sin filtrar deleted_at, como el seed de Parámetros: si un admin lo borró, no se recrea
    return db.query(Parametro.id).filter(Parametro.key == key).first() is not None


def _valor(parametro: Parametro) -> str:
    return (parametro.valor if parametro.valor not in (None, "") else parametro.valor_default) or ""


def utc_a_argentina(hora: str) -> Optional[str]:
    """«12:00» (UTC) → «09:00» (Argentina). None si no es una hora."""
    try:
        hh, mm = str(hora).strip().split(":")
        return f"{(int(hh) - 3) % 24:02d}:{int(mm):02d}"
    except ValueError, AttributeError:
        return None


def _crear(db: Session, **campos) -> None:
    db.add(Parametro(categoria=CATEGORIA, updated_by=USUARIO, **campos))
    logger.info(f"⚙️ Parámetro creado: {campos['key']}")


def asegurar_parametros(db: Session) -> bool:
    """Crea los parámetros que falten (y migra los de los crons viejos). Idempotente."""
    hubo_cambios = False
    if not _existe(db, CLAVE_ROOM):
        _crear(
            db,
            subcategoria="Alertas",
            key=CLAVE_ROOM,
            nombre="Room de Webex para alertas de fallo",
            descripcion="ID del room de Webex donde llegan las alertas cuando una tarea programada falla o "
            "un envío agota los reintentos. Vacío: las alertas solo quedan en el log. El bot de "
            "Webex tiene que estar en el room (y en su equipo, si el room es de un equipo).",
            valor_default=None,
            valor=None,
        )
        hubo_cambios = True

    for tarea in TAREAS.values():
        if tarea.continua:
            continue
        clave_a, clave_h = clave_activa(tarea.codigo), clave_horario(tarea.codigo)
        if _existe(db, clave_a) and _existe(db, clave_h):
            continue
        viejo_activo, viejo_hora = MIGRACIONES.get(tarea.codigo, (None, None))
        activo = _vigente(db, viejo_activo) if viejo_activo else None
        hora = _vigente(db, viejo_hora) if viejo_hora else None
        valor_activa = _valor(activo) if activo else None
        valor_horario = utc_a_argentina(_valor(hora)) if hora else None

        if not _existe(db, clave_a):
            _crear(
                db,
                subcategoria=tarea.nombre,
                key=clave_a,
                nombre=f"{tarea.nombre}: activa",
                descripcion=f"1 para que «{tarea.nombre}» corra sola según su horario; 0 para solo a mano "
                f"(Configuración → Tareas programadas → Ejecutar ahora). {tarea.descripcion}".strip(),
                valor_default="1" if tarea.activa_default else "0",
                valor=valor_activa,
            )
        if not _existe(db, clave_h):
            _crear(
                db,
                subcategoria=tarea.nombre,
                key=clave_h,
                nombre=f"{tarea.nombre}: horario",
                descripcion="Hora Argentina. «09:00» todos los días, «L-V 09:00» de lunes a viernes o "
                "«cada 2h» cada N horas (1 a 24).",
                valor_default=tarea.horario_default,
                valor=valor_horario,
            )
        for viejo in (activo, hora):
            if viejo is not None:
                viejo.deleted_at, viejo.updated_by = utc_now(), f"{USUARIO} (migrado a {CATEGORIA})"
                logger.info(f"⚙️ Parámetro {viejo.key} migrado a «{CATEGORIA}» y dado de baja")
        hubo_cambios = True

    if hubo_cambios:
        db.commit()
    return hubo_cambios
