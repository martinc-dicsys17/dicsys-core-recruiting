"""
Modelos para el módulo LLM.

Tabla:
- core_llm_requests: registro de cada invocación a la LLM con conteo de
  tokens, costo calculado, módulo que la invocó y links al raw en disco.
"""

import uuid

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class LLMRequest(Base):
    """Registro de uso de la LLM."""

    __tablename__ = "core_llm_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Módulo que invocó la LLM (ej: 'soporte', 'recibos').
    modulo = Column(String(50), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)

    # Período yyyy-mm (desnormalizado para sumarizar rápido).
    periodo = Column(String(7), nullable=False, index=True)

    # Conteo de tokens devuelto por Gemini.
    tokens_input = Column(Integer, nullable=False, default=0)
    tokens_output = Column(Integer, nullable=False, default=0)
    tokens_cache = Column(Integer, nullable=False, default=0)
    tokens_total = Column(Integer, nullable=False, default=0)

    # Costo calculado en USD.
    costo_usd = Column(Numeric(12, 6), nullable=False, default=0)

    # Links al raw en disco (rutas relativas a llm_storage_path).
    request_file = Column(String(500), nullable=True)
    response_file = Column(String(500), nullable=True)

    status = Column(String(20), nullable=False, default="ok")
    error_mensaje = Column(Text, nullable=True)
    latencia_ms = Column(Integer, nullable=True)

    # Timestamps y soft delete.
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)
