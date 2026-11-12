"""Id de pedido, X-Request-ID (F06-P06): para seguir un pedido en los logs de punta a punta.

Cada pedido a la API lleva un id. Si llega en X-Request-ID (el de Flask, y en v2 el que mande la SPA) se usa ese; si
no, o si no tiene forma de id, se genera uno. La respuesta lo devuelve en X-Request-ID y cada línea de log del pedido
lo lleva (logging_config agrega `id_pedido` al formato). Lo que corre fuera de un pedido (el programador, los hilos)
loguea «-».
"""

import contextvars
import logging
import re
import uuid

ID_PEDIDO: contextvars.ContextVar[str] = contextvars.ContextVar("id_pedido", default="-")
CABECERA = "X-Request-ID"
_VALIDO = re.compile(r"[A-Za-z0-9._\-]{1,128}")


def id_para(entrante: str | None) -> str:
    """El id que llegó, si tiene forma de id (hasta 128 de letras, números, punto, guion y guion bajo); si no, uno
    nuevo. Así un valor raro no termina en los logs ni en las cabeceras."""
    if entrante and _VALIDO.fullmatch(entrante):
        return entrante
    return uuid.uuid4().hex


class IdDePedido:
    """Middleware ASGI: fija el id del pedido mientras corre y lo devuelve en la respuesta."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        entrante = next((v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"x-request-id"), None)
        ident = id_para(entrante)
        token = ID_PEDIDO.set(ident)

        async def enviar(mensaje):
            if mensaje["type"] == "http.response.start":
                cabeceras = [(k, v) for k, v in mensaje.get("headers", []) if k.lower() != b"x-request-id"]
                mensaje = {**mensaje, "headers": [*cabeceras, (b"x-request-id", ident.encode())]}
            await send(mensaje)

        try:
            await self.app(scope, receive, enviar)
        finally:
            ID_PEDIDO.reset(token)


class FiltroIdDePedido(logging.Filter):
    """Pone el id del pedido en cada registro de log (`%(id_pedido)s`)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.id_pedido = ID_PEDIDO.get()
        return True
