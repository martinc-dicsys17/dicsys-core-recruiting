"""Lector de Google Sheets: ID desde el link, lectura de la hoja y errores aptos para UI."""

import httpx
import pytest

from backend.core.google_sheets import ErrorSheets, id_desde_url, leer_hoja

pytestmark = pytest.mark.services

ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
URL = f"https://docs.google.com/spreadsheets/d/{ID}/edit#gid=0"


def _cliente(manejador):
    return httpx.Client(transport=httpx.MockTransport(manejador))


def test_id_desde_el_link_o_suelto():
    assert id_desde_url(URL) == ID
    assert id_desde_url(f"  {ID}  ") == ID


def test_link_que_no_es_de_sheets_se_rechaza():
    with pytest.raises(ErrorSheets, match="no es de un Google Sheet"):
        id_desde_url("https://drive.google.com/file/d/abc/view")


def test_lee_la_hoja_pedida_con_el_token_y_como_texto():
    pedidos = []

    def manejador(request):
        pedidos.append(request)
        return httpx.Response(
            200, json={"values": [["Razón Social", "Referente"], ["ODOO", "Vega Federico"], ["Solo"]]}
        )

    filas = leer_hoja(URL, "Listado Proveedores", cliente=_cliente(manejador), token="tok")

    assert filas == [["Razón Social", "Referente"], ["ODOO", "Vega Federico"], ["Solo"]]
    pedido = pedidos[0]
    assert pedido.headers["Authorization"] == "Bearer tok"
    assert f"/spreadsheets/{ID}/values/" in str(pedido.url)
    assert "%27Listado%20Proveedores%27" in str(pedido.url)
    assert pedido.url.params["valueRenderOption"] == "FORMATTED_VALUE"


def test_hoja_vacia_devuelve_lista_vacia():
    filas = leer_hoja(URL, "Hoja", cliente=_cliente(lambda r: httpx.Response(200, json={})), token="tok")
    assert filas == []


@pytest.mark.parametrize(
    "estado, cuerpo, mensaje",
    [
        (403, {"error": {"message": "The caller does not have permission"}}, "compartirlo con su mail"),
        (
            403,
            {"error": {"message": "Google Sheets API has not been used in project 1 before or it is disabled"}},
            "no está habilitada",
        ),
        (404, {"error": {"message": "Requested entity was not found."}}, "No se encontró"),
        (400, {"error": {"message": "Unable to parse range: 'Otra'"}}, "no tiene la hoja «Otra»"),
        (500, {}, "respondió 500"),
    ],
)
def test_errores_de_google_se_traducen(estado, cuerpo, mensaje):
    cliente = _cliente(lambda r: httpx.Response(estado, json=cuerpo))
    with pytest.raises(ErrorSheets, match=mensaje):
        leer_hoja(URL, "Otra", cliente=cliente, token="tok")


def test_falla_de_conexion_se_traduce():
    def manejador(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(ErrorSheets, match="No se pudo conectar"):
        leer_hoja(URL, "Hoja", cliente=_cliente(manejador), token="tok")


@pytest.mark.parametrize(
    "propia, bucket, esperada",
    [
        ("/secrets/sheets.json", "/secrets/gcs.json", "/secrets/sheets.json"),
        ("", "/secrets/gcs.json", "/secrets/gcs.json"),
    ],
)
def test_usa_la_cuenta_de_sheets_y_si_falta_la_del_bucket(monkeypatch, propia, bucket, esperada):
    from google.oauth2 import service_account

    from backend.core import google_sheets

    leidas = []

    class Credenciales:
        token = "tok"

        def refresh(self, _request):
            pass

    def desde_archivo(ruta, scopes):
        leidas.append((ruta, scopes))
        return Credenciales()

    monkeypatch.setattr(google_sheets.settings, "google_sheets_credentials_path", propia)
    monkeypatch.setattr(google_sheets.settings, "gcs_credentials_path", bucket)
    monkeypatch.setattr(service_account.Credentials, "from_service_account_file", desde_archivo)

    assert google_sheets._token() == "tok"
    assert leidas == [(esperada, [google_sheets.SCOPE])]


def test_cuenta_de_servicio_sale_del_json_de_credenciales(monkeypatch, tmp_path):
    from backend.core import google_sheets

    archivo = tmp_path / "cuenta.json"
    archivo.write_text('{"client_email": "sheets-lectura@proyecto.iam.gserviceaccount.com"}', encoding="utf-8")
    monkeypatch.setattr(google_sheets.settings, "google_sheets_credentials_path", str(archivo))
    assert google_sheets.cuenta_de_servicio() == "sheets-lectura@proyecto.iam.gserviceaccount.com"

    monkeypatch.setattr(google_sheets.settings, "google_sheets_credentials_path", str(tmp_path / "no-existe.json"))
    assert google_sheets.cuenta_de_servicio() is None
    monkeypatch.setattr(google_sheets.settings, "google_sheets_credentials_path", "")
    monkeypatch.setattr(google_sheets.settings, "gcs_credentials_path", "")
    assert google_sheets.cuenta_de_servicio() is None
