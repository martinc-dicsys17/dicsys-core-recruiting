"""Endpoints públicos del proveedor OpenID Connect en core.dicsys.ai (F21): proxys al backend, login con retoma,
Cancelar y canje del código."""

import base64
import pathlib
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import create_app

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]

PEDIDO = {
    "response_type": "code",
    "client_id": "razorback",
    "redirect_uri": "http://localhost:5174/auth/core",
    "scope": "openid email profile",
    "state": "s1",
    "nonce": "n1",
    "code_challenge": "c" * 43,
    "code_challenge_method": "S256",
}
VUELTA = "http://localhost:5174/auth/core?code=codigo&state=s1"
LOGIN_OK = {
    "access_token": "test-token",
    "user": {"id": "u1", "email": "ana@dicsys.ai", "nombre": "Ana"},
    "empresas": [{"id": "e1", "razon_social": "Dicsys SA", "nombre_fantasia": "Dicsys", "logo": None}],
    "requiere_seleccion_empresa": False,
}


def _con_sesion(cliente):
    with cliente.session_transaction() as sesion:
        sesion["token"] = "test-token"


def _pendiente(frontend_client, fake_api, **pedido):
    """Un ingreso que quedó esperando el login (cookie oidc_pendiente)."""
    fake_api.respond("POST", "/oidc/validar", {"cliente": "razorback · Innovación Dicsys"})
    return frontend_client.get("/oidc/authorize", query_string={**PEDIDO, **pedido})


def test_discovery_y_jwks_son_los_del_backend_con_cache(frontend_client, fake_api):
    fake_api.respond("GET", "/oidc/configuracion", {"issuer": "https://core.dicsys.ai"})
    fake_api.respond("GET", "/oidc/jwks", {"keys": [{"kid": "k1"}]})

    discovery = frontend_client.get("/.well-known/openid-configuration")
    claves = frontend_client.get("/oidc/jwks")

    assert discovery.status_code == 200 and discovery.json == {"issuer": "https://core.dicsys.ai"}
    assert "max-age" in discovery.headers["Cache-Control"]
    assert claves.status_code == 200 and claves.json["keys"][0]["kid"] == "k1"


def test_proveedor_apagado_da_404(frontend_client, fake_api):
    fake_api.respond("GET", "/oidc/configuracion", {"detail": "no configurado"}, status=404)
    fake_api.respond("POST", "/oidc/validar", {"detail": "no configurado"}, status=404)
    assert frontend_client.get("/.well-known/openid-configuration").status_code == 404
    assert frontend_client.get("/oidc/authorize", query_string=PEDIDO).status_code == 404


def test_sin_sesion_guarda_el_pedido_y_manda_al_login_que_dice_a_que_app_se_entra(frontend_client, fake_api):
    respuesta = _pendiente(frontend_client, fake_api)

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
    assert "oidc_pendiente=" in respuesta.headers["Set-Cookie"]
    assert fake_api.calls[-1]["data"] == PEDIDO
    login = frontend_client.get("/login").get_data(as_text=True)
    assert "Estás entrando a <strong" in login and ">Razorback · Innovación</strong>" in login
    assert "/oidc/cancelar" in login


def test_el_login_del_ingreso_muestra_los_logos_de_la_app_y_lo_que_recibe(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api)

    login = frontend_client.get("/login").get_data(as_text=True)

    assert "<title>Entrar a Razorback - " in login and "Entrar a Razorback</h2>" in login
    assert "Innovación Dicsys" not in login  # el nombre de la app es el del login, no el registrado en el cliente
    assert login.count("/static/apps/razorback/razorback-marca-o.svg") == 2  # el panel y la tarjeta
    assert '<svg class="h-7 w-auto" xmlns="http://www.w3.org/2000/svg" viewBox="80 80 1040 92.7"' in login
    assert "<animate" in login  # la horizontal animada va en línea
    for recibe in ("Tu email", "Tu nombre y tu foto de perfil", "Un identificador de tu cuenta que no cambia"):
        assert recibe in login
    assert "Cancelar y volver a Razorback</a>" in login and "¡Bienvenido de nuevo!" not in login


def test_una_app_sin_logos_muestra_su_inicial_y_solo_lo_que_pide_el_scope(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api, client_id="otra-app", scope="openid email")

    login = frontend_client.get("/login").get_data(as_text=True)

    assert "/static/apps/" not in login and ">R</span>" in login
    assert (
        "Entrá a razorback con tu cuenta de Dicsys Core" in login
        and "Ingreso con Dicsys Core · Innovación Dicsys" in login
    )
    assert "Tu email" in login and "Tu nombre y tu foto de perfil" not in login


def test_sin_ingreso_pendiente_el_login_es_el_de_core(frontend_client, fake_api):
    login = frontend_client.get("/login").get_data(as_text=True)

    assert "¡Bienvenido de nuevo!" in login and "Estás entrando a" not in login and "/static/apps/" not in login


def test_los_logos_de_las_apps_existen_en_static():
    from modulos.oidc.app_module import APPS

    estaticos = pathlib.Path(__file__).resolve().parents[2] / "static"
    for app in APPS.values():
        for archivo in (app["marca"], app["horizontal"]):
            assert (estaticos / archivo).is_file(), archivo


def test_con_sesion_emite_el_codigo_y_vuelve_al_cliente(frontend_client, fake_api):
    _con_sesion(frontend_client)
    fake_api.respond("POST", "/oidc/autorizar", {"redirect": VUELTA})

    respuesta = frontend_client.get("/oidc/authorize", query_string=PEDIDO)

    assert respuesta.status_code == 302 and respuesta.headers["Location"] == VUELTA
    assert fake_api.calls[-1]["token"] == "test-token"


def test_con_la_sesion_vencida_vuelve_a_pedir_el_login(frontend_client, fake_api):
    _con_sesion(frontend_client)
    fake_api.respond("POST", "/oidc/autorizar", {"detail": "vencida"}, status=401)
    fake_api.respond("POST", "/oidc/validar", {"cliente": "razorback"})

    respuesta = frontend_client.get("/oidc/authorize", query_string=PEDIDO)

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")


def test_un_pedido_con_cliente_o_redirect_uri_no_registrado_se_muestra_y_no_redirige(frontend_client, fake_api):
    fake_api.respond(
        "POST",
        "/oidc/validar",
        {"error": "invalid_request", "error_description": "La dirección de retorno no está registrada."},
        status=400,
    )

    respuesta = frontend_client.get("/oidc/authorize", query_string=PEDIDO)

    assert respuesta.status_code == 400 and "Location" not in respuesta.headers
    assert "La dirección de retorno no está registrada." in respuesta.get_data(as_text=True)


def test_un_pedido_mal_formado_vuelve_al_cliente_con_el_error(frontend_client, fake_api):
    error = "http://localhost:5174/auth/core?error=invalid_request&state=s1"
    fake_api.respond("POST", "/oidc/validar", {"error": "invalid_request", "redirect": error}, status=400)

    respuesta = frontend_client.get("/oidc/authorize", query_string=PEDIDO)

    assert respuesta.status_code == 302 and respuesta.headers["Location"] == error


def test_el_login_termina_retomando_el_ingreso_pendiente(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api)
    fake_api.respond("POST", "/auth/login", LOGIN_OK)

    respuesta = frontend_client.post("/login", data={"email": "ana@dicsys.ai", "password": "x"})

    destino = urlsplit(respuesta.headers["Location"])
    assert respuesta.status_code == 302 and destino.path == "/oidc/authorize"
    assert {k: v[0] for k, v in parse_qs(destino.query).items()} == PEDIDO


def test_sin_ingreso_pendiente_el_login_va_al_inicio(frontend_client, fake_api):
    fake_api.respond("POST", "/auth/login", LOGIN_OK)

    respuesta = frontend_client.post("/login", data={"email": "ana@dicsys.ai", "password": "x"})

    assert "/oidc/" not in respuesta.headers["Location"]


def test_cancelar_vuelve_al_cliente_con_access_denied(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api)
    negado = "http://localhost:5174/auth/core?error=access_denied&state=s1"
    fake_api.respond("POST", "/oidc/denegar", {"redirect": negado})

    respuesta = frontend_client.get("/oidc/cancelar")

    assert respuesta.status_code == 302 and respuesta.headers["Location"] == negado
    assert fake_api.calls[-1]["data"] == PEDIDO


def test_una_cuenta_desactivada_en_el_login_vuelve_al_cliente_con_access_denied(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api)
    fake_api.respond("POST", "/auth/login", {"detail": "Usuario desactivado"}, status=401)

    respuesta = frontend_client.post("/login", data={"email": "baja@dicsys.ai", "password": "x"})

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/oidc/cancelar")


def test_canje_con_client_secret_basic_pasa_las_credenciales_al_backend(frontend_client, fake_api):
    fake_api.respond("POST", "/oidc/token", {"id_token": "jwt", "token_type": "Bearer"})
    basic = base64.b64encode(b"razorback:s%3Acreto").decode()

    respuesta = frontend_client.post(
        "/oidc/token",
        headers={"Authorization": f"Basic {basic}"},
        data={
            "grant_type": "authorization_code",
            "code": "c",
            "code_verifier": "v",
            "redirect_uri": PEDIDO["redirect_uri"],
        },
    )

    assert respuesta.status_code == 200 and respuesta.json["id_token"] == "jwt"
    assert respuesta.headers["Cache-Control"] == "no-store"
    enviado = fake_api.calls[-1]["data"]
    assert (enviado["client_id"], enviado["client_secret"], enviado["code"]) == ("razorback", "s:creto", "c")


def test_canje_con_cliente_invalido_da_401_con_www_authenticate(frontend_client, fake_api):
    fake_api.respond("POST", "/oidc/token", {"error": "invalid_client"}, status=401)

    respuesta = frontend_client.post("/oidc/token", data={"client_id": "razorback", "client_secret": "mal"})

    assert respuesta.status_code == 401 and respuesta.json["error"] == "invalid_client"
    assert "WWW-Authenticate" in respuesta.headers


SIN_EMAIL = (
    "Tu usuario no tiene un email corporativo y no puede acceder a Dicsys Core. Comunicate con el administrador."
)


def test_una_cuenta_sin_email_corporativo_vuelve_al_cliente_con_access_denied(frontend_client, fake_api):
    _pendiente(frontend_client, fake_api)
    fake_api.respond("POST", "/auth/login", {"detail": SIN_EMAIL}, status=403)

    respuesta = frontend_client.post("/login", data={"email": "juan@gmail.com", "password": "x"})

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/oidc/cancelar")


def test_sin_ingreso_pendiente_el_login_muestra_que_no_tiene_email_corporativo(frontend_client, fake_api):
    fake_api.respond("POST", "/auth/login", {"detail": SIN_EMAIL}, status=403)

    respuesta = frontend_client.post(
        "/login", data={"email": "juan@gmail.com", "password": "x"}, headers={"HX-Request": "true"}
    )

    assert respuesta.status_code == 200 and SIN_EMAIL in respuesta.get_data(as_text=True)


# Con el api_request real: ante un 401 del backend vacía la sesión y marca el pedido, y el middleware de la app
# cambiaba la respuesta por un redirect al login (PG-26). Los endpoints de OIDC manejan ese 401 por su cuenta.
@pytest.fixture
def con_api_real(monkeypatch):
    respuestas = {}

    def backend(peticion):
        payload, status = respuestas[(peticion.method, peticion.url.path.removeprefix("/api/v1"))]
        return httpx.Response(status, json=payload)

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    return app.test_client(), respuestas


def test_canje_con_cliente_invalido_da_401_y_no_redirige_al_login(con_api_real):
    cliente, respuestas = con_api_real
    respuestas[("POST", "/oidc/token")] = ({"error": "invalid_client"}, 401)

    respuesta = cliente.post("/oidc/token", data={"client_id": "razorback", "client_secret": "mal"})

    assert respuesta.status_code == 401 and respuesta.json == {"error": "invalid_client"}
    assert "WWW-Authenticate" in respuesta.headers and "Location" not in respuesta.headers


def test_con_la_sesion_vencida_el_login_conserva_el_ingreso_pendiente(con_api_real):
    cliente, respuestas = con_api_real
    respuestas[("POST", "/oidc/autorizar")] = ({"detail": "Sesión de Dicsys Core inválida o vencida"}, 401)
    respuestas[("POST", "/oidc/validar")] = ({"cliente": "razorback · Innovación Dicsys"}, 200)
    respuestas[("GET", "/auth/google/disponible")] = ({"disponible": False}, 200)
    _con_sesion(cliente)

    respuesta = cliente.get("/oidc/authorize", query_string=PEDIDO)

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
    assert "oidc_pendiente=" in " ".join(respuesta.headers.getlist("Set-Cookie"))
    login = cliente.get("/login").get_data(as_text=True)
    assert "Estás entrando a <strong" in login and "Cancelar y volver a Razorback</a>" in login
