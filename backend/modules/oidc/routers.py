"""API interna del proveedor OpenID Connect (F21). La usa el frontend, que publica los endpoints en core.dicsys.ai:

  GET  /oidc/configuracion   documento de discovery          (/.well-known/openid-configuration)
  GET  /oidc/jwks            claves públicas                 (/oidc/jwks)
  POST /oidc/validar         valida un pedido de autorización antes de pedir el login
  POST /oidc/autorizar       emite el código para la sesión de Core   (/oidc/authorize)
  POST /oidc/denegar         vuelta con access_denied (Cancelar, cuenta desactivada)
  POST /oidc/token           canje del código por el id_token          (/oidc/token)

Sin claves configuradas el proveedor está apagado y todo responde 404.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.core.tokens import decodificar
from backend.database import get_db
from backend.modules.oidc import claves, services
from backend.modules.oidc.services import ErrorOIDC
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/oidc", tags=["OpenID Connect"])
_bearer = HTTPBearer(auto_error=False)
SIN_CACHE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class _SinNul(BaseModel):
    """Postgres no acepta el carácter NUL en un texto: sin esto, un client_id con NUL llega a la consulta y da 500."""

    @field_validator("*")
    @classmethod
    def _sin_nul(cls, valor):
        if isinstance(valor, str) and "\x00" in valor:
            raise ValueError("no puede tener el carácter NUL")
        return valor


class PedidoAutorizacion(_SinNul):
    response_type: Optional[str] = Field(None, max_length=50)
    client_id: Optional[str] = Field(None, max_length=100)
    redirect_uri: Optional[str] = Field(None, max_length=500)
    scope: Optional[str] = Field(None, max_length=255)
    state: Optional[str] = Field(None, max_length=1000)
    nonce: Optional[str] = Field(None, max_length=255)
    code_challenge: Optional[str] = Field(None, max_length=128)
    code_challenge_method: Optional[str] = Field(None, max_length=20)


class PedidoToken(_SinNul):
    grant_type: Optional[str] = Field(None, max_length=50)
    code: Optional[str] = Field(None, max_length=200)
    redirect_uri: Optional[str] = Field(None, max_length=500)
    code_verifier: Optional[str] = Field(None, max_length=200)
    client_id: Optional[str] = Field(None, max_length=100)
    client_secret: Optional[str] = Field(None, max_length=200)


def _encendido():
    if not services.disponible():
        raise HTTPException(404, "El proveedor OpenID Connect no está configurado")


def usuario_de_sesion(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer), db: Session = Depends(get_db)
) -> Usuario:
    """La persona de la sesión de Core (el token que guarda el frontend). Un token intermedio del login (2FA) no vale.
    Una cuenta desactivada sí pasa: autorizar le responde access_denied."""
    if credentials is None:
        raise HTTPException(401, "Sin sesión de Dicsys Core")
    # Sin propósitos permitidos: decodificar rechaza los tokens intermedios del 2FA
    payload = decodificar(credentials.credentials, detalle="Sesión de Dicsys Core inválida o vencida")
    if not payload.get("user_id"):
        raise HTTPException(401, "Sesión de Dicsys Core incompleta")
    try:
        usuario = db.get(Usuario, uuid.UUID(str(payload["user_id"])))
    except ValueError:
        usuario = None
    if usuario is None:
        raise HTTPException(401, "Sesión de Dicsys Core inválida")
    return usuario


def _error(e: ErrorOIDC) -> JSONResponse:
    headers = dict(SIN_CACHE)
    if e.status == 401:
        headers["WWW-Authenticate"] = 'Basic realm="Dicsys Core"'
    return JSONResponse(status_code=e.status, content=e.respuesta(), headers=headers)


@router.get("/configuracion", dependencies=[Depends(_encendido)])
async def configuracion():
    """Documento de discovery (/.well-known/openid-configuration)."""
    return services.discovery()


@router.get("/jwks", dependencies=[Depends(_encendido)])
async def jwks():
    return claves.jwks()


@router.post("/validar", dependencies=[Depends(_encendido)])
async def validar(pedido: PedidoAutorizacion, db: Session = Depends(get_db)):
    """Valida el pedido antes de mandar a la persona al login: así un pedido inválido no la hace entrar en vano."""
    try:
        cliente = services.validar_pedido(db, pedido.model_dump())
    except ErrorOIDC as e:
        return _error(e)
    return {"cliente": cliente.nombre}


@router.post("/autorizar", dependencies=[Depends(_encendido)])
async def autorizar(
    pedido: PedidoAutorizacion, usuario: Usuario = Depends(usuario_de_sesion), db: Session = Depends(get_db)
):
    try:
        return {"redirect": services.autorizar(db, usuario, pedido.model_dump())}
    except ErrorOIDC as e:
        return _error(e)


@router.post("/denegar", dependencies=[Depends(_encendido)])
async def denegar(pedido: PedidoAutorizacion, db: Session = Depends(get_db)):
    try:
        return {"redirect": services.denegar(db, pedido.model_dump())}
    except ErrorOIDC as e:
        return _error(e)


@router.post("/token", dependencies=[Depends(_encendido)])
async def token(pedido: PedidoToken, db: Session = Depends(get_db)):
    try:
        return JSONResponse(content=services.canjear(db, pedido.model_dump()), headers=SIN_CACHE)
    except ErrorOIDC as e:
        return _error(e)
