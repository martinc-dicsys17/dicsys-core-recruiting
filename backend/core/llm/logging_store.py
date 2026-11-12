"""
Persistencia en disco del raw de requests y responses a la LLM.

Estructura:
    {llm_storage_path}/requests/{yyyy-mm}/{id}.json
    {llm_storage_path}/responses/{yyyy-mm}/{id}.json

Las rutas que se guardan en la base de datos son relativas a la raíz de
almacenamiento (ej: "requests/2026-06/<uuid>.json").
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from backend.core.config import settings
from backend.core.utils import utc_now

logger = logging.getLogger(__name__)


def _root() -> Path:
    return Path(settings.llm_storage_path)


def init_directories() -> None:
    """Crea los directorios base de logs de LLM."""
    (_root() / "requests").mkdir(parents=True, exist_ok=True)
    (_root() / "responses").mkdir(parents=True, exist_ok=True)


def _serializar(payload: Any) -> str:
    """Serializa a JSON tolerando objetos no nativos (usa str como fallback)."""
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def guardar_request(request_id: str, payload: Any, periodo: Optional[str] = None) -> str:
    """Guarda el raw request y devuelve la ruta relativa."""
    return _guardar("requests", request_id, payload, periodo)


def guardar_response(request_id: str, payload: Any, periodo: Optional[str] = None) -> str:
    """Guarda el raw response y devuelve la ruta relativa."""
    return _guardar("responses", request_id, payload, periodo)


def _guardar(tipo: str, request_id: str, payload: Any, periodo: Optional[str]) -> str:
    periodo = periodo or utc_now().strftime("%Y-%m")
    carpeta = _root() / tipo / periodo
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{request_id}.json"
    archivo.write_text(_serializar(payload), encoding="utf-8")
    # Ruta relativa para guardar en la DB.
    return f"{tipo}/{periodo}/{request_id}.json"


def leer_raw(ruta_relativa: str) -> Optional[str]:
    """Lee el contenido de un archivo raw a partir de su ruta relativa."""
    if not ruta_relativa:
        return None
    archivo = (_root() / ruta_relativa).resolve()
    # Evitar path traversal: el archivo debe estar dentro de la raíz.
    try:
        archivo.relative_to(_root().resolve())
    except ValueError:
        logger.warning("Intento de acceso fuera de la raíz LLM: %s", ruta_relativa)
        return None
    if not archivo.exists():
        return None
    return archivo.read_text(encoding="utf-8")


def periodo_actual() -> str:
    """Devuelve el período (yyyy-mm) actual en UTC."""
    return utc_now().strftime("%Y-%m")
