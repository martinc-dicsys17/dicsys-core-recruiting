"""Módulo LLM - Registro y uso de modelos de lenguaje (Gemini)."""

# No registra módulo propio en el registry.
# El item "LLM Usage" se muestra dentro del menú de Configuración
# como submódulo `configuracion.llm`
# (registrado en backend/modules/permisos/__init__.py).
from backend.modules.llm.models import LLMRequest

__all__ = ["LLMRequest"]
