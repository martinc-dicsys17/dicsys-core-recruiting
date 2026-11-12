"""
Utilidades comunes de la aplicación.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """Hora UTC actual como datetime naive.

    Reemplazo de datetime.utcnow() (deprecado en Python 3.12), preservando
    la semántica naive-UTC que esperan las columnas TIMESTAMP sin timezone.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def generate_uuid() -> str:
    """Genera un UUID v4 como string."""
    return str(uuid.uuid4())


def format_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Formatea datetime a string ISO."""
    return dt.isoformat() if dt else None


def validate_uuid(uuid_string: str) -> bool:
    """Valida si un string es un UUID válido."""
    try:
        uuid.UUID(uuid_string)
        return True
    except ValueError:
        return False
