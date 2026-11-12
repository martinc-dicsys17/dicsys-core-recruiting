"""
Tablas del motor de tareas (F19).

- core_tareas_corridas: cada ejecución de una tarea (programada o manual) con su
  resultado o su error. Es el historial común y de ahí salen las alertas.
- core_envios: la cola de envíos (mail y Webex) que el motor despacha en orden.
"""

import uuid

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.core.utils import utc_now
from backend.database import Base

DISPAROS = ("programado", "manual")
ESTADOS_CORRIDA = ("pendiente", "en_curso", "ok", "error")
CANALES = ("email", "webex_personal", "webex_room")
ESTADOS_ENVIO = ("pendiente", "enviado", "error")


def _en(columna: str, valores) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


class TareaCorrida(Base):
    """Una ejecución de una tarea programada (o pedida a mano)."""

    __tablename__ = "core_tareas_corridas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tarea = Column(String(100), nullable=False)  # código registrado
    disparo = Column(String(20), nullable=False, default="programado")
    estado = Column(String(20), nullable=False, default="pendiente")
    solicitada_por = Column(String(255), nullable=True)  # email de quien la pidió a mano
    creada_at = Column(DateTime, nullable=False, default=utc_now)  # UTC naive, como el resto
    inicio = Column(DateTime, nullable=True)
    fin = Column(DateTime, nullable=True)
    resultado = Column(Text, nullable=True)  # resumen legible de lo que hizo
    error = Column(Text, nullable=True)
    alerta_enviada = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(_en("disparo", DISPAROS), name="ck_core_tareas_corridas_disparo"),
        CheckConstraint(_en("estado", ESTADOS_CORRIDA), name="ck_core_tareas_corridas_estado"),
        Index("ix_core_tareas_corridas_tarea", "tarea", "creada_at"),
        Index("ix_core_tareas_corridas_estado", "estado"),
    )


class Envio(Base):
    """Un mensaje en la cola: mail, Webex a una persona o Webex a un room."""

    __tablename__ = "core_envios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    origen = Column(String(100), nullable=False)  # código de la tarea o del módulo que lo encoló
    canal = Column(String(20), nullable=False)
    destino = Column(String(255), nullable=False)  # mail, mail de Webex o ID del room
    asunto = Column(String(300), nullable=True)
    # email: {html, cc}; webex: {card, texto} o {texto, markdown}
    contenido = Column(JSONB, nullable=False)
    clave = Column(String(300), nullable=True)  # sin duplicados: la misma clave no se encola dos veces
    referencia = Column(String(120), nullable=True)  # «tipo:id» para avisarle al módulo el resultado
    estado = Column(String(20), nullable=False, default="pendiente")
    intentos = Column(Integer, nullable=False, default=0)
    proximo_intento_at = Column(DateTime, nullable=False, default=utc_now)
    error = Column(Text, nullable=True)
    enviado_at = Column(DateTime, nullable=True)
    creada_at = Column(DateTime, nullable=False, default=utc_now)
    alerta_enviada = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(_en("canal", CANALES), name="ck_core_envios_canal"),
        CheckConstraint(_en("estado", ESTADOS_ENVIO), name="ck_core_envios_estado"),
        Index("ix_core_envios_pendientes", "estado", "proximo_intento_at"),
        Index("uq_core_envios_clave", "clave", unique=True, postgresql_where=text("clave IS NOT NULL")),
    )
