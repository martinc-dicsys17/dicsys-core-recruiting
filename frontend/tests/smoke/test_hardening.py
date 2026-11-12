"""Hardening del frontend (F01): debug apagado, SECRET_KEY obligatoria, cookies seguras,
mutaciones solo desde el propio host y sin CORS abierto."""

import pytest

from app import create_app
from tests.fakes import FakeApi

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


def _entorno(monkeypatch, **extra):
    """Entorno mínimo de producción; `extra` pisa o agrega variables."""
    for variable in ("DEBUG", "TESTING", "SESSION_COOKIE_SECURE", "ORIGIN_CHECK"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("SECRET_KEY", "clave-de-prueba")
    monkeypatch.setenv("ENVIRONMENT", "production")
    for nombre, valor in extra.items():
        monkeypatch.setenv(nombre, valor)


def test_debug_apagado_por_defecto_y_forzado_fuera_de_development(monkeypatch):
    _entorno(monkeypatch)
    assert create_app(api_request_func=FakeApi()).config["DEBUG"] is False

    _entorno(monkeypatch, DEBUG="True")
    assert create_app(api_request_func=FakeApi()).config["DEBUG"] is False

    _entorno(monkeypatch, DEBUG="True", ENVIRONMENT="development")
    assert create_app(api_request_func=FakeApi()).config["DEBUG"] is True


def test_sin_secret_key_no_arranca(monkeypatch):
    _entorno(monkeypatch)
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(api_request_func=FakeApi())


def test_secret_key_del_template_no_arranca_en_produccion(monkeypatch):
    _entorno(monkeypatch, SECRET_KEY="tu-clave-secreta-aqui-cambiar-en-produccion")
    with pytest.raises(RuntimeError, match="ejemplo del .env.template"):
        create_app(api_request_func=FakeApi())

    # en desarrollo sí arranca: es el valor que trae el .env copiado del template
    _entorno(monkeypatch, SECRET_KEY="tu-clave-secreta-aqui-cambiar-en-produccion", ENVIRONMENT="development")
    assert create_app(api_request_func=FakeApi()).config["SECRET_KEY"]


def test_cookies_de_sesion_seguras_fuera_de_development(monkeypatch):
    _entorno(monkeypatch)
    config = create_app(api_request_func=FakeApi()).config
    assert config["SESSION_COOKIE_SECURE"] is True
    assert config["SESSION_COOKIE_HTTPONLY"] is True
    assert config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert config["PREFERRED_URL_SCHEME"] == "https"

    _entorno(monkeypatch, ENVIRONMENT="development")
    assert create_app(api_request_func=FakeApi()).config["SESSION_COOKIE_SECURE"] is False


@pytest.fixture
def cliente_con_chequeo(fake_api):
    # El login llama a la API: con credenciales rechazadas alcanza para distinguir 403 de "pasó".
    fake_api.respond("POST", "/auth/login", {"detail": "Credenciales inválidas"}, 401)
    app = create_app(
        config={
            "TESTING": True,
            "SECRET_KEY": "frontend-test-secret",
            "API_URL": "http://backend.test",
            "ORIGIN_CHECK": True,
        },
        api_request_func=fake_api,
    )
    return app.test_client()


@pytest.mark.parametrize(
    "cabeceras,rechazado",
    [
        ({"Origin": "https://evil.example"}, True),
        ({"Referer": "https://evil.example/pagina"}, True),
        ({"Origin": "null"}, True),
        ({}, True),
        ({"Origin": "http://localhost"}, False),
        ({"Referer": "http://localhost/login"}, False),
    ],
)
def test_mutaciones_solo_desde_el_propio_host(cliente_con_chequeo, cabeceras, rechazado):
    respuesta = cliente_con_chequeo.post(
        "/login",
        data={"email": "a@b.c", "password": "x"},
        headers=cabeceras,
    )
    assert (respuesta.status_code == 403) is rechazado


def test_el_canje_oidc_entre_servidores_no_pasa_por_el_chequeo_de_origen(cliente_con_chequeo, fake_api):
    """razorback canjea el código desde su servidor, sin Origin ni Referer (F21)."""
    fake_api.respond("POST", "/oidc/token", {"id_token": "jwt", "token_type": "Bearer"})
    respuesta = cliente_con_chequeo.post("/oidc/token", data={"grant_type": "authorization_code", "code": "c"})
    assert respuesta.status_code == 200 and respuesta.json["id_token"] == "jwt"
    # Las demás mutaciones siguen exigiendo el propio host
    assert cliente_con_chequeo.post("/login", data={"email": "a@b.c", "password": "x"}).status_code == 403


def test_get_no_pasa_por_el_chequeo_de_origen(cliente_con_chequeo):
    assert cliente_con_chequeo.get("/health").status_code == 200


def test_el_chequeo_queda_apagado_en_testing_salvo_pedido_explicito(frontend_client, fake_api):
    fake_api.respond("POST", "/auth/login", {"detail": "Credenciales inválidas"}, 401)
    respuesta = frontend_client.post("/login", data={"email": "a@b.c", "password": "x"})
    assert respuesta.status_code != 403


def test_sin_cabeceras_cors(frontend_client):
    respuesta = frontend_client.get("/health")
    assert "Access-Control-Allow-Origin" not in respuesta.headers
