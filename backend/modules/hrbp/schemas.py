"""
Schemas HRBP - Validaciones Pydantic
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# === ITEM TIPO ===
class ItemTipoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    stock_actual: int = Field(0, ge=0)
    stock_minimo: int = Field(0, ge=0)


class ItemTipoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    stock_actual: Optional[int] = Field(None, ge=0)
    stock_minimo: Optional[int] = Field(None, ge=0)


class ItemTipoResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str] = None
    stock_actual: int
    stock_minimo: int
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class ItemTipoList(BaseModel):
    items: List[ItemTipoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# === ENTREGA ===
class EntregaCreate(BaseModel):
    item_tipo_id: str
    empleado_id: str
    cantidad: int = Field(1, ge=1)
    observaciones: Optional[str] = None
    fecha_entrega: Optional[datetime] = None


class EntregaUpdate(BaseModel):
    observaciones: Optional[str] = None


class EmpleadoSimple(BaseModel):
    id: str
    nombre: str
    apellido: str
    codigo: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class UsuarioSimple(BaseModel):
    id: str
    nombre: str
    apellido: str
    email: str

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EntregaResponse(BaseModel):
    id: str
    item_tipo_id: str
    item_tipo: Optional[ItemTipoResponse] = None
    empleado_id: str
    empleado: Optional[EmpleadoSimple] = None
    hrbp_usuario_id: str
    hrbp_usuario: Optional[UsuarioSimple] = None
    cantidad: int
    observaciones: Optional[str] = None
    fecha_entrega: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "item_tipo_id", "empleado_id", "hrbp_usuario_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EntregaList(BaseModel):
    items: List[EntregaResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# === AJUSTE STOCK ===
class AjusteStockCreate(BaseModel):
    cantidad: int = Field(..., description="Cantidad a agregar (positivo) o quitar (negativo)")
    motivo: Optional[str] = Field(None, max_length=255)
