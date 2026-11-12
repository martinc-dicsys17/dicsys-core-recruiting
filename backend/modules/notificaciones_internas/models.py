"""Modelo persistente de la bandeja interna."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class NotificacionInterna(Base):
    """Mensaje interno mostrado en la bandeja personal de un usuario."""

    __tablename__ = "core_notificaciones_internas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=False)

    tipo = Column(String(30), nullable=False, default="info")
    titulo = Column(String(160), nullable=False)
    mensaje = Column(Text, nullable=False)
    enlace = Column(String(500), nullable=True)
    origen = Column(String(100), nullable=True)

    leida_at = Column(DateTime, nullable=True, default=None)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        Index(
            "ix_notificaciones_internas_usuario_bandeja_v2",
            "empresa_id",
            "usuario_id",
            "deleted_at",
            "leida_at",
            "created_at",
        ),
    )
