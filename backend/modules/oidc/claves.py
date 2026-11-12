"""Claves de firma de los id_token (F21, docs/OIDC.md).

Un archivo PEM con una clave privada RSA por kid en settings.oidc_claves_dir (`<kid>.pem`). El JWKS publica la
pública de todas; firma la de settings.oidc_kid_activa. Para rotar: agregar la nueva (queda publicada), pasar la activa
a la nueva y, cuando venza el último id_token firmado con la vieja (una hora), sacar el archivo viejo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from backend.core.config import settings

ALGORITMO = "RS256"


class SinClaves(Exception):
    """OIDC sin la clave activa configurada: no se pueden firmar id_token."""


@lru_cache(maxsize=4)
def _cargar(directorio: str, huella: tuple) -> dict[str, rsa.RSAPrivateKey]:
    claves = {}
    for archivo in sorted(Path(directorio).glob("*.pem")):
        clave = serialization.load_pem_private_key(archivo.read_bytes(), password=None)
        if isinstance(clave, rsa.RSAPrivateKey):
            claves[archivo.stem] = clave
    return claves


def claves() -> dict[str, rsa.RSAPrivateKey]:
    """Las claves del directorio, releídas solo si cambió algún archivo (una rotación no pide reiniciar)."""
    directorio = Path(settings.oidc_claves_dir)
    if not directorio.is_dir():
        return {}
    huella = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(directorio.glob("*.pem")))
    return _cargar(str(directorio), huella)


def jwks() -> dict:
    publicas = []
    for kid, clave in claves().items():
        jwk = RSAAlgorithm.to_jwk(clave.public_key(), as_dict=True)
        publicas.append({**jwk, "kid": kid, "use": "sig", "alg": ALGORITMO})
    return {"keys": publicas}


def disponible() -> bool:
    return bool(settings.oidc_kid_activa) and settings.oidc_kid_activa in claves()


def firmar(claims: dict) -> str:
    kid = settings.oidc_kid_activa
    clave = claves().get(kid) if kid else None
    if clave is None:
        raise SinClaves(f"No está la clave activa «{kid}» en {settings.oidc_claves_dir}")
    return jwt.encode(claims, clave, algorithm=ALGORITMO, headers={"kid": kid})


def generar_pem() -> str:
    """Una clave RSA de 2048 bits nueva, en PEM (PKCS#8, sin cifrar), para guardar como <kid>.pem en secrets/."""
    clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return clave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
