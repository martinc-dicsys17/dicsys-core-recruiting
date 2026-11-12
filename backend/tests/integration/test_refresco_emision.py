"""Puente de sesión (F07-P05): con AUTH_REFRESH_ENABLED, cada sesión completa que emite la API lleva el refresh."""

from http.cookies import SimpleCookie

import pyotp
import pytest

from backend.core.config import settings
from backend.core.tokens import decodificar
from backend.modules.auth import refresco
from backend.tests.helpers.auth import auth_headers

XHR = {"X-Requested-With": "XMLHttpRequest"}
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


def _refresh(respuesta) -> str | None:
    galleta = SimpleCookie()
    for linea in respuesta.headers.get_list("set-cookie"):
        galleta.load(linea)
    return galleta[refresco.COOKIE].value if refresco.COOKIE in galleta else None


def _usar(client, token: str):
    return client.post("/api/v1/auth/refresh", headers={"Cookie": f"{refresco.COOKIE}={token}", **XHR})


@pytest.fixture
def puente(monkeypatch):
    monkeypatch.setattr(settings, "auth_refresh_enabled", True)


@pytest.fixture
def persona(data_factory):
    usuario = data_factory.usuario(password="clave-de-prueba")
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    return usuario, empresa


def _login(client, usuario):
    return client.post("/api/v1/auth/login", json={"email": usuario.email, "password": "clave-de-prueba"})


def test_con_el_flag_apagado_el_login_no_emite_refresh(client, persona):
    usuario, _ = persona
    r = _login(client, usuario)
    assert r.status_code == 200, r.text
    assert _refresh(r) is None


def test_login_con_una_empresa_emite_el_refresh_de_esa_sesion(client, puente, persona):
    usuario, empresa = persona

    r = _login(client, usuario)

    assert r.status_code == 200, r.text
    token = _refresh(r)
    assert token
    nuevo = _usar(client, token)
    assert nuevo.status_code == 200, nuevo.text
    datos = decodificar(nuevo.json()["access_token"])
    assert datos["user_id"] == str(usuario.id) and datos["empresa_id"] == str(empresa.id)


def test_con_varias_empresas_emite_al_elegir_y_cambiar_cierra_la_sesion_anterior(client, data_factory, puente, persona):
    usuario, empresa = persona
    otra = data_factory.empresa()
    data_factory.asignar_empresa(usuario, otra)

    r = _login(client, usuario)
    assert r.json()["requiere_seleccion_empresa"] is True and _refresh(r) is None, "falta elegir empresa"

    r = client.post(
        "/api/v1/auth/seleccionar-empresa",
        json={"empresa_id": str(empresa.id)},
        headers={"Authorization": f"Bearer {r.json()['access_token']}"},
    )
    assert r.status_code == 200, r.text
    primero = _refresh(r)

    r = client.post(
        "/api/v1/auth/cambiar-empresa",
        json={"empresa_id": str(otra.id)},
        headers={**auth_headers(usuario, empresa), "Cookie": f"{refresco.COOKIE}={primero}"},
    )
    assert r.status_code == 200, r.text
    segundo = _refresh(r)
    assert segundo and segundo != primero
    assert _usar(client, primero).status_code == 401, "la sesión de la empresa anterior quedó cerrada"
    nuevo = _usar(client, segundo)
    assert nuevo.status_code == 200 and decodificar(nuevo.json()["access_token"])["empresa_id"] == str(otra.id)


def test_con_2fa_emite_al_verificar_el_codigo(client, db_session, puente, persona):
    usuario, _ = persona
    usuario.totp_secret = pyotp.random_base32()
    usuario.totp_enabled = True
    db_session.commit()

    r = _login(client, usuario)
    assert r.json().get("requires_2fa") and _refresh(r) is None, "el 2FA en curso no emite"

    r = client.post(
        "/api/v1/auth/verify-2fa",
        json={"temp_token": r.json()["temp_token"], "code": pyotp.TOTP(usuario.totp_secret).now()},
    )

    assert r.status_code == 200, r.text
    assert _usar(client, _refresh(r)).status_code == 200


def test_refresh_cookie_secure_vacia_es_secure_segun_el_entorno():
    from backend.core.config import Settings

    base = {**settings.model_dump(), "environment": "production"}
    assert Settings(**{**base, "refresh_cookie_secure": ""}, _env_file=None).refresh_cookie_secure is None
    assert Settings(**{**base, "refresh_cookie_secure": "false"}, _env_file=None).refresh_cookie_secure is False


@pytest.mark.parametrize("secure", [True, False])
def test_la_cookie_respeta_refresh_cookie_secure(client, monkeypatch, puente, persona, secure):
    usuario, _ = persona
    monkeypatch.setattr(settings, "refresh_cookie_secure", secure)

    linea = next(c for c in _login(client, usuario).headers.get_list("set-cookie") if c.startswith("refresh_token="))

    assert ("Secure" in linea) is secure
