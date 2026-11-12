"""Refresh tokens de la sesión del navegador (F07-P03, D-12)."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class TokenRefresco(Base):
    """Un refresh token: vive en una cookie httpOnly y solo sirve para pedir un access token nuevo.

    Se guarda el SHA-256 del token, nunca el token. Cada refresh lo rota: queda marcado como rotado y nace otro de la
    misma familia (una familia es una sesión, desde el login). Presentar uno ya rotado es un replay: se revoca la
    familia entera. El logout también la revoca.
    """

    __tablename__ = "auth_refresh_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String(64), nullable=False, unique=True)  # SHA-256 del token en claro
    familia = Column(UUID(as_uuid=True), nullable=False, index=True)
    usuario_id = Column(
        UUID(as_uuid=True), ForeignKey("core_usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Empresa activa de la sesión: el access token que sale del refresh la lleva en empresa_id
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    expira_at = Column(DateTime, nullable=False)
    rotado_at = Column(DateTime, nullable=True)
    revocado_at = Column(DateTime, nullable=True)
