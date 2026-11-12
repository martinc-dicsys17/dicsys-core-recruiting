"""
Schemas Pydantic para el módulo Parámetros.
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.paginacion import Pagina

KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]*$")


class ParametroBase(BaseModel):
    """Campos comunes de un parámetro."""

    categoria: str = Field(..., min_length=1, max_length=100)
    subcategoria: Optional[str] = Field(None, max_length=100)
    nombre: str = Field(..., min_length=1, max_length=200)
    key: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = None
    valor_default: Optional[str] = None
    valor: Optional[str] = None

    @field_validator("categoria", "subcategoria", "nombre", "descripcion", "valor_default", "valor", mode="before")
    @classmethod
    def limpiar_strings(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("key", mode="before")
    @classmethod
    def validar_key(cls, v):
        if not isinstance(v, str):
            raise ValueError("debe ser texto")
        v = v.strip().lower()
        if not v or not KEY_PATTERN.match(v):
            raise ValueError(
                "solo se permiten minúsculas, números, guiones, puntos y guiones bajos (ej: webex_room_birthdate_id)"
            )
        return v


class ParametroCreate(ParametroBase):
    """Schema para crear un parámetro."""

    pass


class ParametroUpdate(ParametroBase):
    """Schema para editar la definición de un parámetro."""

    pass


class ParametroValorUpdate(BaseModel):
    """Schema para editar solo el valor desde la UI principal."""

    valor: Optional[str] = None

    @field_validator("valor", mode="before")
    @classmethod
    def limpiar_valor(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v


class ParametroResponse(BaseModel):
    """Schema de respuesta de un parámetro."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    categoria: str
    subcategoria: Optional[str] = None
    nombre: str
    key: str
    descripcion: Optional[str] = None
    valor_default: Optional[str] = None
    valor: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class ParametroList(Pagina[ParametroResponse]):
    """Listado de parámetros, con las categorías existentes para el filtro."""

    categorias: List[str] = Field(default_factory=list)


class WebexRoom(BaseModel):
    id: str
    nombre: Optional[str] = None


class WebexRooms(BaseModel):
    """Espacios del team de Webex. Si Webex falla, success=False con el error y la UI cae a la selección actual."""

    success: bool
    rooms: List[WebexRoom] = Field(default_factory=list)
    error: Optional[str] = None


class Mensaje(BaseModel):
    message: str
