"""
Modelos para el módulo de Innovación - Gestión de Licencias.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

MONEDA_DEFAULT = "ARS"
MONEDAS_VALIDAS = ("ARS", "USD")


class Proveedor(Base):
    """Catalogo de proveedores (OpenAI, Microsoft, Atlassian).

    Tabla propia y no texto en la herramienta: con texto libre el filtro por
    proveedor repetiria los duplicados que estamos evitando.
    """

    __tablename__ = "innovacion_proveedores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    nombre = Column(String(150), nullable=False)
    nombre_normalizado = Column(String(150), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (
        Index(
            "uq_proveedor_empresa_nombre",
            "empresa_id",
            "nombre_normalizado",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Herramienta(Base):
    """Catalogo de herramientas licenciables (ChatGPT Pro, Jira, Microsoft 365)."""

    __tablename__ = "innovacion_herramientas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    nombre = Column(String(150), nullable=False)
    # Plegado del nombre: sostiene el unique por empresa.
    nombre_normalizado = Column(String(150), nullable=False)
    # Opcional: una herramienta puede no tener proveedor declarado.
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("innovacion_proveedores.id"), nullable=True)

    # Precio de lista. La licencia puede pisarlo con el negociado por asiento.
    costo_referencia = Column(Numeric(10, 2), nullable=True)
    moneda = Column(String(3), nullable=False, default=MONEDA_DEFAULT)

    # Baja logica del catalogo: la saca del select sin tocar el historico.
    activo = Column(Boolean, nullable=False, default=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    proveedor_rel = relationship("Proveedor", foreign_keys=[proveedor_id])

    __table_args__ = (
        Index(
            "uq_herramienta_empresa_nombre",
            "empresa_id",
            "nombre_normalizado",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    @property
    def proveedor_nombre(self) -> str | None:
        """Nombre del proveedor, o None si la herramienta no declara uno."""
        return self.proveedor_rel.nombre if self.proveedor_rel else None


class Licencia(Base):
    """Modelo de Licencia de herramienta/software."""

    __tablename__ = "innovacion_licencias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    # Datos de la licencia
    herramienta_id = Column(UUID(as_uuid=True), ForeignKey("innovacion_herramientas.id"), nullable=False)
    nro_pedido_compra = Column(String(50), nullable=True)  # Opcional
    costo_mensual = Column(Numeric(10, 2), nullable=True)  # Costo mensual
    moneda = Column(String(3), nullable=False, default=MONEDA_DEFAULT)

    # Fechas
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=True)  # Puede ser null si es indefinida

    # Sin circuito de aprobacion: la licencia esta activa o no lo esta.
    activa = Column(Boolean, nullable=False, default=True)

    # Empleado asignado
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    empleado_rel = relationship("Empleado", foreign_keys=[empleado_id])
    herramienta_rel = relationship("Herramienta", foreign_keys=[herramienta_id])

    @property
    def esta_vencida(self) -> bool:
        """Verifica si la licencia está vencida."""
        if not self.fecha_fin:
            return False
        return self.fecha_fin < date.today()
