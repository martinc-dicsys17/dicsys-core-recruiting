"""
Paquete core de LLM.

Uso desde cualquier módulo de backend/modules/:

    from backend.core.llm import generate

    result = generate(modulo='soporte', contents='Hola', db=db)
    print(result.text, result.costo_usd)
"""

from backend.core.adapter_proxy import AdapterProxy
from backend.core.llm.client import LLMError, LLMResult, generate as _generate
from backend.core.llm.logging_store import init_directories, leer_raw
from backend.core.llm.pricing import calcular_costo, obtener_precios

llm_generator = AdapterProxy(_generate)


def generate(*args, **kwargs):
    return llm_generator.adapter(*args, **kwargs)


__all__ = [
    "generate",
    "llm_generator",
    "LLMResult",
    "LLMError",
    "init_directories",
    "leer_raw",
    "calcular_costo",
    "obtener_precios",
]
