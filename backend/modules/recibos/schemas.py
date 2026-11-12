"""
Schemas Pydantic para el módulo de Recibos de Sueldo.
"""

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Lote de Recibos ─────────────────────────────────────────────────────────


class LoteReciboCreate(BaseModel):
    """Schema para crear un lote de recibos."""

    periodo: str = Field(..., min_length=7, max_length=7)
    tipo_liquidacion: str = Field(..., min_length=1, max_length=50)

    @field_validator("periodo")
    @classmethod
    def validar_periodo(cls, v):
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError("El período debe tener formato YYYY-MM (ej: 2024-06)")
        return v


class LoteReciboResponse(BaseModel):
    """Schema de respuesta de lote de recibos."""

    id: str
    empresa_id: str
    periodo: str
    tipo_liquidacion: str
    estado: str
    archivo_original: str
    archivo_nombre: str
    total_paginas: Optional[int] = None
    total_recibos: Optional[int] = None
    total_firmados: Optional[int] = None
    total_errores: Optional[int] = None
    errores_detalle: Optional[list] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    @field_validator("id", "empresa_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class LoteReciboList(BaseModel):
    """Schema para listado paginado de lotes."""

    items: List[LoteReciboResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ─── Recibo Individual ───────────────────────────────────────────────────────


class ReciboResponse(BaseModel):
    """Schema de respuesta de recibo individual."""

    id: str
    empresa_id: str
    lote_id: str
    empleado_id: Optional[str] = None
    empleado_nombre: Optional[str] = None
    cuil_extraido: int
    archivo_original: str
    archivo_duplicado: Optional[str] = None
    archivo_firmado: Optional[str] = None
    estado: str
    pagina_original: int
    pagina_duplicado: Optional[int] = None
    fecha_firma: Optional[datetime] = None
    ip_firma: Optional[str] = None
    periodo: Optional[str] = None
    tipo_liquidacion: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    @field_validator("id", "empresa_id", "lote_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("empleado_id", mode="before")
    @classmethod
    def convert_empleado_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @classmethod
    def from_model(cls, recibo, empleado_nombre_override: str = None) -> "ReciboResponse":
        """Convierte modelo a response con nombre de empleado y datos del lote."""
        empleado_nombre = empleado_nombre_override
        if not empleado_nombre:
            emp_rel = getattr(recibo, "empleado_rel", None)
            if emp_rel:
                empleado_nombre = emp_rel.empleado_nombre_completo

        periodo = None
        tipo_liquidacion = None
        lote = getattr(recibo, "lote_rel", None)
        if lote:
            periodo = lote.periodo
            tipo_liquidacion = lote.tipo_liquidacion

        return cls(
            id=str(recibo.id),
            empresa_id=str(recibo.empresa_id),
            lote_id=str(recibo.lote_id),
            empleado_id=str(recibo.empleado_id) if recibo.empleado_id else None,
            empleado_nombre=empleado_nombre,
            cuil_extraido=recibo.cuil_extraido,
            archivo_original=recibo.archivo_original,
            archivo_duplicado=recibo.archivo_duplicado,
            archivo_firmado=recibo.archivo_firmado,
            estado=recibo.estado,
            pagina_original=recibo.pagina_original,
            pagina_duplicado=recibo.pagina_duplicado,
            fecha_firma=recibo.fecha_firma,
            ip_firma=recibo.ip_firma,
            periodo=periodo,
            tipo_liquidacion=tipo_liquidacion,
            created_at=recibo.created_at,
            updated_at=recibo.updated_at,
            updated_by=recibo.updated_by,
        )

    model_config = ConfigDict(from_attributes=True)


class ReciboList(BaseModel):
    """Schema para listado paginado de recibos."""

    items: List[ReciboResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ─── Log de Recibo ───────────────────────────────────────────────────────────


class ReciboLogResponse(BaseModel):
    """Schema de respuesta de un log de actividad de recibo."""

    id: str
    recibo_id: str
    accion: str
    usuario_email: Optional[str] = None
    usuario_nombre: Optional[str] = None
    ip: Optional[str] = None
    detalle: Optional[str] = None
    created_at: datetime

    @field_validator("id", "recibo_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)
