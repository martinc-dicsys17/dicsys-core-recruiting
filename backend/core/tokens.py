"""Tokens JWT de la API (PyJWT): un solo lugar para firmarlos y validarlos.

Los tokens de sesión no llevan `purpose`. Los intermedios del login con 2FA sí ("2fa" y "2fa_setup") y solo sirven
en los endpoints que los esperan (verify-2fa y el alta del 2FA obligatorio): en cualquier otro lado se rechazan,
porque se emiten con solo la contraseña y darían una sesión completa sin pasar por el segundo factor (F16-P04).
"""

from datetime import timedelta
from typing import Any, Iterable

import jwt
from fastapi import HTTPException

from backend.core.config import settings
from backend.core.utils import utc_now


def crear_token(datos: dict[str, Any], expira_en: timedelta | None = None) -> str:
    """Token firmado con los datos y su vencimiento (por defecto, el de la sesión)."""
    payload = dict(datos)
    payload["exp"] = utc_now() + (expira_en or timedelta(minutes=settings.jwt_expire_minutes))
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decodificar(
    token: str, propositos: Iterable[str] = (), detalle: str = "Token inválido o expirado", codigo: int = 401
) -> dict[str, Any]:
    """Payload de un token válido.

    Firma inválida, vencido o mal formado: `codigo` (401) con `detalle`, nunca un 500. Un token con `purpose` solo
    pasa si su propósito está en `propositos`.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=codigo, detail=detalle)
    proposito = payload.get("purpose")
    if proposito is not None and proposito not in tuple(propositos):
        raise HTTPException(status_code=codigo, detail="Token inválido")
    return payload
