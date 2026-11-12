"""
Modelos para el módulo de Clientes.
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tabla M2M: cliente <-> categoría
cliente_categoria = Table(
    "admin_cliente_categoria",
    Base.metadata,
    Column("cliente_id", UUID(as_uuid=True), ForeignKey("admin_clientes.id"), primary_key=True),
    Column("categoria_id", UUID(as_uuid=True), ForeignKey("admin_categorias_cliente.id"), primary_key=True),
    Column("created_at", DateTime, default=utc_now),
)


class CategoriaCliente(Base):
    """Categoría de cliente (configurable)."""

    __tablename__ = "admin_categorias_cliente"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    clientes = relationship("Cliente", secondary=cliente_categoria, back_populates="categorias")


class Cliente(Base):
    """Modelo de Cliente."""

    __tablename__ = "admin_clientes"

    TIPOS = ["Individual", "Empresa"]
    RESPONSABILIDADES = [
        "Responsable Inscripto",
        "Sujeto Exento",
        "Consumidor Final",
        "Responsable Monotributo",
        "Cliente del Exterior",
        "Sujeto No Categorizado",
    ]

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # Individual | Empresa
    cuit = Column(String(13), nullable=False, index=True)  # XX-XXXXXXXX-X
    razon_social = Column(String(200), nullable=False)
    nombre_fantasia = Column(String(200), nullable=True)
    responsabilidad_afip = Column(String(50), nullable=False)
    sitio_web = Column(String(255), nullable=True)
    logo = Column(String(500), nullable=True)  # URL relativa del logo
    activo = Column(Boolean, default=True, nullable=False)
    observaciones = Column(Text, nullable=True)

    # Datos fiscales
    nro_ingresos_brutos = Column(String(50), nullable=True)
    fecha_inicio_actividades = Column(Date, nullable=True)
    nro_inscripcion_municipal = Column(String(50), nullable=True)
    regimen_retencion = Column(String(100), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    domicilios = relationship("ClienteDomicilio", back_populates="cliente", cascade="all, delete-orphan")
    categorias = relationship("CategoriaCliente", secondary=cliente_categoria, back_populates="clientes")


class ClienteDomicilio(Base):
    """Domicilio de facturación de un cliente (historial)."""

    __tablename__ = "admin_cliente_domicilios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("admin_clientes.id"), nullable=False)

    calle = Column(String(200), nullable=False)
    numero = Column(String(20), nullable=True)
    piso = Column(String(20), nullable=True)
    departamento = Column(String(20), nullable=True)
    localidad = Column(String(100), nullable=False)
    provincia = Column(String(100), nullable=False)
    pais = Column(String(100), nullable=False, default="Argentina")
    codigo_postal = Column(String(10), nullable=True)
    vigente = Column(Boolean, default=True, nullable=False)  # Solo uno activo a la vez

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    cliente = relationship("Cliente", back_populates="domicilios")
