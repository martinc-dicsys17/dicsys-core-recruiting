"""
Schemas para permisos y grupos.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GrupoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)


class GrupoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    activo: Optional[bool] = None


class PermisoModuloSchema(BaseModel):
    modulo: str
    tiene_acceso: bool
    model_config = ConfigDict(from_attributes=True)


class GrupoResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str] = None
    activo: bool
    created_at: datetime
    permisos: List[PermisoModuloSchema] = []
    model_config = ConfigDict(from_attributes=True)


class GrupoListResponse(BaseModel):
    grupos: List[GrupoResponse]
    total: int


class AsignarPermisosRequest(BaseModel):
    """Asignar permisos de módulos a un grupo."""

    permisos: List[PermisoModuloSchema]


class AsignarUsuariosRequest(BaseModel):
    """Asignar usuarios a un grupo."""

    usuario_ids: List[str]


class UsuarioGrupoResponse(BaseModel):
    id: str
    email: str
    nombre: str
    apellido: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ModuloDisponible(BaseModel):
    codigo: str
    nombre: str


class SubmoduloDisponible(BaseModel):
    codigo: str
    nombre: str
    icono: Optional[str] = None
    padre: Optional[str] = None  # código del ítem padre (tercer nivel del sidebar)


class ModuloConSubmodulos(BaseModel):
    codigo: str
    nombre: str
    icono: Optional[str] = None
    items: List[SubmoduloDisponible] = []
