"""Puente de sesión (F07-P05): Flask pasa al navegador la cookie del refresh que emite el backend y la usa en el logout."""

import httpx
import pytest

from app import create_app

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]

EMITIDA = "refresh_token=r-1; HttpOnly; Max-Age=604800; Path=/api/v1/auth; SameSite=lax; Secure"
ROTADA = "refresh_token=r-2; HttpOnly; Max-Age=604800; Path=/api/v1/auth; SameSite=lax; Secure"
BORRADA = 'refresh_token=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; Max-Age=0; Path=/api/v1/auth; SameSite=lax; Secure'
SESION = {
    "access_token": "jwt",
    "user": {"email": "ana@dicsys.ai"},
    "empresas": [{"id": "e-1", "razon_social": "Dicsys", "nombre_fantasia": "Dicsys"}],
    "requiere_seleccion_empresa": False,
}


@pytest.fixture
def con_api_real(monkeypatch):
    """La app con el api_request real contra un backend falso que puede mandar Set-Cookie; anota cada pedido."""
    respuestas, pedidos = {}, []

    def backend(peticion):
        pedidos.append(peticion)
        payload, status, cookie = respuestas.get(
            (peticion.method, peticion.url.path.removeprefix("/api/v1")), ({}, 200, None)
        )
        return httpx.Response(status, json=payload, headers=[("set-cookie", cookie)] if cookie else [])

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    return app.test_client(), respuestas, pedidos


def _set_cookies(respuesta) -> list[str]:
    return [v for k, v in respuesta.headers.items() if k.lower() == "set-cookie" and v.startswith("refresh_token=")]


def test_el_login_pasa_la_cookie_del_refresh_al_navegador_y_la_guarda_para_el_logout(con_api_real):
    cliente, respuestas, pedidos = con_api_real
    respuestas[("POST", "/auth/login")] = (SESION, 200, EMITIDA)

    respuesta = cliente.post("/login", data={"email": "ana@dicsys.ai", "password": "x"})

    assert respuesta.status_code == 302
    assert _set_cookies(respuesta) == [EMITIDA]
    with cliente.session_transaction() as sesion:
        assert sesion["refresh"] == "r-1" and sesion["token"] == "jwt"
    login = next(p for p in pedidos if p.url.path == "/api/v1/auth/login")
    assert login.headers["X-Requested-With"] == "XMLHttpRequest" and "cookie" not in login.headers


def test_el_logout_cierra_la_sesion_en_el_backend_y_borra_la_cookie(con_api_real):
    cliente, respuestas, pedidos = con_api_real
    respuestas[("POST", "/auth/login")] = (SESION, 200, EMITIDA)
    respuestas[("POST", "/auth/logout")] = ({}, 204, BORRADA)
    cliente.post("/login", data={"email": "ana@dicsys.ai", "password": "x"})

    respuesta = cliente.get("/logout")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
    assert _set_cookies(respuesta) == [BORRADA]
    logout = next(p for p in pedidos if p.url.path == "/api/v1/auth/logout")
    assert logout.headers["Cookie"] == "refresh_token=r-1" and logout.headers["X-Requested-With"] == "XMLHttpRequest"
    with cliente.session_transaction() as sesion:
        assert "refresh" not in sesion and "token" not in sesion


def test_sin_refresh_en_la_sesion_el_logout_no_llama_al_backend(con_api_real):
    cliente, _, pedidos = con_api_real

    respuesta = cliente.get("/logout")

    assert respuesta.status_code == 302 and not pedidos and not _set_cookies(respuesta)


def test_el_proxy_lleva_la_cookie_y_el_csrf_al_backend_y_trae_la_cookie_rotada(con_api_real):
    cliente, respuestas, pedidos = con_api_real
    respuestas[("POST", "/auth/refresh")] = (
        {"access_token": "jwt-2", "token_type": "bearer", "expires_in": 1800},
        200,
        ROTADA,
    )
    cliente.set_cookie("refresh_token", "r-1", path="/api/v1/auth")

    respuesta = cliente.post("/api/v1/auth/refresh", headers={"X-Requested-With": "XMLHttpRequest"})

    assert respuesta.status_code == 200 and respuesta.json["access_token"] == "jwt-2"
    assert _set_cookies(respuesta) == [ROTADA]
    refresh = pedidos[-1]
    assert refresh.headers["Cookie"] == "refresh_token=r-1" and refresh.headers["X-Requested-With"] == "XMLHttpRequest"


def test_el_proxy_no_manda_la_cookie_del_refresh_fuera_de_auth(con_api_real):
    cliente, _, pedidos = con_api_real
    cliente.set_cookie("refresh_token", "r-1", path="/")

    cliente.get("/api/v1/usuarios")

    assert "cookie" not in pedidos[-1].headers
