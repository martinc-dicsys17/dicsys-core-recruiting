"""
Schemas Pydantic para el módulo LLM.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMRequestResponse(BaseModel):
    """Schema de respuesta de un registro de uso de LLM."""

    id: str
    modulo: str
    model_name: str
    periodo: str
    tokens_input: int
    tokens_output: int
    tokens_cache: int
    tokens_total: int
    costo_usd: Decimal
    request_file: Optional[str] = None
    response_file: Optional[str] = None
    status: str
    error_mensaje: Optional[str] = None
    latencia_ms: Optional[int] = None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class LLMRequestList(BaseModel):
    """Listado paginado de registros de LLM."""

    items: List[LLMRequestResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class LLMUsageModulo(BaseModel):
    """Uso agregado de un módulo dentro de un período."""

    modulo: str
    requests: int
    tokens_input: int
    tokens_output: int
    tokens_cache: int
    tokens_total: int
    costo_usd: Decimal


class LLMUsagePeriodo(BaseModel):
    """Uso agregado de un período (mes) con desglose por módulo."""

    periodo: str
    requests: int
    tokens_input: int
    tokens_output: int
    tokens_cache: int
    tokens_total: int
    costo_usd: Decimal
    modulos: List[LLMUsageModulo]


class LLMUsageResponse(BaseModel):
    """Resumen de uso por mes y módulo + totales globales."""

    periodos_disponibles: List[str] = Field(default_factory=list)
    periodos: List[LLMUsagePeriodo]
    total_requests: int
    total_tokens: int
    total_costo_usd: Decimal
