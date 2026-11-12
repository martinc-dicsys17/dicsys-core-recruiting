"""Lógica del proveedor OpenID Connect (F21): autorización con código + PKCE, canje del código e id_token.

Los errores siguen RFC 6749 (§4.1.2.1 en la autorización, §5.2 en el canje). Un cliente o un redirect_uri que no está
registrado nunca recibe una redirección: el error se muestra en Core.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.core import config
from backend.core.config import settings
from backend.core.utils import utc_now
from backend.modules.oidc import claves
from backend.modules.oidc.models import ClienteOIDC, CodigoOIDC
from backend.modules.usuarios.models import Usuario

VIGENCIA_CODIGO = timedelta(minutes=10)
VIGENCIA_ID_TOKEN = timedelta(hours=1)
SCOPES = ("openid", "email", "profile")
DOMINIOS_VERIFICADOS = "dicsys.com,dicsys.ai"  # parámetro oidc_dominios_verificados (decisión de F21)
# RFC 7636: el challenge S256 es BASE64URL(SHA256(verifier)) sin relleno; el verifier, 43 a 128 caracteres
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")


class ErrorOIDC(Exception):
    """Error del protocolo. Con `redirect` se le devuelve al cliente en su redirect_uri; sin él, se muestra en Core."""

    def __init__(self, error: str, descripcion: str, redirect: str | None = None, status: int = 400):
        super().__init__(descripcion)
        self.error, self.descripcion, self.redirect, self.status = error, descripcion, redirect, status

    def respuesta(self) -> dict:
        cuerpo = {"error": self.error, "error_description": self.descripcion}
        if self.redirect:
            cuerpo["redirect"] = self.redirect
        return cuerpo


def issuer() -> str:
    """La URL pública de Core, exacta: la misma en el discovery y en el claim iss."""
    return (settings.oidc_issuer or settings.frontend_url).rstrip("/")


def disponible() -> bool:
    return claves.disponible()


def discovery() -> dict:
    base = issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oidc/authorize",
        "token_endpoint": f"{base}/oidc/token",
        "jwks_uri": f"{base}/oidc/jwks",
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [claves.ALGORITMO],
        "scopes_supported": list(SCOPES),
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "claims_supported": ["iss", "aud", "exp", "iat", "nonce", "sub", "email", "email_verified", "name", "picture"],
    }


def hash_secreto(secreto: str) -> str:
    return hashlib.sha256(secreto.encode()).hexdigest()


def _sha(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


def _s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def _con_parametros(uri: str, **parametros) -> str:
    """El redirect_uri con los parámetros de la respuesta agregados a su query (sin perder los que ya tenía)."""
    partes = urlsplit(uri)
    query = parse_qsl(partes.query, keep_blank_values=True) + [(k, v) for k, v in parametros.items() if v is not None]
    return urlunsplit(partes._replace(query=urlencode(query)))


# ----------------------------------------------------------------------------- autorización
def cliente_y_redirect(db: Session, client_id: str | None, redirect_uri: str | None) -> ClienteOIDC:
    """El cliente activo y su redirect_uri, con coincidencia exacta: redirigir a una URI no registrada le entregaría el
    código a cualquiera, así que estos errores no redirigen."""
    cliente = (
        db.query(ClienteOIDC).filter(ClienteOIDC.client_id == (client_id or ""), ClienteOIDC.activo.is_(True)).first()
    )
    if cliente is None:
        raise ErrorOIDC("invalid_client", "La aplicación no está registrada en Dicsys Core o está desactivada.")
    if not redirect_uri or redirect_uri not in (cliente.redirect_uris or []):
        raise ErrorOIDC("invalid_request", "La dirección de retorno no está registrada para esta aplicación.")
    return cliente


def validar_pedido(db: Session, pedido: dict) -> ClienteOIDC:
    """Valida los parámetros de /oidc/authorize. Lo que falla después de validar cliente y redirect_uri vuelve al
    cliente como error en su redirect_uri, con el state."""
    cliente = cliente_y_redirect(db, pedido.get("client_id"), pedido.get("redirect_uri"))

    def error(codigo: str, descripcion: str) -> ErrorOIDC:
        return ErrorOIDC(
            codigo,
            descripcion,
            redirect=_con_parametros(
                pedido["redirect_uri"], error=codigo, error_description=descripcion, state=pedido.get("state")
            ),
        )

    if pedido.get("response_type") != "code":
        raise error("unsupported_response_type", "Solo se admite response_type=code.")
    scopes = (pedido.get("scope") or "").split()
    if "openid" not in scopes:
        raise error("invalid_scope", "El scope tiene que incluir openid.")
    if not set(scopes) <= set(cliente.scopes.split()):
        raise error("invalid_scope", "La aplicación pidió scopes que no tiene permitidos.")
    if pedido.get("code_challenge_method") != "S256" or not _CHALLENGE.match(pedido.get("code_challenge") or ""):
        raise error("invalid_request", "PKCE es obligatorio: code_challenge con code_challenge_method=S256.")
    if not pedido.get("nonce"):
        raise error("invalid_request", "Falta el nonce.")
    return cliente


def autorizar(db: Session, usuario: Usuario, pedido: dict) -> str:
    """Emite un código para la persona de la sesión de Core. Devuelve la URL a la que vuelve el navegador."""
    cliente = validar_pedido(db, pedido)
    if not usuario.activo or usuario.deleted_at is not None:
        raise ErrorOIDC(
            "access_denied",
            "La cuenta de Dicsys Core está desactivada.",
            redirect=denegar(db, pedido, "La cuenta de Dicsys Core está desactivada."),
        )
    db.query(CodigoOIDC).filter(CodigoOIDC.expira_at < utc_now() - timedelta(days=1)).delete()
    codigo = secrets.token_urlsafe(32)
    db.add(
        CodigoOIDC(
            codigo_hash=_sha(codigo),
            cliente_id=cliente.id,
            usuario_id=usuario.id,
            redirect_uri=pedido["redirect_uri"],
            scope=" ".join(s for s in SCOPES if s in pedido["scope"].split()),
            nonce=pedido["nonce"],
            code_challenge=pedido["code_challenge"],
            expira_at=utc_now() + VIGENCIA_CODIGO,
        )
    )
    db.commit()
    return _con_parametros(pedido["redirect_uri"], code=codigo, state=pedido.get("state"))


def denegar(
    db: Session, pedido: dict, motivo: str = "La persona canceló el ingreso o su cuenta de Dicsys Core no puede entrar."
) -> str:
    """La vuelta al cliente con access_denied: la persona canceló o su cuenta no puede entrar."""
    cliente_y_redirect(db, pedido.get("client_id"), pedido.get("redirect_uri"))
    return _con_parametros(
        pedido["redirect_uri"], error="access_denied", error_description=motivo, state=pedido.get("state")
    )


# ----------------------------------------------------------------------------- canje del código
def autenticar_cliente(db: Session, client_id: str | None, client_secret: str | None) -> ClienteOIDC:
    """client_secret_post o client_secret_basic (el frontend pasa las dos formas igual). Durante una rotación valen el
    secreto actual y el nuevo."""
    cliente = (
        db.query(ClienteOIDC).filter(ClienteOIDC.client_id == (client_id or ""), ClienteOIDC.activo.is_(True)).first()
    )
    calculado = hash_secreto(client_secret or "")
    vigentes = [h for h in ((cliente.secreto_hash, cliente.secreto_nuevo_hash) if cliente else ()) if h]
    if not client_secret or not any(hmac.compare_digest(calculado, h) for h in vigentes):
        raise ErrorOIDC("invalid_client", "La autenticación del cliente falló.", status=401)
    return cliente


def canjear(db: Session, datos: dict) -> dict:
    cliente = autenticar_cliente(db, datos.get("client_id"), datos.get("client_secret"))
    if datos.get("grant_type") != "authorization_code":
        raise ErrorOIDC("unsupported_grant_type", "Solo se admite grant_type=authorization_code.")
    invalido = ErrorOIDC(
        "invalid_grant",
        "El código no es válido, ya se usó, venció, o no corresponde al redirect_uri o al code_verifier.",
    )
    codigo = datos.get("code") or ""
    fila = db.query(CodigoOIDC).filter(CodigoOIDC.codigo_hash == _sha(codigo)).first() if codigo else None
    if fila is None or fila.cliente_id != cliente.id:
        raise invalido
    # Un solo uso, también con dos canjes a la vez: el código queda usado para quien lo marca primero, y un intento
    # fallido (otro verifier u otro redirect_uri) también lo consume
    usado = db.execute(
        update(CodigoOIDC).where(CodigoOIDC.id == fila.id, CodigoOIDC.usado_at.is_(None)).values(usado_at=utc_now())
    ).rowcount
    db.commit()
    verifier = datos.get("code_verifier") or ""
    if (
        not usado
        or fila.expira_at < utc_now()
        or datos.get("redirect_uri") != fila.redirect_uri
        or not _VERIFIER.match(verifier)
        or not hmac.compare_digest(_s256(verifier), fila.code_challenge)
    ):
        raise invalido
    usuario = db.get(Usuario, fila.usuario_id)
    if usuario is None or not usuario.activo or usuario.deleted_at is not None:
        raise invalido
    id_token = claves.firmar(claims(db, usuario, cliente, fila))
    return {
        # Obligatorio en la respuesta (OIDC Core 3.1.3.3), sin uso: Core no expone APIs para él
        "access_token": secrets.token_urlsafe(32),
        "token_type": "Bearer",
        "expires_in": int(VIGENCIA_ID_TOKEN.total_seconds()),
        "scope": fila.scope,
        "id_token": id_token,
    }


def dominios_verificados(db: Session) -> set[str]:
    valor = config.get_parameter("oidc_dominios_verificados", DOMINIOS_VERIFICADOS, db=db) or ""
    return {d.strip().lower().lstrip("@") for d in valor.split(",") if d.strip()}


def _foto(usuario: Usuario) -> str | None:
    """La foto como URL https absoluta: las subidas a Core se sirven desde el mismo dominio (/files/...)."""
    url = usuario.avatar_url or ""
    if url.startswith("https://"):
        return url
    if url.startswith("/") and issuer().startswith("https://"):
        return issuer() + url
    return None


def claims(db: Session, usuario: Usuario, cliente: ClienteOIDC, codigo: CodigoOIDC) -> dict:
    emitido = int(utc_now().replace(tzinfo=timezone.utc).timestamp())
    datos = {
        "iss": issuer(),
        "aud": cliente.client_id,
        "iat": emitido,
        "exp": emitido + int(VIGENCIA_ID_TOKEN.total_seconds()),
        "nonce": codigo.nonce,
        # El id del usuario: nunca se reasigna; una persona recreada con el mismo email tiene otro
        "sub": str(usuario.id),
    }
    scopes = codigo.scope.split()
    if "email" in scopes:
        dominio = usuario.email.rsplit("@", 1)[-1].lower()
        datos["email"] = usuario.email
        # Decisión de F21: verificado = cuenta activa con email de un dominio corporativo
        datos["email_verified"] = bool(usuario.activo and dominio in dominios_verificados(db))
    if "profile" in scopes:
        datos["name"] = " ".join(p for p in (usuario.nombre, usuario.apellido) if p)
        if foto := _foto(usuario):
            datos["picture"] = foto
    return datos
