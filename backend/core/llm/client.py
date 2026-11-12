"""
Cliente core para invocar LLMs (Google Gemini).

Provee `generate()`: una función reutilizable por cualquier módulo de
`backend/modules/` que:
  1. Genera un id de request.
  2. Guarda el raw request en disco.
  3. Llama a Gemini.
  4. Guarda el raw response en disco.
  5. Extrae el conteo de tokens (entrada/salida/cache/total).
  6. Calcula el costo en USD.
  7. Registra la fila en `core_llm_requests`.
  8. Devuelve un `LLMResult`.

El parámetro `modulo` es OBLIGATORIO para trazabilidad y sumarización.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.llm import logging_store
from backend.core.llm.pricing import calcular_costo

logger = logging.getLogger(__name__)

# Cliente perezoso (se instancia una sola vez).
_client = None


class LLMError(Exception):
    """Error al invocar la LLM."""


@dataclass
class LLMResult:
    """Resultado de una invocación a la LLM."""

    id: str
    modulo: str
    model_name: str
    text: str
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_cache: int = 0
    tokens_total: int = 0
    costo_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    latencia_ms: int = 0
    status: str = "ok"
    request_file: Optional[str] = None
    response_file: Optional[str] = None
    raw: Any = None


def _get_client():
    """Devuelve (e instancia si hace falta) el cliente de Gemini."""
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY no configurada")
        from google import genai  # import perezoso

        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _extraer_usage(response: Any) -> Dict[str, int]:
    """Extrae el conteo de tokens del usage_metadata de Gemini."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {"input": 0, "output": 0, "cache": 0, "total": 0}

    def _val(*names: str) -> int:
        for n in names:
            v = getattr(usage, n, None)
            if v:
                return int(v)
        return 0

    entrada = _val("prompt_token_count")
    salida = _val("candidates_token_count")
    cache = _val("cached_content_token_count")
    total = _val("total_token_count") or (entrada + salida)
    return {"input": entrada, "output": salida, "cache": cache, "total": total}


def _response_to_dict(response: Any) -> Any:
    """Convierte la response de Gemini a algo serializable a JSON."""
    for attr in ("model_dump", "to_dict", "dict"):
        metodo = getattr(response, attr, None)
        if callable(metodo):
            try:
                return metodo()
            except Exception:  # noqa: BLE001
                continue
    return {"text": getattr(response, "text", str(response))}


def generate(
    modulo: str,
    contents: Any,
    model: Optional[str] = None,
    db: Optional[Session] = None,
    usuario: Optional[str] = None,
    **opciones: Any,
) -> LLMResult:
    """
    Invoca la LLM y registra el uso.

    Args:
        modulo: código del módulo que invoca (ej: 'soporte'). OBLIGATORIO.
        contents: prompt/contenido a enviar (str o estructura del SDK).
        model: nombre del modelo. Si es None usa settings.gemini_model.
        db: sesión SQLAlchemy para registrar el uso (opcional pero recomendado).
        usuario: email/identificador para updated_by.
        **opciones: parámetros extra del SDK (config, etc.).

    Returns:
        LLMResult con texto y métricas.
    """
    if not modulo:
        raise ValueError("El parámetro 'modulo' es obligatorio")

    model_name = (model or settings.gemini_model or "gemini-2.0-flash").strip()
    request_id = str(uuid.uuid4())
    periodo = logging_store.periodo_actual()

    request_file = logging_store.guardar_request(
        request_id,
        {"modulo": modulo, "model": model_name, "contents": contents, "opciones": opciones},
        periodo,
    )

    if not settings.llm_enabled:
        raise LLMError("LLM deshabilitada (LLM_ENABLED=False)")

    inicio = time.perf_counter()
    try:
        client = _get_client()
        response = client.models.generate_content(model=model_name, contents=contents, **opciones)
    except LLMError:
        raise
    except Exception as e:  # noqa: BLE001
        latencia_ms = int((time.perf_counter() - inicio) * 1000)
        logger.error("Error invocando LLM (modulo=%s): %s", modulo, e, exc_info=True)
        response_file = logging_store.guardar_response(request_id, {"error": str(e)}, periodo)
        resultado = LLMResult(
            id=request_id,
            modulo=modulo,
            model_name=model_name,
            text="",
            latencia_ms=latencia_ms,
            status="error",
            request_file=request_file,
            response_file=response_file,
        )
        _registrar(db, resultado, error=str(e), usuario=usuario)
        raise LLMError(str(e)) from e

    latencia_ms = int((time.perf_counter() - inicio) * 1000)
    response_file = logging_store.guardar_response(request_id, _response_to_dict(response), periodo)

    usage = _extraer_usage(response)
    costo = calcular_costo(
        model_name,
        tokens_input=usage["input"],
        tokens_output=usage["output"],
        tokens_cache=usage["cache"],
    )

    resultado = LLMResult(
        id=request_id,
        modulo=modulo,
        model_name=model_name,
        text=getattr(response, "text", "") or "",
        tokens_input=usage["input"],
        tokens_output=usage["output"],
        tokens_cache=usage["cache"],
        tokens_total=usage["total"],
        costo_usd=costo,
        latencia_ms=latencia_ms,
        status="ok",
        request_file=request_file,
        response_file=response_file,
        raw=response,
    )
    _registrar(db, resultado, usuario=usuario)
    return resultado


def _registrar(
    db: Optional[Session],
    resultado: LLMResult,
    error: Optional[str] = None,
    usuario: Optional[str] = None,
) -> None:
    """Registra el uso en la base de datos (si hay sesión)."""
    if db is None:
        return
    try:
        # Import perezoso para evitar ciclos.
        from backend.modules.llm.services import LLMRequestService

        LLMRequestService.registrar(
            db,
            {
                "id": resultado.id,
                "modulo": resultado.modulo,
                "model_name": resultado.model_name,
                "tokens_input": resultado.tokens_input,
                "tokens_output": resultado.tokens_output,
                "tokens_cache": resultado.tokens_cache,
                "tokens_total": resultado.tokens_total,
                "costo_usd": resultado.costo_usd,
                "request_file": resultado.request_file,
                "response_file": resultado.response_file,
                "status": resultado.status,
                "error_mensaje": error,
                "latencia_ms": resultado.latencia_ms,
            },
            usuario=usuario,
        )
    except Exception as e:  # noqa: BLE001
        # El registro de uso nunca debe romper el flujo del módulo que llama.
        logger.error("No se pudo registrar uso de LLM: %s", e, exc_info=True)
