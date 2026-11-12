"""Proveedor OpenID Connect (F21): la API interna que usa el frontend, con el checklist del pedido de razorback."""

import base64
import hashlib
import secrets
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from jwt.algorithms import RSAAlgorithm

from backend.core.config import settings
from backend.core.utils import utc_now
from backend.modules.auth.routers import create_access_token
from backend.modules.oidc import claves
from backend.modules.oidc.models import ClienteOIDC, CodigoOIDC
from backend.modules.oidc.services import hash_secreto
from backend.modules.parametros.models import Parametro
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

API = "/api/v1/oidc"
ISSUER = "https://core.test"
REDIRECT = "http://localhost:5174/auth/core"
SECRETO = "secreto-de-prueba"


@pytest.fixture
def proveedor(tmp_path, monkeypatch):
    (tmp_path / "k1.pem").write_text(claves.generar_pem())
    monkeypatch.setattr(settings, "oidc_claves_dir", str(tmp_path))
    monkeypatch.setattr(settings, "oidc_kid_activa", "k1")
    monkeypatch.setattr(settings, "oidc_issuer", ISSUER)
    return tmp_path


@pytest.fixture
def cliente(db_session, proveedor):
    cliente = ClienteOIDC(
        client_id=f"razorback-{uuid.uuid4().hex[:6]}",
        nombre="razorback · Innovación Dicsys",
        redirect_uris=[REDIRECT, "https://innovacion.test/auth/core"],
        scopes="openid email profile",
        secreto_hash=hash_secreto(SECRETO),
    )
    db_session.add(cliente)
    db_session.flush()
    return cliente


@pytest.fixture
def persona(data_factory):
    usuario = data_factory.usuario(email=f"ana.{uuid.uuid4().hex[:6]}@dicsys.ai", nombre="Ana", apellido="Pérez")
    return usuario, auth_headers(usuario)


def _pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _pedido(cliente, challenge, **cambios):
    pedido = {
        "response_type": "code",
        "client_id": cliente.client_id,
        "redirect_uri": REDIRECT,
        "scope": "openid email profile",
        "state": "estado-123",
        "nonce": "nonce-456",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return {**pedido, **cambios}


def _query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _autorizar(client, cliente, headers, **cambios):
    verifier, challenge = _pkce()
    r = client.post(f"{API}/autorizar", json=_pedido(cliente, challenge, **cambios), headers=headers)
    assert r.status_code == 200, r.text
    return _query(r.json()["redirect"]), verifier


def _canjear(client, cliente, code, verifier, **cambios):
    datos = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "code_verifier": verifier,
        "client_id": cliente.client_id,
        "client_secret": SECRETO,
    }
    return client.post(f"{API}/token", json={**datos, **cambios})


def _verificar(client, id_token, cliente):
    jwks = client.get(f"{API}/jwks").json()["keys"]
    kid = jwt.get_unverified_header(id_token)["kid"]
    clave = RSAAlgorithm.from_jwk(next(k for k in jwks if k["kid"] == kid))
    return jwt.decode(id_token, clave, algorithms=["RS256"], audience=cliente.client_id, issuer=ISSUER)


def test_discovery_anuncia_issuer_endpoints_pkce_y_metodos_del_cliente(client, proveedor):
    r = client.get(f"{API}/configuracion")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["issuer"] == ISSUER
    assert (d["authorization_endpoint"], d["token_endpoint"], d["jwks_uri"]) == (
        f"{ISSUER}/oidc/authorize",
        f"{ISSUER}/oidc/token",
        f"{ISSUER}/oidc/jwks",
    )
    assert d["code_challenge_methods_supported"] == ["S256"]
    assert set(d["token_endpoint_auth_methods_supported"]) == {"client_secret_post", "client_secret_basic"}
    assert d["id_token_signing_alg_values_supported"] == ["RS256"]


def test_sin_clave_activa_el_proveedor_esta_apagado(client, monkeypatch):
    monkeypatch.setattr(settings, "oidc_kid_activa", "")
    assert client.get(f"{API}/configuracion").status_code == 404
    assert client.post(f"{API}/token", json={}).status_code == 404


def test_flujo_completo_con_id_token_verificable_y_todos_los_claims(client, cliente, persona):
    usuario, headers = persona
    respuesta, verifier = _autorizar(client, cliente, headers)
    assert respuesta["state"] == "estado-123" and respuesta["code"]

    r = _canjear(client, cliente, respuesta["code"], verifier)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    cuerpo = r.json()
    assert cuerpo["token_type"] == "Bearer" and cuerpo["access_token"]
    claims = _verificar(client, cuerpo["id_token"], cliente)
    assert claims["sub"] == str(usuario.id) and claims["nonce"] == "nonce-456"
    assert (claims["email"], claims["email_verified"], claims["name"]) == (usuario.email, True, "Ana Pérez")
    assert claims["exp"] - claims["iat"] == 3600


def test_la_misma_persona_trae_el_mismo_sub(client, cliente, persona):
    _, headers = persona
    subs = set()
    for _ in range(2):
        respuesta, verifier = _autorizar(client, cliente, headers)
        subs.add(
            _verificar(client, _canjear(client, cliente, respuesta["code"], verifier).json()["id_token"], cliente)[
                "sub"
            ]
        )
    assert len(subs) == 1


def test_el_codigo_es_de_un_solo_uso(client, cliente, persona):
    respuesta, verifier = _autorizar(client, cliente, persona[1])
    assert _canjear(client, cliente, respuesta["code"], verifier).status_code == 200
    segundo = _canjear(client, cliente, respuesta["code"], verifier)
    assert (segundo.status_code, segundo.json()["error"]) == (400, "invalid_grant")


@pytest.mark.parametrize(
    "cambio",
    [
        {"code_verifier": None},
        {"code_verifier": "otro-" + "x" * 50},
        {"redirect_uri": "https://innovacion.test/auth/core"},
    ],
)
def test_sin_el_verifier_correcto_o_con_otro_redirect_uri_da_invalid_grant(client, cliente, persona, cambio):
    respuesta, verifier = _autorizar(client, cliente, persona[1])
    r = _canjear(client, cliente, respuesta["code"], verifier, **cambio)
    assert (r.status_code, r.json()["error"]) == (400, "invalid_grant")


def test_un_codigo_vencido_da_invalid_grant(client, db_session, cliente, persona):
    respuesta, verifier = _autorizar(client, cliente, persona[1])
    db_session.query(CodigoOIDC).update({CodigoOIDC.expira_at: utc_now() - timedelta(seconds=1)})
    db_session.flush()
    assert _canjear(client, cliente, respuesta["code"], verifier).json()["error"] == "invalid_grant"


@pytest.mark.parametrize(
    "cambio",
    [
        {"redirect_uri": "http://localhost:5174/auth/core/otra"},
        {"redirect_uri": "http://localhost:5174/"},
        {"client_id": "desconocido"},
    ],
)
def test_un_redirect_uri_no_registrado_o_un_cliente_desconocido_no_se_redirige(client, cliente, persona, cambio):
    _, challenge = _pkce()
    for ruta, headers in (("validar", {}), ("autorizar", persona[1])):
        r = client.post(f"{API}/{ruta}", json=_pedido(cliente, challenge, **cambio), headers=headers)
        assert r.status_code == 400, r.text
        assert "redirect" not in r.json() and r.json()["error"] in ("invalid_request", "invalid_client")


@pytest.mark.parametrize(
    "cambio, error",
    [
        ({"code_challenge_method": "plain"}, "invalid_request"),
        ({"code_challenge": None}, "invalid_request"),
        ({"nonce": None}, "invalid_request"),
        ({"scope": "email profile"}, "invalid_scope"),
        ({"response_type": "token"}, "unsupported_response_type"),
    ],
)
def test_un_pedido_mal_formado_vuelve_al_cliente_con_el_error_y_el_state(client, cliente, cambio, error):
    _, challenge = _pkce()
    r = client.post(f"{API}/validar", json=_pedido(cliente, challenge, **cambio))
    assert r.status_code == 400, r.text
    vuelta = _query(r.json()["redirect"])
    assert (vuelta["error"], vuelta["state"]) == (error, "estado-123")
    assert r.json()["redirect"].startswith(REDIRECT + "?")


def test_una_cuenta_desactivada_vuelve_con_access_denied(client, db_session, cliente, persona):
    usuario, headers = persona
    usuario.activo = False
    db_session.flush()
    _, challenge = _pkce()
    r = client.post(f"{API}/autorizar", json=_pedido(cliente, challenge), headers=headers)
    assert r.status_code == 400, r.text
    vuelta = _query(r.json()["redirect"])
    assert (vuelta["error"], vuelta["state"]) == ("access_denied", "estado-123") and "code" not in vuelta


def test_cancelar_vuelve_con_access_denied(client, cliente):
    _, challenge = _pkce()
    r = client.post(f"{API}/denegar", json=_pedido(cliente, challenge))
    assert r.status_code == 200, r.text
    assert _query(r.json()["redirect"])["error"] == "access_denied"


def test_autorizar_pide_una_sesion_completa_de_core(client, cliente, persona):
    usuario, _ = persona
    _, challenge = _pkce()
    intermedio = create_access_token(
        {"sub": usuario.email, "user_id": str(usuario.id), "purpose": "2fa"}, timedelta(minutes=5)
    )
    for headers in ({}, {"Authorization": f"Bearer {intermedio}"}, {"Authorization": "Bearer basura"}):
        assert client.post(f"{API}/autorizar", json=_pedido(cliente, challenge), headers=headers).status_code == 401


def test_cliente_con_secreto_incorrecto_da_invalid_client(client, cliente, persona):
    respuesta, verifier = _autorizar(client, cliente, persona[1])
    r = _canjear(client, cliente, respuesta["code"], verifier, client_secret="otro")
    assert (r.status_code, r.json()["error"]) == (401, "invalid_client")
    assert "WWW-Authenticate" in r.headers


def test_durante_una_rotacion_valen_los_dos_secretos(client, db_session, cliente, persona):
    cliente.secreto_nuevo_hash = hash_secreto("secreto-nuevo")
    db_session.flush()
    for secreto in (SECRETO, "secreto-nuevo"):
        respuesta, verifier = _autorizar(client, cliente, persona[1])
        assert _canjear(client, cliente, respuesta["code"], verifier, client_secret=secreto).status_code == 200


def test_email_verified_depende_del_dominio(client, db_session, data_factory, cliente):
    otro = data_factory.usuario(email=f"ext.{uuid.uuid4().hex[:6]}@gmail.com")
    respuesta, verifier = _autorizar(client, cliente, auth_headers(otro))
    claims = _verificar(client, _canjear(client, cliente, respuesta["code"], verifier).json()["id_token"], cliente)
    assert claims["email_verified"] is False

    db_session.add(
        Parametro(
            categoria="Seguridad",
            subcategoria="OpenID Connect",
            nombre="Dominios",
            key="oidc_dominios_verificados",
            valor="gmail.com, dicsys.ai",
        )
    )
    db_session.flush()
    respuesta, verifier = _autorizar(client, cliente, auth_headers(otro))
    claims = _verificar(client, _canjear(client, cliente, respuesta["code"], verifier).json()["id_token"], cliente)
    assert claims["email_verified"] is True


def test_la_foto_sale_como_url_https_del_issuer(client, db_session, cliente, persona):
    usuario, headers = persona
    usuario.avatar_url = "/files/profile/ana.png"
    db_session.flush()
    respuesta, verifier = _autorizar(client, cliente, headers)
    claims = _verificar(client, _canjear(client, cliente, respuesta["code"], verifier).json()["id_token"], cliente)
    assert claims["picture"] == f"{ISSUER}/files/profile/ana.png"


def test_una_clave_nueva_se_publica_y_firma_cuando_pasa_a_ser_la_activa(
    client, monkeypatch, proveedor, cliente, persona
):
    (proveedor / "k2.pem").write_text(claves.generar_pem())
    assert {k["kid"] for k in client.get(f"{API}/jwks").json()["keys"]} == {"k1", "k2"}
    monkeypatch.setattr(settings, "oidc_kid_activa", "k2")
    respuesta, verifier = _autorizar(client, cliente, persona[1])
    id_token = _canjear(client, cliente, respuesta["code"], verifier).json()["id_token"]
    assert jwt.get_unverified_header(id_token)["kid"] == "k2"
    assert _verificar(client, id_token, cliente)["aud"] == cliente.client_id


def test_un_parametro_con_el_caracter_nul_da_422_y_no_500(client, proveedor):
    for ruta, cuerpo in (
        ("validar", {"client_id": "raz\x00orback"}),
        ("token", {"client_id": "a\x00b", "client_secret": "x"}),
    ):
        assert client.post(f"{API}/{ruta}", json=cuerpo).status_code == 422
