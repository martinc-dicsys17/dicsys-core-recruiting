"""Secretos de usuario que nunca se guardan en claro en la base.

Códigos de respaldo del 2FA (F02-P02): se guarda el HMAC-SHA256 de cada código con un pepper que vive fuera de la
base (BACKUP_CODES_PEPPER, o SECRET_KEY si está vacío) y se comparan con compare_digest. Rotar el pepper invalida los
códigos guardados. Magic links (F02-P03): se guarda el SHA-256 del token.
"""

import hashlib
import hmac
import json
import secrets
from typing import Optional

from backend.core.config import settings

PREFIJO = "hmac-sha256:"
CANTIDAD_CODIGOS = 8


def _pepper() -> bytes:
    return (settings.backup_codes_pepper or settings.secret_key).encode()


def normalizar(codigo: str) -> str:
    """Sin espacios ni guiones y en minúsculas: 'AB12C-34DEF' y 'ab12c34def' son el mismo código."""
    return "".join(codigo.split()).replace("-", "").lower()


def hashear(codigo: str) -> str:
    return PREFIJO + hmac.new(_pepper(), normalizar(codigo).encode(), hashlib.sha256).hexdigest()


def generar() -> tuple[list[str], str]:
    """Códigos nuevos de 10 caracteres ('xxxxx-xxxxx') para mostrar una sola vez, y el JSON con sus hashes."""
    codigos = []
    for _ in range(CANTIDAD_CODIGOS):
        crudo = secrets.token_hex(5)
        codigos.append(f"{crudo[:5]}-{crudo[5:]}")
    return codigos, json.dumps([hashear(c) for c in codigos])


def consumir(guardados: Optional[str], codigo: str) -> Optional[str]:
    """Si `codigo` es uno de los guardados, devuelve el JSON sin él (se usa una sola vez); si no, None.

    Solo compara hashes: los códigos en claro de antes los convierte la migración al arrancar.
    """
    if not guardados or not codigo:
        return None
    hashes = json.loads(guardados)
    buscado = hashear(codigo)
    for i, guardado in enumerate(hashes):
        if guardado.startswith(PREFIJO) and hmac.compare_digest(guardado, buscado):
            return json.dumps(hashes[:i] + hashes[i + 1 :])
    return None


def migrar(guardados: str) -> Optional[str]:
    """JSON con los códigos en claro convertidos a hash; None si no había ninguno en claro."""
    codigos = json.loads(guardados)
    if all(c.startswith(PREFIJO) for c in codigos):
        return None
    return json.dumps([c if c.startswith(PREFIJO) else hashear(c) for c in codigos])


# ---------------------------------------------------------------------- magic links (F02-P03)
PREFIJO_MAGIC_LINK = "sha256:"


def hash_magic_link(token: str) -> str:
    """Lo que se guarda de un magic link: su SHA-256. El token en claro solo viaja en el email (256 bits de azar:
    no necesita pepper)."""
    return PREFIJO_MAGIC_LINK + hashlib.sha256(token.encode()).hexdigest()


def nuevo_magic_link() -> tuple[str, str]:
    """Token nuevo para el email y su hash para la base."""
    token = secrets.token_urlsafe(32)
    return token, hash_magic_link(token)
