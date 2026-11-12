"""Límite de intentos del ingreso (F07-P07): Flask le pasa al backend la IP del navegador y muestra el 429."""

import httpx
import pytest

from app import create_app

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]

FRENADO = {"detail": "Demasiados intentos. Probá de nuevo en 7 minutos."}


@pytest.fixture
def frenado(monkeypatch):
    """La app con el api_request real contra un backend que responde 429 a todo; anota cada pedido."""
    pedidos = []

    def backend(peticion):
        pedidos.append(peticion)
        return httpx.Response(429, json=FRENADO, headers={"Retry-After": "420"})

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    return app.test_client(), pedidos


def test_el_proxy_pasa_la_ip_del_navegador_y_devuelve_retry_after(frenado):
    cliente, pedidos = frenado

    respuesta = cliente.post(
        "/api/v1/auth/login",
        json={"email": "ana@dicsys.ai", "password": "x"},
        environ_base={"REMOTE_ADDR": "190.0.0.7"},
    )

    assert respuesta.status_code == 429 and respuesta.headers["Retry-After"] == "420"
    assert respuesta.json == FRENADO
    assert pedidos[-1].headers["X-Cliente-IP"] == "190.0.0.7"


def test_el_login_y_el_2fa_muestran_el_aviso_del_429(frenado):
    cliente, _ = frenado

    login = cliente.post("/login", data={"email": "ana@dicsys.ai", "password": "x"}, headers={"HX-Request": "true"})
    with cliente.session_transaction() as sesion:
        sesion["2fa_temp_token"] = "temp"
    segundo_factor = cliente.post("/login/2fa", data={"code": "123456"}, headers={"HX-Request": "true"})

    for respuesta in (login, segundo_factor):
        assert FRENADO["detail"] in respuesta.get_data(as_text=True)
