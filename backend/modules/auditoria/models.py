"""
Modelo de Auditoría — registra cada navegación de usuario.
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class AuditoriaLog(Base):
    """Log de navegación: una fila por cada pantalla visitada por un usuario."""

    __tablename__ = "core_auditoria_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)

    fecha_hora = Column(DateTime, nullable=False, default=utc_now, index=True)
    modulo = Column(String(100), nullable=False, index=True)
    ruta = Column(String(500), nullable=False)
    metodo = Column(String(10), nullable=False, default="GET")
    email_usuario = Column(String(255), nullable=False, index=True)

    # Soft delete y auditoría base (norma del proyecto)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_auditoria_log_empresa_fecha", "empresa_id", "fecha_hora"),
        Index("ix_auditoria_log_empresa_email", "empresa_id", "email_usuario"),
        Index("ix_auditoria_log_empresa_modulo", "empresa_id", "modulo"),
    )
