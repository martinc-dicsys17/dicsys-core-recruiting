"""
Modelos HRBP - Gestión de Entregas RRHH
"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base


class HRBPItemTipo(Base):
    """Tipos de items para entrega (Kit Ingreso, Gift Card, etc.)"""

    __tablename__ = "hrbp_item_tipos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    stock_actual = Column(Integer, nullable=False, default=0)
    stock_minimo = Column(Integer, nullable=False, default=0)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    entregas = relationship("HRBPEntrega", back_populates="item_tipo")


class HRBPEntrega(Base):
    """Registro de entregas de items a empleados"""

    __tablename__ = "hrbp_entregas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    # Relaciones
    item_tipo_id = Column(UUID(as_uuid=True), ForeignKey("hrbp_item_tipos.id"), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)
    hrbp_usuario_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=False)

    # Datos de la entrega
    cantidad = Column(Integer, nullable=False, default=1)
    observaciones = Column(Text, nullable=True)
    fecha_entrega = Column(DateTime, nullable=False, default=utc_now)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones ORM
    item_tipo = relationship("HRBPItemTipo", back_populates="entregas")
    empleado = relationship("Empleado", foreign_keys=[empleado_id])
    hrbp_usuario = relationship("Usuario", foreign_keys=[hrbp_usuario_id])
