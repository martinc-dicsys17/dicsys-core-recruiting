"""
Tabla de precios de modelos Gemini (USD por 1.000.000 de tokens).

Fuente: https://ai.google.dev/gemini-api/docs/pricing
Revisar y actualizar cuando Google modifique las tarifas.

Cada entrada define:
- input:  precio por 1M tokens de entrada (prompt)
- output: precio por 1M tokens de salida (respuesta)
- cache:  precio por 1M tokens servidos desde cache de contexto

Cuando Google publica varios precios por modalidad (texto/audio/video) o por
tramo de tokens, esta tabla guarda la tarifa estandar base que el calculo
actual puede aplicar con los contadores agregados que devuelve Gemini.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Dict

# Precios en USD por 1M de tokens.
PRICING: Dict[str, Dict[str, Decimal]] = {
    "gemini-3.1-flash-lite": {
        "input": Decimal("0.25"),
        "output": Decimal("1.50"),
        "cache": Decimal("0.025"),
    },
    "gemini-3.1-pro-preview": {
        "input": Decimal("2.00"),
        "output": Decimal("12.00"),
        "cache": Decimal("0.20"),
    },
    "gemini-3.1-pro-preview-customtools": {
        "input": Decimal("2.00"),
        "output": Decimal("12.00"),
        "cache": Decimal("0.20"),
    },
    "gemini-3.1-flash-live-preview": {
        "input": Decimal("0.75"),
        "output": Decimal("4.50"),
        "cache": Decimal("0.00"),
    },
    "gemini-3.5-flash": {
        "input": Decimal("1.50"),
        "output": Decimal("9.00"),
        "cache": Decimal("0.15"),
    },
}

# Precio usado si el modelo no está en la tabla (evita costo 0 silencioso).
DEFAULT_PRICING: Dict[str, Decimal] = {
    "input": Decimal("0.10"),
    "output": Decimal("0.40"),
    "cache": Decimal("0.025"),
}

_MILLON = Decimal("1000000")


def obtener_precios(model_name: str) -> Dict[str, Decimal]:
    """Devuelve la tabla de precios del modelo (o el default)."""
    if not model_name:
        return DEFAULT_PRICING
    # Normalizar: quitar prefijo "models/" si viene del SDK.
    clave = model_name.replace("models/", "").strip().lower()
    return PRICING.get(clave, DEFAULT_PRICING)


def calcular_costo(
    model_name: str,
    tokens_input: int = 0,
    tokens_output: int = 0,
    tokens_cache: int = 0,
) -> Decimal:
    """
    Calcula el costo en USD de una request.

    Los tokens de cache se cobran a su tarifa reducida y NO se vuelven a
    cobrar como input (Gemini reporta cached_content_token_count por separado
    dentro del prompt_token_count, por eso se descuentan del input).
    """
    precios = obtener_precios(model_name)

    input_no_cache = max(int(tokens_input or 0) - int(tokens_cache or 0), 0)

    costo = (
        (Decimal(input_no_cache) * precios["input"]) / _MILLON
        + (Decimal(int(tokens_output or 0)) * precios["output"]) / _MILLON
        + (Decimal(int(tokens_cache or 0)) * precios["cache"]) / _MILLON
    )
    # Redondear a 6 decimales (Numeric(12, 6) en la DB).
    return costo.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
