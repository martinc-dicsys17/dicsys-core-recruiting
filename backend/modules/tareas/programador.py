"""
Programador único (F19-P01, D-98).

Un solo loop por proceso. Entre los workers de uvicorn, uno solo es el líder: el que
tiene el advisory lock de Postgres en una conexión que mantiene abierta (si ese
proceso muere, la conexión se cierra, el candado se libera y otro toma la posta).

En cada vuelta el líder:
  1. corre las corridas pedidas a mano (quedan en estado `pendiente`);
  2. decide qué tareas programadas tocan (hora Argentina, según Parámetros);
  3. corre las tareas continuas (las que deciden solas, como los avisos de proveedores);
  4. despacha la cola de envíos, en orden.

Cada corrida de una tarea programada o manual va en un hilo de trabajo acotado
(MAX_HILOS) y una tarea nunca se superpone consigo misma: hay tareas largas (los
cumpleaños esperan minutos entre saludos) que no pueden frenar al resto.
"""

import logging
import threading
import time as reloj
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core import config
from backend.core.utils import utc_now
from backend.modules.tareas import alertas, cola
from backend.modules.tareas.models import TareaCorrida
from backend.modules.tareas.registro import (
    TAREAS,
    VERDADERO,
    FalloTarea,
    Tarea,
    a_argentina,
    ahora_argentina,
    clave_activa,
    clave_horario,
    parsear_horario,
    toca,
)

logger = logging.getLogger(__name__)

PG_LOCK_PROGRAMADOR = 982451700  # arbitrario pero estable
INTERVALO_SEGUNDOS = 20
INTERVALO_CONTINUAS = timedelta(seconds=60)
MAX_HILOS = 3
USUARIO = "programador@sistema"

_iniciado = threading.Lock()
_corriendo: Set[str] = set()  # tareas con una corrida en curso en este proceso
_corriendo_lock = threading.Lock()
_ultima_continua: Dict[str, datetime] = {}


# ─── Configuración de cada tarea (Parámetros) ───────────────────────────────────


def configuracion(db: Session, tarea: Tarea) -> Dict:
    """Si está activa, su horario y si el horario es válido, leídos de Parámetros."""
    if tarea.continua:
        return {"activa": True, "horario_texto": None, "horario": None, "horario_error": None}
    activa = str(config.get_parameter(clave_activa(tarea.codigo), "1" if tarea.activa_default else "0", db=db))
    horario_texto = str(config.get_parameter(clave_horario(tarea.codigo), tarea.horario_default, db=db) or "")
    try:
        horario, error = parsear_horario(horario_texto), None
    except ValueError as exc:
        horario, error = None, str(exc)
    return {
        "activa": activa.strip().lower() in VERDADERO,
        "horario_texto": horario_texto,
        "horario": horario,
        "horario_error": error,
    }


def parametros_listos(db: Session, tarea: Tarea) -> bool:
    """
    Una tarea programada solo corre si sus parámetros ya existen: hasta que el seed los
    crea (y migra los de los crons viejos) los defaults podrían prender algo que estaba
    apagado.
    """
    from backend.modules.parametros.models import Parametro

    return (
        db.query(Parametro.id)
        .filter(
            Parametro.key == clave_activa(tarea.codigo),
            Parametro.deleted_at.is_(None),
        )
        .first()
        is not None
    )


def ultima_programada(db: Session, codigo: str) -> Optional[datetime]:
    """Inicio de la última corrida programada, en hora Argentina (para decidir si toca)."""
    corrida = (
        db.query(TareaCorrida)
        .filter(
            TareaCorrida.tarea == codigo,
            TareaCorrida.disparo == "programado",
        )
        .order_by(TareaCorrida.creada_at.desc())
        .first()
    )
    return a_argentina(corrida.creada_at) if corrida else None


def en_curso(db: Session, codigo: str) -> bool:
    with _corriendo_lock:
        if codigo in _corriendo:
            return True
    return (
        db.query(TareaCorrida.id)
        .filter(
            TareaCorrida.tarea == codigo,
            TareaCorrida.estado.in_(("pendiente", "en_curso")),
        )
        .first()
        is not None
    )


# ─── Correr una tarea ───────────────────────────────────────────────────────────


def correr(db: Session, corrida: TareaCorrida) -> TareaCorrida:
    """Corre la tarea de la corrida en esta sesión y registra el resultado (y la alerta si falló)."""
    tarea = TAREAS.get(corrida.tarea)
    corrida.estado, corrida.inicio = "en_curso", utc_now()
    db.commit()
    try:
        if tarea is None:
            raise FalloTarea(f"La tarea «{corrida.tarea}» ya no está registrada")
        resumen = tarea.funcion(db)
        corrida.estado, corrida.resultado = "ok", (resumen or "Sin novedades")[:4000]
    except Exception as exc:  # noqa: BLE001 - toda falla queda en la corrida y se alerta
        db.rollback()
        corrida = db.get(TareaCorrida, corrida.id)
        detalle = str(exc) if isinstance(exc, FalloTarea) else f"{exc.__class__.__name__}: {exc}"
        corrida.estado, corrida.error = "error", detalle[:4000]
        if not isinstance(exc, FalloTarea):
            logger.error(f"❌ La tarea {corrida.tarea} falló: {exc}", exc_info=True)
    corrida.fin = utc_now()
    db.commit()
    if corrida.estado == "error":
        alertas.alertar_corrida(db, corrida, tarea.nombre if tarea else corrida.tarea)
        db.commit()
    return corrida


def _correr_en_hilo(codigo: str, corrida_id) -> None:
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        corrida = db.get(TareaCorrida, corrida_id)
        if corrida is not None:
            correr(db, corrida)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"❌ Error corriendo la tarea {codigo}: {exc}", exc_info=True)
    finally:
        db.close()
        with _corriendo_lock:
            _corriendo.discard(codigo)


def _lanzar(db: Session, corrida: TareaCorrida, en_hilo: bool) -> None:
    if not en_hilo:
        correr(db, corrida)
        return
    with _corriendo_lock:
        _corriendo.add(corrida.tarea)
    threading.Thread(
        target=_correr_en_hilo, args=(corrida.tarea, corrida.id), daemon=True, name=f"tarea-{corrida.tarea}"
    ).start()


def _correr_continua(db: Session, tarea: Tarea, ahora: datetime) -> None:
    """Las continuas corren en la vuelta misma y solo dejan corrida si hicieron algo o fallaron."""
    ultima = _ultima_continua.get(tarea.codigo)
    if ultima is not None and ahora - ultima < INTERVALO_CONTINUAS:
        return
    _ultima_continua[tarea.codigo] = ahora
    inicio = utc_now()
    try:
        resumen = tarea.funcion(db)
        if resumen is None:
            return
        db.add(
            TareaCorrida(
                tarea=tarea.codigo,
                disparo="programado",
                estado="ok",
                inicio=inicio,
                fin=utc_now(),
                creada_at=inicio,
                resultado=resumen[:4000],
            )
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        detalle = str(exc) if isinstance(exc, FalloTarea) else f"{exc.__class__.__name__}: {exc}"
        corrida = TareaCorrida(
            tarea=tarea.codigo,
            disparo="programado",
            estado="error",
            inicio=inicio,
            fin=utc_now(),
            creada_at=inicio,
            error=detalle[:4000],
        )
        db.add(corrida)
        db.commit()
        alertas.alertar_corrida(db, corrida, tarea.nombre)
        db.commit()


# ─── Una vuelta ─────────────────────────────────────────────────────────────────


def vuelta(
    db: Session, ahora: Optional[datetime] = None, en_hilos: bool = True, despachar_cola: bool = True
) -> List[str]:
    """
    Una vuelta del programador. Devuelve los códigos de las tareas que lanzó.
    `en_hilos=False` corre todo en esta sesión (tests y ejecución sincrónica).
    """
    ahora = ahora or ahora_argentina()
    lanzadas: List[str] = []

    def hay_lugar() -> bool:
        with _corriendo_lock:
            return not en_hilos or len(_corriendo) < MAX_HILOS

    # 1. Corridas pedidas a mano
    for corrida in (
        db.query(TareaCorrida).filter(TareaCorrida.estado == "pendiente").order_by(TareaCorrida.creada_at).all()
    ):
        with _corriendo_lock:
            ocupada = corrida.tarea in _corriendo
        if ocupada or not hay_lugar():
            continue
        _lanzar(db, corrida, en_hilos)
        lanzadas.append(corrida.tarea)

    # 2. Programadas y 3. continuas
    for tarea in sorted(TAREAS.values(), key=lambda t: t.codigo):
        if tarea.continua:
            _correr_continua(db, tarea, ahora)
            continue
        if not parametros_listos(db, tarea):
            continue
        cfg = configuracion(db, tarea)
        if not cfg["activa"] or cfg["horario"] is None or en_curso(db, tarea.codigo):
            continue
        if not toca(cfg["horario"], ahora, ultima_programada(db, tarea.codigo)) or not hay_lugar():
            continue
        corrida = TareaCorrida(tarea=tarea.codigo, disparo="programado", estado="pendiente", solicitada_por=USUARIO)
        db.add(corrida)
        db.commit()
        _lanzar(db, corrida, en_hilos)
        lanzadas.append(tarea.codigo)

    # 4. Cola de envíos
    if despachar_cola:
        cola.despachar(db, pausar=en_hilos)
    return lanzadas


def marcar_interrumpidas(db: Session) -> int:
    """Al tomar el liderazgo: lo que quedó en curso lo cortó un reinicio. Se registra y se alerta."""
    corridas = db.query(TareaCorrida).filter(TareaCorrida.estado == "en_curso").all()
    for corrida in corridas:
        corrida.estado, corrida.fin = "error", utc_now()
        corrida.error = "Interrumpida: el backend se reinició mientras corría"
        db.commit()
        tarea = TAREAS.get(corrida.tarea)
        alertas.alertar_corrida(db, corrida, tarea.nombre if tarea else corrida.tarea)
        db.commit()
    return len(corridas)


# ─── Loop ───────────────────────────────────────────────────────────────────────


def iniciar_programador() -> None:
    """Arranca el loop (idempotente por proceso; llamar desde el lifespan)."""
    if not _iniciado.acquire(blocking=False):
        return
    threading.Thread(target=_loop, daemon=True, name="programador").start()


def _tomar_liderazgo(conexion_actual):
    """Devuelve la conexión que tiene el candado (la misma si ya era líder) o None."""
    from backend.database import engine

    if conexion_actual is not None:
        try:
            conexion_actual.execute(text("SELECT 1"))
            conexion_actual.commit()  # sin transacción abierta: el candado es de sesión y sigue tomado
            return conexion_actual
        except Exception:  # noqa: BLE001 - se perdió la conexión: se perdió el liderazgo
            try:
                conexion_actual.close()
            except Exception:  # noqa: BLE001
                pass
    conexion = engine.connect()
    if conexion.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": PG_LOCK_PROGRAMADOR}).scalar():
        conexion.commit()
        return conexion
    conexion.close()
    return None


def _loop() -> None:
    from backend.database import SessionLocal

    logger.info("⏰ Programador de tareas iniciado")
    conexion = None
    reloj.sleep(INTERVALO_SEGUNDOS)  # que los seeds terminen antes de la primera vuelta
    while True:
        try:
            era_lider = conexion is not None
            conexion = _tomar_liderazgo(conexion)
            if conexion is not None:
                db = SessionLocal()
                try:
                    if not era_lider:
                        logger.info("⏰ Este proceso es el líder del programador de tareas")
                        marcar_interrumpidas(db)
                    vuelta(db)
                finally:
                    db.close()
        except Exception as exc:  # noqa: BLE001 - el loop no se cae nunca
            logger.error(f"❌ Error en el programador de tareas: {exc}", exc_info=True)
        reloj.sleep(INTERVALO_SEGUNDOS)
