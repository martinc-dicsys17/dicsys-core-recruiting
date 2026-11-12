"""
Modelos para el módulo Parámetros.

Tabla:
- core_parametros: parámetros de configuración del sistema, editables desde
  la UI de Configuración. Otros módulos los leen con config.get_parameter(key).
"""

import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class Parametro(Base):
    """Parámetro de configuración del sistema."""

    __tablename__ = "core_parametros"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    categoria = Column(String(100), nullable=False, index=True)
    subcategoria = Column(String(100), nullable=True)
    nombre = Column(String(200), nullable=False)

    # Identificador estable usado por config.get_parameter(key, default_value)
    key = Column(String(100), nullable=False, unique=True, index=True)

    descripcion = Column(Text, nullable=True)

    # valor_default: definido al crear el parámetro; valor: editable desde la UI.
    # get_parameter resuelve: valor → valor_default → default_value del caller.
    valor_default = Column(Text, nullable=True)
    valor = Column(Text, nullable=True)

    # Timestamps y soft delete
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)
