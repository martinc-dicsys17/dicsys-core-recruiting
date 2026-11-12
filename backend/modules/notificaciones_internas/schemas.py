"""Schemas de la bandeja de notificaciones internas."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class NotificacionInternaResponse(BaseModel):
    id: str
    tipo: str
    titulo: str
    mensaje: str
    enlace: Optional[str] = None
    origen: Optional[str] = None
    leida_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def serializar_uuid(cls, value):
        return str(value) if isinstance(value, uuid.UUID) else value

    model_config = ConfigDict(from_attributes=True)


class NotificacionInternaList(BaseModel):
    items: List[NotificacionInternaResponse]
    total_no_leidas: int


class NotificacionInternaConteo(BaseModel):
    total_no_leidas: int


class NotificacionInternaHistorial(BaseModel):
    items: List[NotificacionInternaResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class NotificacionInternaAuditoriaItem(NotificacionInternaResponse):
    usuario_email: str
    usuario_nombre: str


class NotificacionInternaAuditoria(BaseModel):
    items: List[NotificacionInternaAuditoriaItem]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
