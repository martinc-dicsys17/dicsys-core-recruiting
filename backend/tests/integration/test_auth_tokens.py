"""Tokens JWT con PyJWT: mal formados, vencidos, con otra firma y tokens intermedios del 2FA (F02-P01, F16-P04)."""

import base64
import importlib.util
import json
from datetime import timedelta

import jwt
import pytest

from backend.core.config import settings
from backend.core.utils import utc_now
from backend.modules.auth.routers import create_access_token, create_reset_token

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _datos(usuario, **extra) -> dict:
    return {"sub": usuario.email, "user_id": str(usuario.id), **extra}


def _b64(datos: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(datos).encode()).rstrip(b"=").decode()


def test_python_jose_ya_no_esta_instalado():
    assert importlib.util.find_spec("jose") is None


def test_token_mal_formado_vencido_sin_firma_o_con_otra_clave_da_401(client, data_factory):
    usuario = data_factory.usuario(rol="admin")
    vigente = utc_now() + timedelta(minutes=5)
    vencido = jwt.encode(
        {**_datos(usuario), "exp": utc_now() - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    otra_clave = jwt.encode(
        {**_datos(usuario), "exp": vigente}, "otra-clave-de-firma-" + "x" * 32, algorithm=settings.jwt_algorithm
    )
    sin_firma = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({**_datos(usuario), 'exp': 9999999999})}."

    for token in ("no-es-un-jwt", "a.b.c", vencido, otra_clave, sin_firma):
        # get_user_id_from_token (auth) y get_current_user (resto de la API): 401, nunca 500
        assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401, token
        assert client.get("/api/v1/usuarios", headers=_bearer(token)).status_code == 401, token


def test_el_token_intermedio_del_2fa_no_vale_como_sesion(client, data_factory):
    usuario = data_factory.usuario(rol="admin")
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)

    for proposito in ("2fa", "2fa_setup"):
        token = create_access_token(
            _datos(usuario, purpose=proposito, empresa_id=str(empresa.id)), timedelta(minutes=5)
        )
        assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401
        assert client.get("/api/v1/usuarios", headers=_bearer(token)).status_code == 401
        r = client.post(
            "/api/v1/auth/seleccionar-empresa", headers=_bearer(token), json={"empresa_id": str(empresa.id)}
        )
        assert r.status_code == 401, "con solo la contraseña no se obtiene una sesión completa"

    # el intermedio del login de un usuario con 2FA activo tampoco sirve para el alta: no puede pisar el secreto
    token = create_access_token(_datos(usuario, purpose="2fa"), timedelta(minutes=5))
    assert client.post("/api/v1/auth/me/2fa/setup", headers=_bearer(token)).status_code == 401


def test_el_token_del_alta_obligatoria_del_2fa_sirve_solo_para_el_alta(client, data_factory):
    usuario = data_factory.usuario()
    token = create_access_token(_datos(usuario, purpose="2fa_setup"), timedelta(minutes=15))

    r = client.post("/api/v1/auth/me/2fa/setup", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["secret_manual"]
    assert client.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401


def test_verify_2fa_solo_acepta_tokens_intermedios(client, data_factory):
    usuario = data_factory.usuario()
    for token in (create_access_token(_datos(usuario)), "no-es-un-jwt"):
        r = client.post("/api/v1/auth/verify-2fa", json={"temp_token": token, "code": "123456"})
        assert r.status_code == 401, r.text


def test_los_tokens_de_reset_y_de_sesion_no_se_cruzan(client, data_factory):
    usuario = data_factory.usuario()
    assert client.get("/api/v1/auth/me", headers=_bearer(create_reset_token(usuario.email))).status_code == 401

    r = client.post(
        "/api/v1/auth/reset-password",
        json={"token": create_access_token(_datos(usuario)), "password": "una-clave-nueva-larga"},
    )
    assert r.status_code == 400
    r = client.post("/api/v1/auth/reset-password", json={"token": "no-es-un-jwt", "password": "una-clave-nueva-larga"})
    assert r.status_code == 400
