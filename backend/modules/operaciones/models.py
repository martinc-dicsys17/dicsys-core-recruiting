"""
Modelos para el módulo de Operaciones - Equipos.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tabla intermedia para integrantes del equipo (muchos a muchos)
equipo_integrantes = Table(
    "operaciones_equipo_integrantes",
    Base.metadata,
    Column("equipo_id", UUID(as_uuid=True), ForeignKey("operaciones_equipos.id"), primary_key=True),
    Column("empleado_id", UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), primary_key=True),
    Column("created_at", DateTime, nullable=False, default=utc_now),
)


class Equipo(Base):
    """Modelo de Equipo de trabajo."""

    __tablename__ = "operaciones_equipos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)

    # Cliente (FK futura - por ahora nullable)
    cliente_id = Column(UUID(as_uuid=True), nullable=True)

    # Líder del equipo (FK a empleado)
    lider_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    # Estado: True = Activo, False = Inactivo
    activo = Column(Boolean, default=True, nullable=False)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    lider_rel = relationship("Empleado", foreign_keys=[lider_id])
    integrantes = relationship("Empleado", secondary=equipo_integrantes, backref="equipos_como_integrante")
