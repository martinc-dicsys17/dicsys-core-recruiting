"""Ingreso con Google en el login (F22): el botón, la ida a Google con state/nonce/PKCE en cookie firmada y la vuelta,
que sigue como el login con contraseña."""

import base64
import hashlib
from urllib.parse import parse_qs, urlsplit

import pytest
from itsdangerous import URLSafeTimedSerializer

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]

GOOGLE = "https://accounts.google.com/o/oauth2/v2/auth"
LOGIN_OK = {
    "access_token": "test-token",
    "user": {"id": "u1", "email": "ana@dicsys.ai", "nombre": "Ana"},
    "empresas": [{"id": "e1", "razon_social": "Dicsys SA", "nombre_fantasia": "Dicsys", "logo": None}],
    "requiere_seleccion_empresa": False,
}
OIDC = {
    "response_type": "code",
    "client_id": "razorback",
    "redirect_uri": "http://localhost:5174/auth/core",
    "scope": "openid email profile",
    "state": "s1",
    "nonce": "n1",
    "code_challenge": "c" * 43,
    "code_challenge_method": "S256",
}


def _ida(frontend_client, fake_api):
    """GET /login/google: devuelve la respuesta y el pedido que quedó en la cookie."""
    fake_api.respond("POST", "/auth/google/autorizacion", {"url": f"{GOOGLE}?client_id=core"})
    respuesta = frontend_client.get("/login/google")
    cookie = frontend_client.get_cookie("google_ingreso")
    pendiente = URLSafeTimedSerializer("frontend-test-secret", salt="google-ingreso").loads(cookie.value)
    return respuesta, pendiente


def _vuelta(frontend_client, fake_api, respuesta_backend, status=200, **args):
    _, pendiente = _ida(frontend_client, fake_api)
    fake_api.respond("POST", "/auth/google/ingreso", respuesta_backend, status=status)
    query = {"code": "4/codigo", "state": pendiente["state"], **args}
    return frontend_client.get("/login/google/callback", query_string=query), pendiente


def test_el_login_muestra_el_boton_solo_con_google_configurado(frontend_client, fake_api):
    assert "Entrar con Google" not in frontend_client.get("/login").get_data(as_text=True)  # sin respuesta del backend

    fake_api.respond("GET", "/auth/google/disponible", {"disponible": False})
    assert "Entrar con Google" not in frontend_client.get("/login").get_data(as_text=True)

    fake_api.respond("GET", "/auth/google/disponible", {"disponible": True, "dominio": "dicsys.ai"})
    pagina = frontend_client.get("/login").get_data(as_text=True)
    assert "Entrar con Google" in pagina and "/login/google" in pagina and "Con tu cuenta @dicsys.ai" in pagina


def test_ida_a_google_con_pkce_y_cookie_firmada(frontend_client, fake_api):
    respuesta, pendiente = _ida(frontend_client, fake_api)

    assert respuesta.status_code == 302 and respuesta.headers["Location"] == f"{GOOGLE}?client_id=core"
    assert "HttpOnly" in respuesta.headers["Set-Cookie"] and "SameSite=Lax" in respuesta.headers["Set-Cookie"]
    enviado = fake_api.calls[-1]["data"]
    desafio = base64.urlsafe_b64encode(hashlib.sha256(pendiente["verificador"].encode()).digest()).rstrip(b"=").decode()
    assert enviado == {"state": pendiente["state"], "nonce": pendiente["nonce"], "code_challenge": desafio}
    assert len(pendiente["verificador"]) >= 43


def test_ida_con_google_apagado_da_404(frontend_client, fake_api):
    fake_api.respond("POST", "/auth/google/autorizacion", {"detail": "no configurado"}, status=404)
    assert frontend_client.get("/login/google").status_code == 404


def test_vuelta_aceptada_inicia_sesion_y_borra_la_cookie(frontend_client, fake_api):
    respuesta, pendiente = _vuelta(frontend_client, fake_api, LOGIN_OK)

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/")
    assert fake_api.calls[-1]["data"] == {
        "code": "4/codigo",
        "code_verifier": pendiente["verificador"],
        "nonce": pendiente["nonce"],
    }
    assert frontend_client.get_cookie("google_ingreso") is None
    with frontend_client.session_transaction() as sesion:
        assert sesion["token"] == "test-token" and sesion["empresa_id"] == "e1"


def test_vuelta_con_2fa_va_al_codigo(frontend_client, fake_api):
    respuesta, _ = _vuelta(frontend_client, fake_api, {"requires_2fa": True, "temp_token": "t", "user": {}})
    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login/2fa")


def _error_en_el_login(frontend_client, respuesta, mensaje):
    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
    fake_disponible = frontend_client.application.config["api_request"]
    fake_disponible.respond("GET", "/auth/google/disponible", {"disponible": True, "dominio": "dicsys.ai"})
    assert mensaje in frontend_client.get("/login").get_data(as_text=True)


@pytest.mark.parametrize(
    "args, mensaje",
    [
        ({"error": "access_denied"}, "Cancelaste el ingreso con Google"),
        ({"state": "otro-state"}, "venció o no empezó en este navegador"),
        ({"code": ""}, "venció o no empezó en este navegador"),
    ],
)
def test_vuelta_que_no_sigue(frontend_client, fake_api, args, mensaje):
    respuesta, _ = _vuelta(frontend_client, fake_api, LOGIN_OK, **args)
    _error_en_el_login(frontend_client, respuesta, mensaje)
    assert all(c["endpoint"] != "/auth/google/ingreso" for c in fake_api.calls)


def test_vuelta_sin_cookie(frontend_client, fake_api):
    respuesta = frontend_client.get("/login/google/callback", query_string={"code": "x", "state": "y"})
    _error_en_el_login(frontend_client, respuesta, "venció o no empezó en este navegador")


def test_vuelta_sin_cuenta_en_core(frontend_client, fake_api):
    respuesta, _ = _vuelta(frontend_client, fake_api, {"detail": "Tu cuenta de Google no está asociada"}, status=403)
    _error_en_el_login(frontend_client, respuesta, "Tu cuenta de Google no está asociada")


def test_vuelta_con_ingreso_oidc_pendiente(frontend_client, fake_api):
    fake_api.respond("POST", "/oidc/validar", {"cliente": "razorback"})
    frontend_client.get("/oidc/authorize", query_string=OIDC)

    respuesta, _ = _vuelta(frontend_client, fake_api, LOGIN_OK)
    destino = urlsplit(respuesta.headers["Location"])
    assert destino.path == "/oidc/authorize" and parse_qs(destino.query)["client_id"] == ["razorback"]

    respuesta, _ = _vuelta(frontend_client, fake_api, {"detail": "Usuario desactivado"}, status=401)
    assert respuesta.headers["Location"].endswith("/oidc/cancelar")
