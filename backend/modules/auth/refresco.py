"""Refresh tokens rotativos de la sesión del navegador (F07-P03, D-12).

El refresh viaja en una cookie httpOnly limitada a /api/v1/auth y solo sirve para pedir un access token nuevo: el JWT
de siempre, de JWT_EXPIRE_MINUTES, que la SPA guarda en memoria. Cada uso lo rota y reusar uno ya rotado revoca la
sesión entera (su familia). El Bearer que usa Flask no cambia.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.utils import utc_now
from backend.modules.auth.models import TokenRefresco
from backend.modules.empresa.models import core_usuario_empresa
from backend.modules.usuarios.models import Usuario

COOKIE = "refresh_token"
RUTA_COOKIE = f"{settings.api_v1_prefix}/auth"


class RefrescoInvalido(Exception):
    """El refresh no sirve: no existe, venció, se revocó o se reusó (y entonces se revocó su sesión)."""


@dataclass
class Rotacion:
    usuario: Usuario
    empresa_id: uuid.UUID | None
    token: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def emitir(
    db: Session, usuario_id: uuid.UUID, empresa_id: uuid.UUID | None = None, familia: uuid.UUID | None = None
) -> str:
    """Un refresh nuevo para el usuario (y su empresa activa). Sin familia, empieza una sesión nueva."""
    token = secrets.token_urlsafe(32)
    db.add(
        TokenRefresco(
            jti=_hash(token),
            familia=familia or uuid.uuid4(),
            usuario_id=usuario_id,
            empresa_id=empresa_id,
            expira_at=utc_now() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return token


def _revocar_familia(db: Session, familia: uuid.UUID) -> None:
    db.query(TokenRefresco).filter(TokenRefresco.familia == familia, TokenRefresco.revocado_at.is_(None)).update(
        {"revocado_at": utc_now()}, synchronize_session=False
    )
    db.commit()


def rotar(db: Session, token: str) -> Rotacion:
    """Canjea un refresh por otro de la misma sesión. Si no sirve, RefrescoInvalido."""
    fila = (
        db.query(TokenRefresco).filter(TokenRefresco.jti == _hash(token)).with_for_update().first() if token else None
    )
    if fila is None or fila.revocado_at is not None:
        raise RefrescoInvalido("Sesión inválida o cerrada")
    if fila.rotado_at is not None:
        # replay: alguien usó un refresh que ya se había canjeado; la sesión entera deja de valer
        _revocar_familia(db, fila.familia)
        raise RefrescoInvalido("Sesión inválida o cerrada")
    if fila.expira_at <= utc_now():
        raise RefrescoInvalido("La sesión venció")
    usuario = db.get(Usuario, fila.usuario_id)
    sigue_en_la_empresa = (
        fila.empresa_id is None
        or db.execute(
            select(core_usuario_empresa.c.usuario_id).where(
                core_usuario_empresa.c.usuario_id == fila.usuario_id,
                core_usuario_empresa.c.empresa_id == fila.empresa_id,
            )
        ).first()
    )
    if usuario is None or not usuario.activo or usuario.deleted_at is not None or not sigue_en_la_empresa:
        _revocar_familia(db, fila.familia)
        raise RefrescoInvalido("La cuenta ya no tiene acceso")
    fila.rotado_at = utc_now()
    return Rotacion(
        usuario=usuario, empresa_id=fila.empresa_id, token=emitir(db, usuario.id, fila.empresa_id, fila.familia)
    )


def revocar(db: Session, token: str) -> None:
    """Cierra la sesión del refresh (logout): su familia entera deja de valer. Un token desconocido no hace nada."""
    fila = db.query(TokenRefresco).filter(TokenRefresco.jti == _hash(token)).first() if token else None
    if fila is not None:
        _revocar_familia(db, fila.familia)
