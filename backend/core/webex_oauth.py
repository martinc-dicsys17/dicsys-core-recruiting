"""
OAuth de Webex para la cuenta "lectora".

Los bots de Webex solo ven los mensajes de salas grupales donde fueron
@mencionados, por lo que no sirven para leer el canal de presentaciones.
Esta integración OAuth obtiene tokens de una cuenta de usuario real
(miembro de la sala) y los persiste en core_webex_oauth_tokens con
auto-refresh (access token ~14 días, refresh token ~90 días que se
renueva con cada uso).

Flujo:
  1. El admin abre `authorize_url()` y aprueba la integración con la
     cuenta lectora.
  2. Webex redirige al frontend (/oauth/callback) con un `code`.
  3. El frontend llama al backend, que canjea el code con `exchange_code()`.
  4. `get_reader_access_token()` devuelve siempre un token vigente
     (refresca solo si está por vencer).
"""

import hashlib
import hmac
import logging
from datetime import timedelta
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.utils import utc_now

logger = logging.getLogger(__name__)

WEBEX_AUTHORIZE_URL = "https://webexapis.com/v1/authorize"
WEBEX_TOKEN_URL = "https://webexapis.com/v1/access_token"
WEBEX_PEOPLE_ME_URL = "https://webexapis.com/v1/people/me"

# Deben ser subconjunto de los scopes registrados en la integración.
READER_SCOPES = "spark:memberships_read spark:kms spark:rooms_read spark:messages_write spark:messages_read"
PROPOSITO_READER = "reader"

# Margen para refrescar el access token antes de que venza.
_MARGEN_REFRESH = timedelta(days=1)


class WebexOAuthError(Exception):
    """Error en el flujo OAuth de Webex."""


def esta_configurado() -> bool:
    """Indica si la integración tiene client_id y secret configurados."""
    return bool(settings.webex_reader_client_id and settings.webex_reader_client_secret)


def generar_state() -> str:
    """
    State firmado con la secret key de la app: no requiere guardar estado
    entre el redirect y el callback (sobrevive reinicios y múltiples workers).
    """
    return hmac.new(settings.secret_key.encode(), b"webex-reader-oauth", hashlib.sha256).hexdigest()[:32]


def validar_state(state: Optional[str]) -> bool:
    """Valida el state recibido en el callback."""
    return bool(state) and hmac.compare_digest(state, generar_state())


def _resolver_redirect_uri(redirect_uri: Optional[str] = None) -> Optional[str]:
    """
    Redirect URI a usar: la que manda el frontend (derivada del host del
    request, funciona igual en localhost y producción) o el override opcional
    WEBEX_READER_REDIRECT_URI. Debe coincidir exactamente con una de las
    registradas en la integración.
    """
    return redirect_uri or settings.webex_reader_redirect_uri or None


def authorize_url(redirect_uri: Optional[str] = None) -> Optional[str]:
    """URL de autorización para conectar la cuenta lectora."""
    uri = _resolver_redirect_uri(redirect_uri)
    if not esta_configurado() or not uri:
        return None
    return (
        WEBEX_AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.webex_reader_client_id,
                "response_type": "code",
                "redirect_uri": uri,
                "scope": READER_SCOPES,
                "state": generar_state(),
            }
        )
    )


def _obtener_row(db: Session):
    from backend.modules.notificaciones.models import WebexOAuthToken

    return db.query(WebexOAuthToken).filter(WebexOAuthToken.proposito == PROPOSITO_READER).first()


def _pedir_token(payload: Dict[str, str]) -> Dict[str, Any]:
    """POST al endpoint de tokens de Webex (canje de code o refresh)."""
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(WEBEX_TOKEN_URL, data=payload)
    except httpx.HTTPError as e:
        raise WebexOAuthError(f"No se pudo conectar con Webex: {e}") from e

    if not response.is_success:
        raise WebexOAuthError(f"Webex devolvió {response.status_code}: {response.text}")
    return response.json()


def _guardar_tokens(db: Session, data: Dict[str, Any], usuario: Optional[str] = None):
    """Crea/actualiza la fila de tokens con la respuesta de Webex."""
    from backend.modules.notificaciones.models import WebexOAuthToken

    row = _obtener_row(db) or WebexOAuthToken(proposito=PROPOSITO_READER)
    ahora = utc_now()
    row.access_token = data["access_token"]
    if data.get("refresh_token"):
        row.refresh_token = data["refresh_token"]
    if data.get("expires_in"):
        row.expires_at = ahora + timedelta(seconds=int(data["expires_in"]))
    if data.get("refresh_token_expires_in"):
        row.refresh_expires_at = ahora + timedelta(seconds=int(data["refresh_token_expires_in"]))
    if usuario:
        row.updated_by = usuario
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def exchange_code(db: Session, code: str, usuario: Optional[str] = None, redirect_uri: Optional[str] = None):
    """
    Canjea el authorization code por tokens y los persiste.
    redirect_uri debe ser el mismo usado al generar la URL de autorización.
    """
    if not esta_configurado():
        raise WebexOAuthError("Integración lectora sin configurar (WEBEX_READER_CLIENT_ID/SECRET)")
    uri = _resolver_redirect_uri(redirect_uri)
    if not uri:
        raise WebexOAuthError("No se pudo determinar el redirect URI del callback OAuth")
    data = _pedir_token(
        {
            "grant_type": "authorization_code",
            "client_id": settings.webex_reader_client_id,
            "client_secret": settings.webex_reader_client_secret,
            "code": code,
            "redirect_uri": uri,
        }
    )
    row = _guardar_tokens(db, data, usuario=usuario)

    # Identificar la cuenta conectada (best effort, solo informativo)
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                WEBEX_PEOPLE_ME_URL,
                headers={"Authorization": f"Bearer {row.access_token}"},
            )
        if response.is_success:
            persona = response.json()
            row.account_email = (persona.get("emails") or [None])[0]
            row.account_nombre = persona.get("displayName")
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠️ No se pudo identificar la cuenta lectora de Webex: {e}")

    logger.info(f"✅ Cuenta lectora de Webex conectada: {row.account_email or 'desconocida'}")
    return row


def refresh(db: Session):
    """Renueva el access token usando el refresh token guardado."""
    row = _obtener_row(db)
    if not row or not row.refresh_token:
        raise WebexOAuthError("No hay cuenta lectora conectada; autorizá la integración")
    data = _pedir_token(
        {
            "grant_type": "refresh_token",
            "client_id": settings.webex_reader_client_id,
            "client_secret": settings.webex_reader_client_secret,
            "refresh_token": row.refresh_token,
        }
    )
    return _guardar_tokens(db, data)


def get_reader_access_token(db: Session) -> Optional[str]:
    """
    Access token vigente de la cuenta lectora, refrescando si está por vencer.
    Devuelve None si no hay cuenta conectada o el refresh falla.
    """
    row = _obtener_row(db)
    if not row or not row.access_token:
        return None
    if row.expires_at and row.expires_at - _MARGEN_REFRESH > utc_now():
        return row.access_token
    try:
        return refresh(db).access_token
    except WebexOAuthError as e:
        logger.error(f"❌ No se pudo refrescar el token lector de Webex: {e}")
        return None


def estado(db: Session, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """Estado de la integración para mostrar en la UI."""
    row = _obtener_row(db)
    return {
        "configurado": esta_configurado(),
        "conectado": bool(row and row.refresh_token),
        "account_email": row.account_email if row else None,
        "expira": row.expires_at.isoformat() if row and row.expires_at else None,
        "authorize_url": authorize_url(redirect_uri),
    }
