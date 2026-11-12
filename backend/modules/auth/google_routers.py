"""Rutas del ingreso con Google (F22). Las llama el frontend: el navegador nunca habla con estas rutas."""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.modules.auth import google
from backend.modules.auth.routers import con_refresco, ingresar

router = APIRouter(prefix="/auth/google", tags=["autenticación"])

_AZAR = r"^[A-Za-z0-9_-]{16,200}$"  # state y nonce: los arma el frontend con secrets.token_urlsafe


class PedidoAutorizacion(BaseModel):
    state: str = Field(pattern=_AZAR)
    nonce: str = Field(pattern=_AZAR)
    code_challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")  # S256, RFC 7636


class PedidoIngreso(BaseModel):
    code: str = Field(min_length=1, max_length=2048, pattern=r"^[\x21-\x7e]+$")
    code_verifier: str = Field(pattern=r"^[A-Za-z0-9._~-]{43,128}$")
    nonce: str = Field(pattern=_AZAR)


def _encendido():
    if not google.disponible():
        raise HTTPException(status_code=404, detail="El ingreso con Google no está configurado")


@router.get("/disponible")
def disponible(db: Session = Depends(get_db)):
    """Si el login muestra el botón «Entrar con Google» y con qué dominio."""
    if not google.disponible():
        return {"disponible": False}
    return {"disponible": True, "dominio": google.dominio_google(db)}


@router.post("/autorizacion", dependencies=[Depends(_encendido)])
def autorizacion(pedido: PedidoAutorizacion, db: Session = Depends(get_db)):
    """La URL de Google a la que el frontend lleva el navegador."""
    return {"url": google.url_autorizacion(db, pedido.state, pedido.nonce, pedido.code_challenge)}


@router.post("/ingreso", dependencies=[Depends(_encendido)])
def ingreso(
    pedido: PedidoIngreso,
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str | None = Cookie(None),
):
    """La vuelta de Google: lo mismo que POST /auth/login (2FA según google_login_requiere_2fa, empresas y token)."""
    try:
        usuario = google.identificar(db, pedido.code, pedido.code_verifier, pedido.nonce)
    except google.IngresoRechazado as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detalle)
    return con_refresco(ingresar(db, usuario, pedir_2fa=google.requiere_2fa(db)), response, db, refresh_token)
