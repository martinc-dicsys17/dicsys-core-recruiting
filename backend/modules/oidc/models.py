"""Clientes registrados y códigos de autorización del proveedor OpenID Connect (F21)."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from backend.core.utils import utc_now
from backend.database import Base


class ClienteOIDC(Base):
    """Una app que usa a Core para identificar personas (razorback). Se administra con backend/modules/oidc/cli.py."""

    __tablename__ = "core_oidc_clientes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String(100), nullable=False, unique=True)
    nombre = Column(String(150), nullable=False)
    # Coincidencia exacta: ni prefijos ni comodines
    redirect_uris = Column(JSONB, nullable=False, default=list)
    scopes = Column(String(255), nullable=False, default="openid email profile")
    # SHA-256 del secreto. Durante una rotación valen el actual y el nuevo, hasta que se confirma
    secreto_hash = Column(String(100), nullable=False)
    secreto_nuevo_hash = Column(String(100), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class CodigoOIDC(Base):
    """Código de autorización: de un solo uso, vence a los 10 minutos y queda atado al PKCE y al redirect_uri."""

    __tablename__ = "core_oidc_codigos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo_hash = Column(String(64), nullable=False, unique=True)  # SHA-256: el código en claro no se guarda
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("core_oidc_clientes.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=False)
    redirect_uri = Column(String(500), nullable=False)
    scope = Column(String(255), nullable=False)
    nonce = Column(String(255), nullable=False)
    code_challenge = Column(String(128), nullable=False)  # S256
    expira_at = Column(DateTime, nullable=False, index=True)
    usado_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
