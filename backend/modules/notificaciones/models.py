"""
Modelos para el módulo de Notificaciones.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class NotificacionLog(Base):
    """
    Log de notificaciones enviadas (o intentadas).
    Una fila por persona/evento: permite revisar con check qué se envió
    y el detalle del error cuando falló. También actúa como registro de
    idempotencia: si ya existe una fila 'enviado' para el empleado y la
    fecha del evento, no se vuelve a notificar.
    """

    __tablename__ = "notificaciones_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), nullable=True)

    tipo = Column(String(50), nullable=False, default="cumpleanos", index=True)
    fecha_evento = Column(Date, nullable=False, index=True)

    # Destinatario
    empleado_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    empleado_nombre = Column(String(255), nullable=True)
    empleado_email = Column(String(255), nullable=True)

    # Estado del envío: pendiente | procesando | enviado | error
    estado = Column(String(20), nullable=False, default="pendiente", index=True)

    # Contenido
    contexto_presentacion = Column(Text, nullable=True)  # Mensajes del canal de presentaciones usados como contexto
    mensaje_generado = Column(Text, nullable=True)  # Texto generado por la LLM
    llm_request_id = Column(String(64), nullable=True)  # FK lógica a core_llm_requests
    webex_message_id = Column(String(255), nullable=True)

    # Resultado
    error_detalle = Column(Text, nullable=True)
    enviado_at = Column(DateTime, nullable=True)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class WebexOAuthToken(Base):
    """
    Tokens OAuth de la integración "lectora" de Webex.
    Los bots no pueden leer el historial de salas grupales, por eso la lectura
    del canal de presentaciones usa los tokens de una cuenta de usuario
    (miembro de la sala) autorizada vía OAuth. Una fila por propósito.
    """

    __tablename__ = "core_webex_oauth_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposito = Column(String(50), nullable=False, unique=True, default="reader")

    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # vencimiento del access token (~14 días)
    refresh_expires_at = Column(
        DateTime, nullable=True
    )  # vencimiento del refresh token (~90 días, se renueva al usarlo)

    # Cuenta de Webex conectada (informativo, para mostrar en la UI)
    account_email = Column(String(255), nullable=True)
    account_nombre = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)
