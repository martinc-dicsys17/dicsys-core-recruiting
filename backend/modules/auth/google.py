"""Ingreso con Google (F22, docs/IngresoGoogle.md).

Para Google, Core es una app más con OpenID Connect: código con PKCE y nonce. El frontend lleva el navegador a Google y
recibe la vuelta. Acá se arma la URL de Google, se canjea el código (server a server, con el secreto) y se verifica el
id_token. Después se busca la cuenta de Core de esa persona y, en su primer ingreso, se muda el email de la cuenta:
nombre@dicsys.ai pasa a ser el email y nombre@dicsys.com el secundario; las fichas de nómina copian el nuevo.
"""

import logging
import re
from typing import Optional
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.core import config
from backend.core.adapter_proxy import AdapterProxy
from backend.core.config import settings
from backend.modules.parametros.services import registrar_validador
from backend.modules.usuarios import emails_corporativos
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

AUTORIZACION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
EMISORES = ("https://accounts.google.com", "accounts.google.com")
RUTA_VUELTA = "/login/google/callback"  # en el frontend; Google la tiene registrada como URL de vuelta autorizada

PARAMETRO_2FA = "google_login_requiere_2fa"
PARAMETRO_DOMINIO = "google_login_dominio"
DOMINIO_POR_DEFECTO = "dicsys.ai"
VERDADERO = ("1", "true", "si", "sí")
FALSO = ("0", "false", "no")
ACTOR = "ingreso_google"  # updated_by de la cuenta mudada

SIN_CUENTA = (
    "Tu cuenta de Google no está asociada a un usuario de Dicsys Core. Pedile al administrador que "
    "cargue ese email en tu usuario."
)


class ErrorGoogle(Exception):
    """Google no dio un id_token válido: código vencido o usado, firma, audiencia, emisor."""


class IngresoRechazado(Exception):
    def __init__(self, status: int, detalle: str):
        super().__init__(detalle)
        self.status, self.detalle = status, detalle


class ClienteGoogle:
    """Lo que se habla con Google. Los tests lo reemplazan con `google.set_adapter(...)`."""

    def __init__(self):
        self._cliente_jwks: Optional[jwt.PyJWKClient] = None

    def _jwks(self) -> jwt.PyJWKClient:
        if self._cliente_jwks is None:
            self._cliente_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
        return self._cliente_jwks

    def canjear(self, code: str, code_verifier: str, redirect_uri: str) -> dict:
        """Canjea el código en Google y devuelve los claims del id_token verificado."""
        try:
            respuesta = httpx.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": code_verifier,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                },
                timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise ErrorGoogle(f"no se pudo hablar con Google ({exc.__class__.__name__})") from exc
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = {}
        if not respuesta.is_success:
            # invalid_grant: el código venció, ya se usó o es de otra URL de vuelta
            raise ErrorGoogle(f"Google rechazó el código ({cuerpo.get('error') or respuesta.status_code})")
        if not cuerpo.get("id_token"):
            raise ErrorGoogle("Google no devolvió un id_token")
        return self.verificar(cuerpo["id_token"])

    def verificar(self, id_token: str) -> dict:
        """Firma con las claves públicas de Google, emisor, audiencia (nuestro client_id) y vencimiento."""
        try:
            clave = self._jwks().get_signing_key_from_jwt(id_token)
            return jwt.decode(
                id_token,
                clave.key,
                algorithms=["RS256"],
                audience=settings.google_oauth_client_id,
                issuer=EMISORES,
                leeway=60,
                options={"require": ["iss", "aud", "sub", "exp", "iat"]},
            )
        except jwt.PyJWTError as exc:
            raise ErrorGoogle(f"el id_token de Google no es válido ({exc})") from exc


google = AdapterProxy(ClienteGoogle())


def disponible() -> bool:
    """Sin el cliente OAuth configurado el ingreso con Google está apagado: no hay botón y sus rutas dan 404."""
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def redirect_uri() -> str:
    return settings.frontend_url.rstrip("/") + RUTA_VUELTA


def dominio_google(db: Session) -> str:
    valor = config.get_parameter(PARAMETRO_DOMINIO, DOMINIO_POR_DEFECTO, db=db) or DOMINIO_POR_DEFECTO
    return valor.strip().lower().lstrip("@")


def requiere_2fa(db: Session) -> bool:
    """Parámetro google_login_requiere_2fa: apagado, entrar con Google no pide el 2FA de Core (decisión de F22)."""
    return str(config.get_parameter(PARAMETRO_2FA, "false", db=db) or "").strip().lower() in VERDADERO


def url_autorizacion(db: Session, state: str, nonce: str, code_challenge: str) -> str:
    return (
        AUTORIZACION_URL
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.google_oauth_client_id,
                "redirect_uri": redirect_uri(),
                "scope": "openid email profile",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "hd": dominio_google(db),
                "prompt": "select_account",
            }
        )
    )


def email_verificado(claims: dict, nonce: str, dominio: str) -> str:
    """El email del id_token, si es de este pedido (nonce) y de una cuenta verificada del dominio. El dominio sale
    del claim `hd`, que firma Google: no alcanza con que el email termine en @dicsys.ai."""
    if not nonce or claims.get("nonce") != nonce:
        raise IngresoRechazado(400, "El ingreso con Google no corresponde a este pedido. Probá de nuevo.")
    email = emails_corporativos.normalizar(claims.get("email"))
    if claims.get("email_verified") is not True or not email:
        raise IngresoRechazado(403, "Google no confirmó el email de esa cuenta")
    if str(claims.get("hd") or "").lower() != dominio or emails_corporativos.dominio(email) != dominio:
        raise IngresoRechazado(403, f"Solo se puede entrar con una cuenta de Google @{dominio}")
    return email


def _mudable(db: Session, usuario: Usuario, local: str, dominio: str) -> bool:
    actual = emails_corporativos.normalizar(usuario.email)
    if not actual or actual.split("@", 1)[0] != local or emails_corporativos.dominio(actual) == dominio:
        return False
    if emails_corporativos.normalizar(usuario.email_secundario):
        return False
    dominios = emails_corporativos.dominios_de_la_cuenta(db, usuario)
    return emails_corporativos.dominio(actual) in dominios and dominio in dominios


def _mudar(db: Session, email: str, dominio: str) -> Optional[Usuario]:
    """Primer ingreso de nombre@<dominio de Google> de quien solo tiene nombre@<otro dominio de su empresa> en la
    cuenta: el de Google pasa a ser el email de la cuenta y el anterior el secundario, y las fichas copian el nuevo. La
    parte antes de la arroba tiene que ser la misma; con secundario cargado no se toca nada. Una cuenta desactivada no
    se muda: el login la rechaza igual."""
    local = email.split("@", 1)[0]
    candidatas = [
        usuario
        for usuario in db.query(Usuario)
        .filter(
            Usuario.deleted_at.is_(None),
            func.lower(func.trim(Usuario.email)).startswith(local + "@", autoescape=True),
        )
        .all()
        if _mudable(db, usuario, local, dominio)
    ]
    if len(candidatas) > 1:
        logger.warning(
            f"Ingreso con Google de {email}: {len(candidatas)} cuentas con {local}@ en otro dominio, no se muda"
        )
    if len(candidatas) != 1:
        return None
    usuario = candidatas[0]
    if not usuario.activo:
        return usuario

    anterior = emails_corporativos.normalizar(usuario.email)
    usuario.email_secundario = anterior
    usuario.email = email
    usuario.updated_by = ACTOR
    emails_corporativos.copiar_a_fichas(db, usuario)
    db.commit()
    logger.info(
        f"Ingreso con Google: la cuenta {usuario.id} pasa de {anterior} a {email} ({anterior} queda de secundario)"
    )
    return usuario


def cuenta(db: Session, email: str, dominio: str) -> Usuario:
    """La cuenta de Core de ese email de Google: la que lo tiene como email o secundario; si no hay, la mudanza del
    primer ingreso. Google no crea cuentas."""
    cuentas = emails_corporativos.cuentas_con_email(db, email)
    if len(cuentas) > 1:
        logger.warning(f"Ingreso con Google de {email}: el email está en {len(cuentas)} cuentas")
        raise IngresoRechazado(403, SIN_CUENTA)
    usuario = cuentas[0] if cuentas else _mudar(db, email, dominio)
    if usuario is None:
        raise IngresoRechazado(403, SIN_CUENTA)
    return usuario


def identificar(db: Session, code: str, code_verifier: str, nonce: str) -> Usuario:
    """El usuario de Core que vuelve de Google con ese código. IngresoRechazado si no corresponde."""
    try:
        claims = google.canjear(code, code_verifier, redirect_uri())
    except ErrorGoogle as exc:
        logger.warning(f"Ingreso con Google: {exc}")
        raise IngresoRechazado(400, "Google no confirmó el ingreso. Probá de nuevo.") from exc
    dominio = dominio_google(db)
    return cuenta(db, email_verificado(claims, nonce, dominio), dominio)


# Parámetros: un valor que no se entiende no se guarda.
def _validar_si_no(valor: Optional[str]) -> None:
    texto = str(valor or "").strip().lower()
    if texto and texto not in VERDADERO + FALSO:
        raise ValueError(f"Valor inválido: «{valor}». Usá true (pide el 2FA de Core) o false (Google alcanza)")


def _validar_dominio(valor: Optional[str]) -> None:
    texto = str(valor or "").strip().lower().lstrip("@")
    if texto and not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", texto):
        raise ValueError(f"Dominio inválido: «{valor}». Por ejemplo: dicsys.ai")


registrar_validador(lambda key: key == PARAMETRO_2FA, _validar_si_no)
registrar_validador(lambda key: key == PARAMETRO_DOMINIO, _validar_dominio)
