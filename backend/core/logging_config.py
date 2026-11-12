"""Configuración de logging de la aplicación.

Sin esto los `logging.getLogger(__name__)` de los módulos quedan sin handler y
Python cae en su `lastResort`, que descarta todo lo que esté por debajo de
WARNING. En la práctica eso significa que ningún `logger.info` llega a la
consola ni a `docker logs` (por ejemplo, el aviso de certificación enviada a
Webex), y los `logger.error` salen sin timestamp ni nombre de módulo.

El `log_level` que se le pasa a uvicorn no cubre esto: configura los loggers de
uvicorn, no los de la aplicación.
"""

import logging
import os
import sys

from backend.core.config import settings
from backend.core.pedido import FiltroIdDePedido

# id_pedido: el X-Request-ID del pedido que estaba corriendo (F06-P06), «-» fuera de un pedido
_FORMATO = "%(asctime)s | %(levelname)-8s | %(id_pedido)s | %(name)s | %(message)s"
_FECHA = "%Y-%m-%d %H:%M:%S"

# Bibliotecas que loguean cada request/respuesta en INFO y tapan lo propio.
_RUIDOSAS = ("httpx", "httpcore", "urllib3", "google_genai", "watchfiles", "sqlalchemy.engine")


def _nivel_configurado() -> int:
    """Nivel del root logger: LOG_LEVEL si es válido, si no según `debug`."""
    nombre = os.getenv("LOG_LEVEL", "").strip().upper()
    if nombre:
        nivel = logging.getLevelName(nombre)
        if isinstance(nivel, int):
            return nivel
    return logging.DEBUG if settings.debug else logging.INFO


def configurar_logging() -> None:
    """Manda los logs de la aplicación a stdout, y por lo tanto a `docker logs`.

    Idempotente: con `uvicorn --reload` el módulo se reimporta y no hay que
    duplicar handlers (saldría cada línea repetida).
    """
    root = logging.getLogger()
    root.setLevel(_nivel_configurado())

    if not any(getattr(h, "_dicsys_consola", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMATO, datefmt=_FECHA))
        handler.addFilter(FiltroIdDePedido())
        handler._dicsys_consola = True
        root.addHandler(handler)

    for nombre in _RUIDOSAS:
        logging.getLogger(nombre).setLevel(logging.WARNING)
