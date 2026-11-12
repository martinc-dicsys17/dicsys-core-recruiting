"""Refresh token rotativo en cookie httpOnly (F07-P03, D-12): /auth/refresh rota y /auth/logout revoca."""

from datetime import timedelta
from http.cookies import SimpleCookie

import pytest
from sqlalchemy import delete

from backend.core.tokens import decodificar
from backend.core.utils import utc_now
from backend.modules.auth import refresco
from backend.modules.auth.models import TokenRefresco
from backend.modules.empresa.models import core_usuario_empresa

REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


XHR = {"X-Requested-With": "XMLHttpRequest"}


def _con_cookie(token: str) -> dict:
    return {"Cookie": f"{refresco.COOKIE}={token}", **XHR}


def _cookie(respuesta) -> SimpleCookie:
    galleta = SimpleCookie()
    for linea in respuesta.headers.get_list("set-cookie"):
        galleta.load(linea)
    return galleta


@pytest.fixture
def sesion(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    return usuario, empresa, refresco.emitir(db_session, usuario.id, empresa.id)


def test_sin_cookie_o_con_una_inventada_da_401_y_la_borra(client):
    for headers in (XHR, _con_cookie("inventada")):
        r = client.post(REFRESH, headers=headers)
        assert r.status_code == 401, r.text
        assert _cookie(r)[refresco.COOKIE]["max-age"] == "0"


def test_refresh_da_un_access_token_de_la_sesion_y_rota_la_cookie(client, sesion):
    usuario, empresa, token = sesion

    r = client.post(REFRESH, headers=_con_cookie(token))

    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["token_type"] == "bearer" and cuerpo["expires_in"] > 0
    datos = decodificar(cuerpo["access_token"])
    assert datos["user_id"] == str(usuario.id) and datos["empresa_id"] == str(empresa.id)
    cookie = _cookie(r)[refresco.COOKIE]
    assert cookie.value and cookie.value != token
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"].lower() == "lax"
    assert cookie["path"] == "/api/v1/auth"
    # el access token sirve como Bearer, con la empresa de la sesión
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {cuerpo['access_token']}"})
    assert me.status_code == 200 and me.json()["empresa"]["id"] == str(empresa.id)


def test_reusar_un_refresh_ya_rotado_cierra_la_sesion_entera(client, sesion):
    _, _, viejo = sesion
    nuevo = _cookie(client.post(REFRESH, headers=_con_cookie(viejo)))[refresco.COOKIE].value

    assert client.post(REFRESH, headers=_con_cookie(viejo)).status_code == 401  # replay
    assert client.post(REFRESH, headers=_con_cookie(nuevo)).status_code == 401  # la sesión quedó revocada


def test_logout_revoca_la_sesion_y_borra_la_cookie(client, db_session, sesion):
    usuario, _, token = sesion
    otra = refresco.emitir(db_session, usuario.id)  # otra sesión de la misma persona (otro navegador)

    r = client.post(LOGOUT, headers=_con_cookie(token))

    assert r.status_code == 204
    assert _cookie(r)[refresco.COOKIE]["max-age"] == "0"
    assert client.post(REFRESH, headers=_con_cookie(token)).status_code == 401
    assert client.post(REFRESH, headers=_con_cookie(otra)).status_code == 200, "solo se cierra esa sesión"
    assert client.post(LOGOUT, headers=XHR).status_code == 204  # sin cookie no hace nada


def test_sin_x_requested_with_da_403_y_no_toca_la_sesion(client, db_session, sesion):
    """CSRF (F07-P04): un formulario de otro sitio manda la cookie pero no puede poner la cabecera."""
    _, _, token = sesion
    solo_cookie = {"Cookie": f"{refresco.COOKIE}={token}"}

    for ruta in (REFRESH, LOGOUT):
        r = client.post(ruta, headers=solo_cookie)
        assert r.status_code == 403 and r.json()["detail"] == "Falta la cabecera X-Requested-With", ruta
        assert "set-cookie" not in r.headers

    fila = db_session.query(TokenRefresco).one()
    assert fila.rotado_at is None and fila.revocado_at is None
    assert client.post(REFRESH, headers=_con_cookie(token)).status_code == 200


def test_refresh_vencido_da_401(client, db_session, sesion):
    _, _, token = sesion
    db_session.query(TokenRefresco).update({"expira_at": utc_now() - timedelta(minutes=1)})
    db_session.commit()

    r = client.post(REFRESH, headers=_con_cookie(token))
    assert r.status_code == 401 and r.json()["detail"] == "La sesión venció"


@pytest.mark.parametrize("cambio", ["inactiva", "fuera_de_la_empresa"])
def test_cuenta_sin_acceso_da_401_y_revoca_la_sesion(client, db_session, sesion, cambio):
    usuario, empresa, token = sesion
    if cambio == "inactiva":
        usuario.activo = False
    else:
        db_session.execute(
            delete(core_usuario_empresa).where(
                core_usuario_empresa.c.usuario_id == usuario.id, core_usuario_empresa.c.empresa_id == empresa.id
            )
        )
    db_session.commit()

    r = client.post(REFRESH, headers=_con_cookie(token))

    assert r.status_code == 401 and r.json()["detail"] == "La cuenta ya no tiene acceso"
    assert db_session.query(TokenRefresco).filter(TokenRefresco.revocado_at.is_(None)).count() == 0


def test_el_token_no_se_guarda_en_claro(db_session, sesion):
    _, _, token = sesion
    fila = db_session.query(TokenRefresco).one()
    assert fila.jti != token and len(fila.jti) == 64
