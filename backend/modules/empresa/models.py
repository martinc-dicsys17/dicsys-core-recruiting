"""
Modelos para el módulo de Empresa.

Tablas:
- core_empresas: Datos maestros de empresa (CUIT, razón social, datos fiscales)
- core_empresa_domicilios: Domicilios de empresa (calle, localidad, provincia, etc.)
- core_usuario_empresa: Tabla de asociación M2M entre usuarios y empresas
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tabla de asociación M2M: usuario <-> empresa
core_usuario_empresa = Table(
    "core_usuario_empresa",
    Base.metadata,
    Column("usuario_id", UUID(as_uuid=True), ForeignKey("core_usuarios.id"), primary_key=True),
    Column("empresa_id", UUID(as_uuid=True), ForeignKey("core_empresas.id"), primary_key=True),
    Column("created_at", DateTime, default=utc_now),
)


class Empresa(Base):
    """Modelo de Empresa."""

    __tablename__ = "core_empresas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cuit = Column(String(13), nullable=False, index=True)
    razon_social = Column(String(200), nullable=False)
    nombre_fantasia = Column(String(200), nullable=True)
    responsabilidad_afip = Column(String(50), nullable=False)
    logo = Column(String(500), nullable=True)
    sitio_web = Column(String(255), nullable=True)
    telefono = Column(String(30), nullable=True)
    email_contacto = Column(String(255), nullable=True)
    observaciones = Column(Text, nullable=True)
    dominios_email = Column(Text, nullable=True)  # JSON: ["dicsys.com", "dicsys.com.ar"]
    activo = Column(Boolean, default=True, nullable=False)

    # Datos fiscales
    nro_ingresos_brutos = Column(String(50), nullable=True)
    fecha_inicio_actividades = Column(Date, nullable=True)
    nro_inscripcion_municipal = Column(String(50), nullable=True)
    regimen_retencion = Column(String(100), nullable=True)

    # Timestamps y soft delete
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    domicilios = relationship("EmpresaDomicilio", back_populates="empresa", cascade="all, delete-orphan")
    usuarios = relationship("Usuario", secondary=core_usuario_empresa, backref="empresas")


class EmpresaDomicilio(Base):
    """Modelo de Domicilio de Empresa."""

    __tablename__ = "core_empresa_domicilios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    calle = Column(String(200), nullable=False)
    numero = Column(String(20), nullable=True)
    piso = Column(String(20), nullable=True)
    departamento = Column(String(20), nullable=True)
    localidad = Column(String(100), nullable=False)
    provincia = Column(String(100), nullable=False)
    pais = Column(String(100), nullable=False, default="Argentina")
    codigo_postal = Column(String(10), nullable=True)
    vigente = Column(Boolean, nullable=False, default=True)

    # Timestamps y soft delete
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    empresa = relationship("Empresa", back_populates="domicilios")
