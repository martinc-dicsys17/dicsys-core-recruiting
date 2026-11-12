"""
Modelos para el sistema de menús con permisos.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tabla intermedia: permisos de grupo sobre menús
grupo_menu = Table(
    "core_grupo_menu",
    Base.metadata,
    Column("grupo_id", UUID(as_uuid=True), ForeignKey("core_grupos.id"), primary_key=True),
    Column("menu_id", UUID(as_uuid=True), ForeignKey("core_menus.id"), primary_key=True),
    Column("puede_ver", Boolean, default=True),
    Column("puede_acceder", Boolean, default=True),
    Column("created_at", DateTime, default=utc_now),
)


class Menu(Base):
    """Menú principal del sistema."""

    __tablename__ = "core_menus"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(50), unique=True, nullable=False)  # ej: 'administracion', 'nomina'
    nombre = Column(String(100), nullable=False)
    icono = Column(String(50), nullable=True)  # nombre del icono lucide
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relaciones
    items = relationship("MenuItem", back_populates="menu", cascade="all, delete-orphan", lazy="joined")
    grupos = relationship("Grupo", secondary=grupo_menu, backref="menus_permitidos")


class MenuItem(Base):
    """Item de submenú."""

    __tablename__ = "core_menu_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id = Column(UUID(as_uuid=True), ForeignKey("core_menus.id"), nullable=False)
    codigo = Column(String(50), nullable=False)  # ej: 'usuarios', 'roles'
    nombre = Column(String(100), nullable=False)
    icono = Column(String(50), nullable=True)
    ruta = Column(String(200), nullable=True)  # ej: 'usuarios.list'
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relación
    menu = relationship("Menu", back_populates="items")
