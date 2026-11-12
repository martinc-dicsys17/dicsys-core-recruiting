"""
Sesión vencida: cada pedido va al login a su manera.

El indicador de la campana se refresca solo cada 60 s con htmx. Con un 302 el navegador
seguía la redirección y htmx metía la pantalla de login adentro del encabezado; ahora
recibe HX-Redirect y lleva la página entera al login.
"""

import httpx
import pytest

from app import create_app
from modulos.auth_helpers import SESION_VENCIDA

pytestmark = [pytest.mark.frontend, pytest.mark.smoke]

INDICADOR = "/notificaciones-internas/indicador"


def test_htmx_sin_sesion_lleva_la_pagina_entera_al_login(frontend_client):
    respuesta = frontend_client.get(INDICADOR, headers={"HX-Request": "true"})

    assert respuesta.status_code == 200
    assert respuesta.headers["HX-Redirect"] == "/login"
    assert respuesta.get_data(as_text=True) == ""  # nada que htmx pueda meter en el elemento


def test_fetch_json_sin_sesion_responde_401_con_el_motivo(frontend_client):
    respuesta = frontend_client.get("/tareas-programadas/api", headers={"Accept": "application/json"})

    assert respuesta.status_code == 401
    assert respuesta.json == {"detail": SESION_VENCIDA}


def test_navegacion_sin_sesion_sigue_redirigiendo(frontend_client):
    respuesta = frontend_client.get("/tareas-programadas")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")


def test_token_vencido_en_el_indicador_lleva_al_login_sin_meterlo_en_el_encabezado(monkeypatch):
    """El backend responde 401 (JWT vencido) mientras la campana se refresca sola."""
    cliente_http = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: cliente_http(
            transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"detail": "Token expirado"})), **kwargs
        ),
    )
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["token"] = "vencido"
        sesion["user"] = {"id": "u1", "email": "ana@dicsys.com", "rol": "usuario"}

    respuesta = cliente.get(INDICADOR, headers={"HX-Request": "true"})

    assert respuesta.status_code == 200 and respuesta.headers["HX-Redirect"] == "/login"
    assert respuesta.get_data(as_text=True) == ""
    with cliente.session_transaction() as sesion:
        assert "token" not in sesion  # la sesión quedó limpia
