"""
Schemas Pydantic del módulo de Auditoría.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuditoriaLogCreate(BaseModel):
    """Payload para registrar una navegación."""

    modulo: str = Field(..., min_length=1, max_length=100)
    ruta: str = Field(..., min_length=1, max_length=500)
    metodo: str = Field("GET", max_length=10)
    email_usuario: str = Field(..., min_length=3, max_length=255)
    fecha_hora: Optional[datetime] = None  # default = now en el service


class AuditoriaLogResponse(BaseModel):
    """Respuesta al cliente."""

    id: str
    fecha_hora: datetime
    modulo: str
    ruta: str
    metodo: str
    email_usuario: str

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class AuditoriaLogList(BaseModel):
    """Listado paginado."""

    items: List[AuditoriaLogResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
