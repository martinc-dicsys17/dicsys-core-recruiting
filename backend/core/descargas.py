"""URLs firmadas de corta duración para descargas (F07-P06).

Un <img src> o un <a href> no pueden mandar el Bearer que la SPA tiene en memoria. Para eso la SPA pide con su Bearer
una URL firmada de la ruta que quiere bajar (POST /auth/descargas) y usa esa URL: `ruta?firma=<token>`. El token dice
«esta persona, en esta empresa, puede hacer GET de esta ruta exacta durante unos minutos». El middleware lo cambia por
el Bearer de esa persona y el endpoint corre como siempre, con sus permisos y su auditoría: firmar no da más acceso que
el que la persona ya tiene. Una URL que se filtra sirve solo para esa ruta y hasta que vence.
"""

import json
from datetime import timedelta
from urllib.parse import parse_qs

from fastapi import HTTPException

from backend.core.config import settings
from backend.core.tokens import crear_token, decodificar

PROPOSITO = "descarga"
VIGENCIA = timedelta(minutes=5)
DE_LA_SESION = ("sub", "user_id", "rol", "empresa_id")


def rutas_firmables() -> tuple[str, ...]:
    return (f"{settings.api_v1_prefix}/", "/storage/")


def firmar(ruta: str, sesion: dict) -> str:
    """El token de una URL firmada: los datos de la sesión que pide, la ruta y el vencimiento corto."""
    datos = {k: sesion[k] for k in DE_LA_SESION if k in sesion}
    return crear_token({**datos, "purpose": PROPOSITO, "ruta": ruta}, VIGENCIA)


class FirmaDeDescarga:
    """Middleware ASGI: un GET con `?firma=` válida para su ruta pasa con el Bearer de quien la firmó. Una firma
    vencida, adulterada o de otra ruta da 401. En otros métodos la firma no cuenta."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in ("GET", "HEAD"):
            firma = parse_qs(scope.get("query_string", b"").decode()).get("firma")
            if firma:
                try:
                    payload = decodificar(firma[0], (PROPOSITO,), detalle="URL firmada inválida o vencida")
                    if payload.get("purpose") != PROPOSITO or payload.get("ruta") != scope["path"]:
                        raise HTTPException(status_code=401, detail="URL firmada inválida o vencida")
                except HTTPException as e:
                    await _responder(send, e.status_code, {"detail": e.detail})
                    return
                acceso = crear_token({k: payload[k] for k in DE_LA_SESION if k in payload})
                cabeceras = [(k, v) for k, v in scope["headers"] if k.lower() != b"authorization"]
                scope = {**scope, "headers": [*cabeceras, (b"authorization", f"Bearer {acceso}".encode())]}
        await self.app(scope, receive, send)


async def _responder(send, status: int, cuerpo: dict) -> None:
    contenido = json.dumps(cuerpo).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(contenido)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": contenido})
