"""Ingreso con Google (F22): la API que usa el frontend, la verificación del id_token de Google, la cuenta de la
persona y la mudanza de nombre@dicsys.com a nombre@dicsys.ai en el primer ingreso. Google está simulado: el canje
real solo se puede probar con el cliente OAuth del Workspace (F22-P08)."""

import json
import time
import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.core.config import settings
from backend.modules.auth import google as ingreso_google
from backend.modules.parametros.models import Parametro
from backend.modules.parametros.services import ValorInvalido, validar_valor

pytestmark = [pytest.mark.integration]

API = "/api/v1/auth/google"
CLIENT_ID = "core-qa.apps.googleusercontent.com"
NONCE = "nonce-de-prueba-1234567890"
VERIFIER = "v" * 43


class GoogleFalso:
    """Lo que Google devolvería al canjear el código: los claims del id_token ya verificado."""

    def __init__(self):
        self.claims = None
        self.error = None
        self.canjes = []

    def canjear(self, code, code_verifier, redirect_uri):
        self.canjes.append({"code": code, "code_verifier": code_verifier, "redirect_uri": redirect_uri})
        if self.error:
            raise ingreso_google.ErrorGoogle(self.error)
        return self.claims


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", CLIENT_ID)
    monkeypatch.setattr(settings, "google_oauth_client_secret", "secreto-qa")
    monkeypatch.setattr(settings, "frontend_url", "https://core.test/")


@pytest.fixture
def google(configurado):
    anterior = ingreso_google.google.adapter
    falso = GoogleFalso()
    ingreso_google.google.set_adapter(falso)
    yield falso
    ingreso_google.google.set_adapter(anterior)


def _claims(email, **cambios):
    return {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "1234",
        "email": email,
        "email_verified": True,
        "hd": email.rsplit("@", 1)[-1],
        "nonce": NONCE,
        **cambios,
    }


def _ingresar(client, google, email=None, **cambios):
    if email is not None:
        google.claims = _claims(email, **cambios)
    return client.post(f"{API}/ingreso", json={"code": "4/codigo-de-google", "code_verifier": VERIFIER, "nonce": NONCE})


def _local():
    return f"qa{uuid.uuid4().hex[:8]}"


def _persona(data_factory, email, email_secundario=None, ficha=True, **datos_ficha):
    """Cuenta con empresa y, salvo ficha=False, su ficha de nómina (que copia el email de la cuenta)."""
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(
        email=email,
        email_secundario=email_secundario,
        password="clave-123",
        dni=uuid.uuid4().int % 89_999_999 + 10_000_000,
    )
    data_factory.asignar_empresa(usuario, empresa)
    datos_ficha.setdefault("email_corporativo", email)
    empleado = data_factory.empleado(empresa, dni=usuario.dni, **datos_ficha) if ficha else None
    return usuario, empresa, empleado


def _parametro(db_session, key, valor):
    db_session.add(
        Parametro(categoria="Seguridad", subcategoria="Ingreso con Google", nombre=key, key=key, valor=valor)
    )
    db_session.flush()


# ─── Encendido y URL de Google ─────────────────────────────────────────────


def test_sin_cliente_oauth_esta_apagado(client, monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "")
    assert client.get(f"{API}/disponible").json() == {"disponible": False}
    pedido = {"state": "s" * 20, "nonce": NONCE, "code_challenge": "c" * 43}
    assert client.post(f"{API}/autorizacion", json=pedido).status_code == 404
    assert (
        client.post(f"{API}/ingreso", json={"code": "x", "code_verifier": VERIFIER, "nonce": NONCE}).status_code == 404
    )


def test_url_de_google_con_pkce_nonce_y_dominio(client, configurado):
    assert client.get(f"{API}/disponible").json() == {"disponible": True, "dominio": "dicsys.ai"}
    r = client.post(
        f"{API}/autorizacion", json={"state": "estado-" + "s" * 20, "nonce": NONCE, "code_challenge": "c" * 43}
    )
    assert r.status_code == 200, r.text
    url = urlsplit(r.json()["url"])
    assert f"{url.scheme}://{url.netloc}{url.path}" == ingreso_google.AUTORIZACION_URL
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q == {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": "https://core.test/login/google/callback",
        "scope": "openid email profile",
        "state": "estado-" + "s" * 20,
        "nonce": NONCE,
        "code_challenge": "c" * 43,
        "code_challenge_method": "S256",
        "hd": "dicsys.ai",
        "prompt": "select_account",
    }


@pytest.mark.parametrize(
    "pedido",
    [
        {"state": "corto", "nonce": NONCE, "code_challenge": "c" * 43},
        {"state": "s" * 20, "nonce": NONCE, "code_challenge": "c" * 42},
        {"state": "s" * 20 + "\x00", "nonce": NONCE, "code_challenge": "c" * 43},
    ],
)
def test_autorizacion_valida_el_pedido(client, configurado, pedido):
    assert client.post(f"{API}/autorizacion", json=pedido).status_code == 422


# ─── Qué dice Google ──────────────────────────────────────────────────────


def test_cuenta_con_ese_email_entra(client, data_factory, google):
    local = _local()
    usuario, empresa, _ = _persona(data_factory, f"{local}@dicsys.ai")
    r = _ingresar(client, google, f"{local}@DICSYS.ai".lower())
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == str(usuario.id)
    assert r.json()["access_token"]
    assert google.canjes == [
        {
            "code": "4/codigo-de-google",
            "code_verifier": VERIFIER,
            "redirect_uri": "https://core.test/login/google/callback",
        }
    ]


@pytest.mark.parametrize(
    "cambios, status, mensaje",
    [
        ({"nonce": "otro-nonce-1234567890"}, 400, "no corresponde a este pedido"),
        ({"email_verified": False}, 403, "no confirmó el email"),
        ({"hd": None}, 403, "Solo se puede entrar con una cuenta de Google @dicsys.ai"),
    ],
)
def test_id_token_que_no_corresponde(client, data_factory, google, cambios, status, mensaje):
    local = _local()
    _persona(data_factory, f"{local}@dicsys.ai")
    r = _ingresar(client, google, f"{local}@dicsys.ai", **cambios)
    assert r.status_code == status
    assert mensaje in r.json()["detail"]


def test_cuenta_de_otro_dominio_no_entra(client, data_factory, google):
    _persona(data_factory, "alguien@gmail.com")
    r = _ingresar(client, google, "alguien@gmail.com")
    assert r.status_code == 403
    assert "@dicsys.ai" in r.json()["detail"]


def test_google_rechaza_el_codigo(client, google):
    google.error = "Google rechazó el código (invalid_grant)"
    r = _ingresar(client, google)
    assert r.status_code == 400
    assert r.json()["detail"] == "Google no confirmó el ingreso. Probá de nuevo."


def test_usuario_desactivado_y_sin_cuenta(client, data_factory, google, db_session):
    local = _local()
    usuario, _, _ = _persona(data_factory, f"{local}@dicsys.ai")
    usuario.activo = False
    db_session.flush()
    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert (r.status_code, r.json()["detail"]) == (401, "Usuario desactivado")

    r = _ingresar(client, google, f"{_local()}@dicsys.ai")
    assert r.status_code == 403
    assert r.json()["detail"] == ingreso_google.SIN_CUENTA


# ─── La cuenta de la persona y la mudanza ─────────────────────────────────


def test_entra_por_el_secundario_de_la_cuenta_sin_mudar_nada(client, data_factory, google, db_session):
    local = _local()
    usuario, _, ficha = _persona(data_factory, f"{local}@dicsys.com", email_secundario=f"{local}@dicsys.ai")
    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == str(usuario.id)
    db_session.refresh(usuario)
    db_session.refresh(ficha)
    assert (usuario.email, usuario.email_secundario) == (f"{local}@dicsys.com", f"{local}@dicsys.ai")
    assert ficha.email_corporativo == f"{local}@dicsys.com"


def test_primer_ingreso_muda_la_cuenta_y_las_fichas_copian(client, data_factory, google, db_session):
    local = _local()
    usuario, empresa, ficha = _persona(data_factory, f"{local}@dicsys.com")
    # La misma persona con ficha en otra empresa
    empresa2 = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa2)
    ficha2 = data_factory.empleado(empresa2, dni=usuario.dni, email_corporativo=f"{local}@dicsys.com")

    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == f"{local}@dicsys.ai"
    db_session.refresh(usuario)
    assert (usuario.email, usuario.email_secundario) == (f"{local}@dicsys.ai", f"{local}@dicsys.com")
    assert usuario.updated_by == "ingreso_google"
    for f in (ficha, ficha2):
        db_session.refresh(f)
        assert f.email_corporativo == f"{local}@dicsys.ai"

    # Después entra con la contraseña con cualquiera de los dos y con Google sin mudar de nuevo
    for email in (f"{local}@dicsys.ai", f"{local}@dicsys.com"):
        assert client.post("/api/v1/auth/login", json={"email": email, "password": "clave-123"}).status_code == 200
    assert _ingresar(client, google, f"{local}@dicsys.ai").status_code == 200


def test_cuenta_sin_ficha_tambien_se_muda(client, data_factory, google, db_session):
    local = _local()
    usuario, _, _ = _persona(data_factory, f"{local}@dicsys.com", ficha=False)
    assert _ingresar(client, google, f"{local}@dicsys.ai").status_code == 200
    db_session.refresh(usuario)
    assert (usuario.email, usuario.email_secundario) == (f"{local}@dicsys.ai", f"{local}@dicsys.com")


@pytest.mark.parametrize("caso", ["otro_nombre", "con_secundario", "dominio_ajeno_a_la_empresa"])
def test_sin_mudanza(client, data_factory, google, db_session, caso):
    local = _local()
    email = f"x{local}@dicsys.com" if caso == "otro_nombre" else f"{local}@dicsys.com"
    secundario = f"otro{local}@dicsys.com" if caso == "con_secundario" else None
    usuario, empresa, _ = _persona(data_factory, email, email_secundario=secundario)
    if caso == "dominio_ajeno_a_la_empresa":
        empresa.dominios_email = json.dumps(["dicsys.com"])
        db_session.flush()

    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert r.status_code == 403, r.text
    db_session.refresh(usuario)
    assert (usuario.email, usuario.email_secundario) == (email, secundario)


def test_cuenta_desactivada_no_se_muda(client, data_factory, google, db_session):
    local = _local()
    usuario, _, _ = _persona(data_factory, f"{local}@dicsys.com")
    usuario.activo = False
    db_session.flush()
    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert (r.status_code, r.json()["detail"]) == (401, "Usuario desactivado")
    db_session.refresh(usuario)
    assert (usuario.email, usuario.email_secundario) == (f"{local}@dicsys.com", None)


# ─── 2FA de Core según el parámetro ───────────────────────────────────────


def test_el_2fa_de_core_lo_decide_el_parametro(client, data_factory, google, db_session):
    local = _local()
    usuario, _, _ = _persona(data_factory, f"{local}@dicsys.ai")
    usuario.totp_secret, usuario.totp_enabled = pyotp.random_base32(), True
    db_session.flush()

    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert r.status_code == 200 and "access_token" in r.json()  # apagado por defecto: Google alcanza

    _parametro(db_session, "google_login_requiere_2fa", "true")
    r = _ingresar(client, google, f"{local}@dicsys.ai")
    assert r.json().get("requires_2fa") is True and r.json()["temp_token"]

    usuario.totp_enabled, usuario.totp_required = False, True
    db_session.flush()
    assert _ingresar(client, google, f"{local}@dicsys.ai").json().get("requires_2fa_setup") is True


def test_parametros_con_valores_que_no_se_entienden():
    with pytest.raises(ValorInvalido):
        validar_valor("google_login_requiere_2fa", "quizás")
    with pytest.raises(ValorInvalido):
        validar_valor("google_login_dominio", "no es un dominio")
    validar_valor("google_login_requiere_2fa", "true")
    validar_valor("google_login_dominio", "@dicsys.ai")


# ─── El cliente real de Google: verificación del id_token y errores del canje ─


@pytest.fixture
def claves_de_google(monkeypatch, configurado):
    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    clave = type("Clave", (), {"key": privada.public_key()})()
    cliente = ingreso_google.ClienteGoogle()
    monkeypatch.setattr(
        cliente, "_jwks", lambda: type("Jwks", (), {"get_signing_key_from_jwt": lambda self, t: clave})()
    )
    return cliente, privada


def _firmar(privada, **cambios):
    ahora = int(time.time())
    return jwt.encode(
        {**_claims("ana@dicsys.ai"), "iat": ahora, "exp": ahora + 3600, **cambios},
        privada,
        algorithm="RS256",
        headers={"kid": "g1"},
    )


def test_verificar_id_token_de_google(claves_de_google):
    cliente, privada = claves_de_google
    assert cliente.verificar(_firmar(privada))["email"] == "ana@dicsys.ai"
    assert cliente.verificar(_firmar(privada, iss="accounts.google.com"))["sub"] == "1234"
    for cambios in ({"aud": "otra-app"}, {"iss": "https://evil.test"}, {"exp": int(time.time()) - 3600}):
        with pytest.raises(ingreso_google.ErrorGoogle):
            cliente.verificar(_firmar(privada, **cambios))
    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ingreso_google.ErrorGoogle):
        cliente.verificar(_firmar(otra))


def test_canje_rechazado_por_google(claves_de_google, monkeypatch):
    cliente, privada = claves_de_google
    enviados = []

    def post(url, data, timeout):
        enviados.append((url, data))
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(ingreso_google.httpx, "post", post)
    with pytest.raises(ingreso_google.ErrorGoogle, match="invalid_grant"):
        cliente.canjear("codigo", VERIFIER, "https://core.test/login/google/callback")
    assert enviados[0][0] == ingreso_google.TOKEN_URL
    assert enviados[0][1]["client_secret"] == "secreto-qa" and enviados[0][1]["code_verifier"] == VERIFIER

    monkeypatch.setattr(
        ingreso_google.httpx,
        "post",
        lambda url, data, timeout: httpx.Response(200, json={"id_token": _firmar(privada)}),
    )
    assert cliente.canjear("codigo", VERIFIER, "https://core.test/login/google/callback")["email"] == "ana@dicsys.ai"
