"""Contrato HTTP real del helper usado por los proxies de licencias."""

import json

import httpx
import pytest
from flask import request, session

from app import create_app

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


@pytest.fixture
def proxy_http(monkeypatch):
    solicitudes, respuestas = [], []

    def backend(peticion):
        solicitudes.append(peticion)
        respuesta = respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(
        config={
            "TESTING": True,
            "SECRET_KEY": "frontend-test-secret",
            "API_URL": "http://backend.test",
        }
    )
    return app, solicitudes, respuestas


@pytest.mark.parametrize(
    "metodo,token", [("GET", None), ("POST", "test-token"), ("PUT", "test-token"), ("DELETE", "test-token")]
)
def test_proxy_conserva_metodo_payload_token_y_json(proxy_http, metodo, token):
    app, solicitudes, respuestas = proxy_http
    respuestas.append(httpx.Response(200, json={"id": "licencia-id"}))

    with app.test_request_context("/innovacion/licencias"):
        datos, status = app.config["api_request"](metodo, "/innovacion/licencias", {"costo_mensual": 10}, token)

    assert (datos, status) == ({"id": "licencia-id"}, 200)
    peticion = solicitudes[0]
    assert peticion.method == metodo
    assert str(peticion.url) == "http://backend.test/api/v1/innovacion/licencias"
    assert peticion.headers.get("Authorization") == ("Bearer test-token" if token else None)
    if metodo in ("POST", "PUT", "DELETE"):
        # el DELETE también lleva el cuerpo: la revocación de licencias y desactivar 2FA lo necesitan (PG-05)
        assert json.loads(peticion.read()) == {"costo_mensual": 10}
    else:
        assert peticion.read() == b""


def test_delete_sin_datos_sale_sin_cuerpo(proxy_http):
    app, solicitudes, respuestas = proxy_http
    respuestas.append(httpx.Response(204))

    with app.test_request_context("/innovacion/licencias"):
        app.config["api_request"]("DELETE", "/innovacion/licencias/x", token="test-token")

    assert solicitudes[0].method == "DELETE"
    assert solicitudes[0].read() == b""


@pytest.mark.parametrize("cuerpo", [{"licencia_ids": ["a", "b"]}, None])
def test_proxy_api_v1_reenvia_el_cuerpo_del_delete(proxy_http, cuerpo):
    app, solicitudes, respuestas = proxy_http
    respuestas.append(httpx.Response(200, json={"ok": True}))
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["token"] = "test-token"

    r = (
        cliente.delete("/api/v1/soporte/marcas/m-1", json=cuerpo)
        if cuerpo
        else cliente.delete("/api/v1/soporte/marcas/m-1")
    )

    assert r.status_code == 200
    peticion = solicitudes[0]
    assert peticion.method == "DELETE" and str(peticion.url) == "http://backend.test/api/v1/soporte/marcas/m-1"
    assert (json.loads(peticion.read()) if cuerpo else peticion.read()) == (cuerpo or b"")


@pytest.mark.parametrize(
    "ruta,limpia", [("/innovacion/licencias", True), ("/login/2fa", False), ("/login/2fa-setup", False)]
)
def test_token_expirado_limpia_sesion_salvo_flujo_2fa(proxy_http, ruta, limpia):
    app, _, respuestas = proxy_http
    respuestas.append(httpx.Response(401, json={"detail": "Token expirado"}))

    with app.test_request_context(ruta):
        session["token"] = "test-token"
        datos, status = app.config["api_request"]("GET", "/innovacion/licencias", token="test-token")
        assert ("token" not in session) is limpia
        assert getattr(request, "_session_cleared_by_401", False) is limpia

    assert status == 401
    assert datos == {"detail": "Token expirado"}


@pytest.mark.parametrize("respuesta", [httpx.ConnectError("offline"), httpx.Response(200, content=b"no es JSON")])
def test_error_de_transporte_o_json_es_visible_sin_excepcion(proxy_http, respuesta):
    app, solicitudes, respuestas = proxy_http
    respuestas.append(respuesta)

    with app.test_request_context("/innovacion/licencias"):
        datos, status = app.config["api_request"]("GET", "/innovacion/licencias")

    assert status == 500
    assert datos == {"error": "Error de comunicación con el servidor"}
    assert len(solicitudes) == 1


def test_metodo_no_soportado_no_envia_peticion(proxy_http):
    app, solicitudes, _ = proxy_http

    with app.test_request_context("/innovacion/licencias"):
        datos, status = app.config["api_request"]("PATCH", "/innovacion/licencias")

    assert status == 500
    assert datos == {"error": "Error de comunicación con el servidor"}
    assert solicitudes == []


def test_proxy_reenvia_ip_y_navegador_del_usuario(proxy_http):
    app, solicitudes, respuestas = proxy_http
    respuestas.append(httpx.Response(200, json={}))

    with app.test_request_context(
        "/administracion/proveedores",
        environ_base={"REMOTE_ADDR": "203.0.113.7"},
        headers={"User-Agent": "Navegador/1.0"},
    ):
        app.config["api_request"]("GET", "/proveedores", token="test-token")

    peticion = solicitudes[0]
    assert peticion.headers.get("X-Cliente-IP") == "203.0.113.7"
    assert peticion.headers.get("X-Cliente-User-Agent") == "Navegador/1.0"
