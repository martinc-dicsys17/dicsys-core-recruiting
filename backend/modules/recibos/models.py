"""
Modelos para el módulo de Recibos de Sueldo.

Tablas:
- recibos_lotes: Lotes de recibos cargados desde PDF masivo
- recibos_recibos: Recibos individuales extraídos de cada lote
"""

import uuid

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base


class LoteRecibo(Base):
    """Modelo de Lote de Recibos de Sueldo."""

    __tablename__ = "recibos_lotes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    periodo = Column(String(7), nullable=False)  # Formato YYYY-MM
    tipo_liquidacion = Column(String(50), nullable=False)
    estado = Column(String(30), nullable=False, default="pendiente")
    archivo_original = Column(String(500), nullable=False)
    archivo_nombre = Column(String(255), nullable=False)
    total_paginas = Column(Integer, nullable=True)
    total_recibos = Column(Integer, nullable=True)
    total_errores = Column(Integer, nullable=True)
    errores_detalle = Column(JSON, nullable=True)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    recibos = relationship("Recibo", back_populates="lote_rel", foreign_keys="Recibo.lote_id")


class Recibo(Base):
    """Modelo de Recibo individual extraído de un lote."""

    __tablename__ = "recibos_recibos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    lote_id = Column(UUID(as_uuid=True), ForeignKey("recibos_lotes.id"), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)
    cuil_extraido = Column(BigInteger, nullable=False)
    archivo_original = Column(String(500), nullable=False)
    # El duplicado es opcional: hay recibos que vienen en una sola hoja, con la
    # firma del empleador ya estampada y el espacio para la del empleado, así que
    # no hay una segunda página que guardar.
    archivo_duplicado = Column(String(500), nullable=True)
    archivo_firmado = Column(String(500), nullable=True)
    estado = Column(String(20), nullable=False)  # asignado, sin_asignar, firmado
    pagina_original = Column(Integer, nullable=False)
    pagina_duplicado = Column(Integer, nullable=True)
    fecha_firma = Column(DateTime, nullable=True)
    ip_firma = Column(String(45), nullable=True)  # IPv4 o IPv6

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    lote_rel = relationship("LoteRecibo", back_populates="recibos", foreign_keys=[lote_id])
    empleado_rel = relationship("Empleado", foreign_keys=[empleado_id])
    logs = relationship(
        "ReciboLog",
        back_populates="recibo_rel",
        foreign_keys="ReciboLog.recibo_id",
        order_by="ReciboLog.created_at.desc()",
    )


class ReciboLog(Base):
    """Log de actividad de un recibo (auditoría)."""

    __tablename__ = "recibos_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recibo_id = Column(UUID(as_uuid=True), ForeignKey("recibos_recibos.id"), nullable=False)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    accion = Column(
        String(50), nullable=False
    )  # creacion, descarga_original, descarga_duplicado, descarga_firmado, firma, reversion_firma
    usuario_email = Column(String(255), nullable=True)
    usuario_nombre = Column(String(200), nullable=True)
    ip = Column(String(45), nullable=True)
    detalle = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    # Relaciones
    recibo_rel = relationship("Recibo", back_populates="logs", foreign_keys=[recibo_id])
