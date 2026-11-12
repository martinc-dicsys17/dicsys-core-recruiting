"""Utilidades del catálogo de gestión de licencias."""

import unicodedata
from typing import Optional


def normalizar_nombre(valor: Optional[str]) -> str:
    """Plega un nombre para comparar duplicados: sin acentos, minusculas, un espacio.

    "ChatGPT  Pro", "chatgpt pro" y "CHATGPT PRO" colapsan al mismo valor, que
    es lo que permite bloquear duplicados con un unique constraint.
    """
    if not valor:
        return ""
    sin_acentos = unicodedata.normalize("NFKD", valor)
    sin_acentos = "".join(c for c in sin_acentos if not unicodedata.combining(c))
    return " ".join(sin_acentos.lower().split())
