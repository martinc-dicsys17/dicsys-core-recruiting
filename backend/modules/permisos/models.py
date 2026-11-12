"""
Modelos para el sistema de permisos.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tabla intermedia: usuarios en grupos POR EMPRESA
usuario_grupo = Table(
    "core_usuario_grupo",
    Base.metadata,
    Column("usuario_id", UUID(as_uuid=True), ForeignKey("core_usuarios.id"), primary_key=True),
    Column("grupo_id", UUID(as_uuid=True), ForeignKey("core_grupos.id"), primary_key=True),
    Column("empresa_id", UUID(as_uuid=True), ForeignKey("core_empresas.id"), primary_key=True),
    Column("created_at", DateTime, default=utc_now),
)

# Tabla: grupos vinculados a departamentos POR EMPRESA
# Cuando un empleado es creado/actualizado en ese departamento, se auto-suscribe a estos grupos
grupo_departamento = Table(
    "core_grupo_departamento",
    Base.metadata,
    Column("grupo_id", UUID(as_uuid=True), ForeignKey("core_grupos.id"), primary_key=True),
    Column("departamento_id", UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"), primary_key=True),
    Column("empresa_id", UUID(as_uuid=True), ForeignKey("core_empresas.id"), primary_key=True),
    Column("created_at", DateTime, default=utc_now),
)


class Grupo(Base):
    """Grupo de usuarios."""

    __tablename__ = "core_grupos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), unique=True, nullable=False)
    descripcion = Column(String(255), nullable=True)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relaciones
    permisos = relationship("PermisoModulo", back_populates="grupo", cascade="all, delete-orphan")


class PermisoModulo(Base):
    """Permiso de acceso a un módulo para un grupo."""

    __tablename__ = "core_permisos_modulo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grupo_id = Column(UUID(as_uuid=True), ForeignKey("core_grupos.id"), nullable=False)
    modulo = Column(String(100), nullable=False)
    tiene_acceso = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relación
    grupo = relationship("Grupo", back_populates="permisos")
