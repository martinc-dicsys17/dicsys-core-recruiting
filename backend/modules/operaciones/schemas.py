"""
Schemas Pydantic para el módulo de Operaciones - Equipos.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntegranteResponse(BaseModel):
    """Schema para mostrar un integrante del equipo."""

    id: str
    codigo: str
    apellido: str
    nombre: str

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class LiderResponse(BaseModel):
    """Schema para mostrar el líder del equipo."""

    id: str
    codigo: str
    apellido: str
    nombre: str

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EquipoCreate(BaseModel):
    """Schema para crear un equipo."""

    nombre: str = Field(..., min_length=2, max_length=100)
    cliente_id: Optional[str] = None
    lider_id: Optional[str] = None
    activo: bool = True
    integrantes_ids: List[str] = Field(default_factory=list)


class EquipoUpdate(BaseModel):
    """Schema para actualizar un equipo."""

    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    cliente_id: Optional[str] = None
    lider_id: Optional[str] = None
    activo: Optional[bool] = None
    integrantes_ids: Optional[List[str]] = None


class EquipoResponse(BaseModel):
    """Schema de respuesta para un equipo."""

    id: str
    nombre: str
    cliente_id: Optional[str] = None
    lider_id: Optional[str] = None
    lider: Optional[LiderResponse] = None
    activo: bool
    integrantes: List[IntegranteResponse] = []
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "cliente_id", "lider_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EquipoList(BaseModel):
    """Schema para listado paginado de equipos."""

    items: List[EquipoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
