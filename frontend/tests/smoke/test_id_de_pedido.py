"""X-Request-ID (F06-P06): Flask usa el id que llega o uno nuevo, lo pasa a la API y lo devuelve."""

import re

import httpx
import pytest

from app import create_app

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


@pytest.fixture
def con_api(monkeypatch):
    """La app con el api_request real contra un backend falso que responde 401; anota cada pedido."""
    pedidos = []

    def backend(peticion):
        pedidos.append(peticion)
        return httpx.Response(401, json={"detail": "Credenciales inválidas"})

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    return app.test_client(), pedidos


def test_el_id_que_llega_viaja_a_la_api_y_vuelve(con_api):
    cliente, pedidos = con_api

    r = cliente.post("/login", data={"email": "a@b.com", "password": "x"}, headers={"X-Request-ID": "spa-42"})

    assert r.headers["X-Request-ID"] == "spa-42"
    assert pedidos and all(p.headers["X-Request-ID"] == "spa-42" for p in pedidos)


def test_sin_id_genera_uno_y_es_el_mismo_en_la_api(con_api):
    cliente, pedidos = con_api

    r = cliente.post("/login", data={"email": "a@b.com", "password": "x"}, headers={"X-Request-ID": "con espacio"})

    ident = r.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", ident)
    assert pedidos[-1].headers["X-Request-ID"] == ident


def test_el_proxy_de_la_api_tambien_lo_pasa(con_api):
    cliente, pedidos = con_api

    r = cliente.get("/api/v1/menus", headers={"X-Request-ID": "proxy-7"})

    assert r.headers["X-Request-ID"] == "proxy-7" and pedidos[-1].headers["X-Request-ID"] == "proxy-7"
