"""
Lectura de Google Sheets, solo lectura.

Usa una cuenta de servicio propia, sin roles en el proyecto
(sheets-lectura@dicsys-core-public): el JSON de GOOGLE_SHEETS_CREDENTIALS_PATH.
Si está vacío, cae en la del bucket (GCS_CREDENTIALS_PATH) y, si esa también,
en las credenciales del entorno (ADC). Para leer un Sheet hay que compartirlo
con el mail de la cuenta como Lector; la API de Google Sheets ya está
habilitada en dicsys-core-public.

Nada de este módulo escribe en Google: el scope es spreadsheets.readonly.
"""

import json
import logging
import re
from typing import List, Optional
from urllib.parse import quote

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
API_URL = "https://sheets.googleapis.com/v4/spreadsheets"
TIMEOUT = 30.0  # segundos por request a Google

_PATRON_ID = re.compile(r"/spreadsheets/d/([\w-]+)")
_PATRON_ID_SUELTO = re.compile(r"^[\w-]{20,}$")


class ErrorSheets(Exception):
    """No se pudo leer el Sheet (mensaje apto para mostrar en la UI)."""


def id_desde_url(url_o_id: str) -> str:
    """ID del Sheet a partir de su link (docs.google.com/spreadsheets/d/<id>/...) o del ID suelto."""
    valor = (url_o_id or "").strip()
    coincidencia = _PATRON_ID.search(valor)
    if coincidencia:
        return coincidencia.group(1)
    if _PATRON_ID_SUELTO.match(valor):
        return valor
    raise ErrorSheets("El link no es de un Google Sheet (docs.google.com/spreadsheets/d/...).")


def _ruta_credenciales() -> str:
    return settings.google_sheets_credentials_path or settings.gcs_credentials_path


def cuenta_de_servicio() -> Optional[str]:
    """Mail de la cuenta con la que se lee: es con quien hay que compartir el Sheet."""
    ruta = _ruta_credenciales()
    if not ruta:
        return None
    try:
        with open(ruta, encoding="utf-8") as archivo:
            return json.load(archivo).get("client_email")
    except OSError, ValueError, AttributeError:
        return None


def _token() -> str:
    """Token de acceso de la cuenta de servicio con el scope de solo lectura."""
    from google.auth import default as credenciales_del_entorno
    from google.auth.exceptions import GoogleAuthError
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    ruta = _ruta_credenciales()
    try:
        if ruta:
            credenciales = service_account.Credentials.from_service_account_file(ruta, scopes=[SCOPE])
        else:
            credenciales, _ = credenciales_del_entorno(scopes=[SCOPE])
        credenciales.refresh(Request())
    except (GoogleAuthError, OSError, ValueError) as exc:
        logger.error(f"No se pudo autenticar la cuenta de servicio de Google: {exc}")
        raise ErrorSheets(
            "No se pudo autenticar la cuenta de servicio de Google: revisá GOOGLE_SHEETS_CREDENTIALS_PATH."
        ) from exc
    return credenciales.token


def _error(respuesta: httpx.Response, hoja: str) -> ErrorSheets:
    try:
        motivo = respuesta.json()["error"]["message"]
    except ValueError, KeyError, TypeError:
        motivo = ""
    if respuesta.status_code == 403:
        if "disabled" in motivo or "has not been used" in motivo:
            return ErrorSheets("La API de Google Sheets no está habilitada en el proyecto de la cuenta de servicio.")
        return ErrorSheets(
            "La cuenta de servicio no tiene acceso al Sheet: hay que compartirlo con su mail como Lector."
        )
    if respuesta.status_code == 404:
        return ErrorSheets("No se encontró el Google Sheet: revisá el link.")
    if respuesta.status_code == 400 and "parse range" in motivo:
        return ErrorSheets(f"El Sheet no tiene la hoja «{hoja}».")
    return ErrorSheets(f"Google Sheets respondió {respuesta.status_code}.")


def leer_hoja(
    url_o_id: str,
    hoja: str,
    *,
    cliente: Optional[httpx.Client] = None,
    token: Optional[str] = None,
) -> List[List[str]]:
    """
    Devuelve las filas de la hoja como texto, tal cual se ven en el Sheet.

    Cada fila es una lista de celdas; la API omite las celdas vacías del final,
    así que las filas pueden tener largos distintos. `cliente` y `token` se
    inyectan en los tests.
    """
    id_sheet = id_desde_url(url_o_id)
    rango = quote("'" + hoja.replace("'", "''") + "'", safe="")
    url = f"{API_URL}/{id_sheet}/values/{rango}"
    cabeceras = {"Authorization": f"Bearer {token or _token()}"}
    parametros = {"valueRenderOption": "FORMATTED_VALUE", "majorDimension": "ROWS"}

    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=TIMEOUT)
    try:
        respuesta = cliente.get(url, headers=cabeceras, params=parametros)
    except httpx.HTTPError as exc:
        logger.error(f"Error de conexión con Google Sheets: {exc}")
        raise ErrorSheets(f"No se pudo conectar con Google Sheets ({exc.__class__.__name__}).") from exc
    finally:
        if propio:
            cliente.close()

    if respuesta.status_code != 200:
        raise _error(respuesta, hoja)
    filas = respuesta.json().get("values", [])
    return [[str(celda) for celda in fila] for fila in filas]
