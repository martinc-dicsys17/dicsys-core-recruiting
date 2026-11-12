"""URLs firmadas de corta duración para descargas (F07-P06): POST /auth/descargas y el middleware FirmaDeDescarga."""

from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.core import descargas
from backend.core.tokens import crear_token
from backend.tests.helpers.auth import auth_headers

FIRMAR = "/api/v1/auth/descargas"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def persona(data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    return usuario, empresa, auth_headers(usuario, empresa)


def _firmar(client, headers, ruta: str):
    return client.post(FIRMAR, json={"ruta": ruta}, headers=headers)


def test_la_url_firmada_sirve_sin_bearer_como_quien_la_pidio(client, persona):
    usuario, empresa, headers = persona

    r = _firmar(client, headers, "/api/v1/auth/me")

    assert r.status_code == 200, r.text
    assert r.json()["expira_en"] == 300
    url = r.json()["url"]
    assert url.startswith("/api/v1/auth/me?firma=")
    me = client.get(url)
    assert me.status_code == 200, me.text
    assert me.json()["email"] == usuario.email and me.json()["empresa"]["id"] == str(empresa.id)


def test_la_firma_sirve_solo_para_su_ruta_y_para_get(client, persona):
    _, _, headers = persona
    firma = parse_qs(urlsplit(_firmar(client, headers, "/api/v1/auth/me").json()["url"]).query)["firma"][0]

    otra = client.get(f"/api/v1/menus?firma={firma}")
    assert otra.status_code == 401 and otra.json()["detail"] == "URL firmada inválida o vencida"
    # en un POST la firma no cuenta: sin Bearer no hay sesión
    assert client.post(f"/api/v1/auth/descargas?firma={firma}", json={"ruta": "/api/v1/auth/me"}).status_code == 401


def test_firma_adulterada_vencida_o_de_otro_proposito_da_401(client, persona):
    usuario, empresa, headers = persona
    firma = parse_qs(urlsplit(_firmar(client, headers, "/api/v1/auth/me").json()["url"]).query)["firma"][0]
    sesion = {"sub": usuario.email, "user_id": str(usuario.id), "rol": usuario.rol, "empresa_id": str(empresa.id)}
    vencida = crear_token({**sesion, "purpose": descargas.PROPOSITO, "ruta": "/api/v1/auth/me"}, timedelta(seconds=-1))
    de_sesion = crear_token(sesion)  # un access token común no es una firma de descarga

    for token in (firma[:-2] + "xx", vencida, de_sesion):
        r = client.get(f"/api/v1/auth/me?firma={token}")
        assert r.status_code == 401, token


def test_firmar_pide_bearer_y_una_ruta_firmable(client, persona):
    _, _, headers = persona

    assert client.post(FIRMAR, json={"ruta": "/api/v1/auth/me"}).status_code == 401
    for ruta in (
        "/otra/cosa",
        "https://evil.example/api/v1/x",
        "/api/v1/auth/me?x=1",
        "/api/v1/../storage/x",
        "/api/v1/#a",
    ):
        r = _firmar(client, headers, ruta)
        assert r.status_code == 422, ruta
    assert _firmar(client, headers, "/storage/recibos-1/x.pdf").status_code == 200


def test_la_firma_de_una_cuenta_desactivada_no_sirve(client, db_session, persona):
    """El endpoint corre con sus chequeos de siempre: get_current_user rechaza la cuenta inactiva."""
    usuario, _, headers = persona
    url = _firmar(client, headers, "/api/v1/menus").json()["url"]
    assert client.get(url).status_code == 200
    usuario.activo = False
    db_session.commit()

    assert client.get(url).status_code == 401
