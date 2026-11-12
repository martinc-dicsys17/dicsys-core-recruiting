"""Magic links: en la base solo el SHA-256 del token; el link del email sigue andando (F02-P03)."""

import re
import secrets

import pytest

from backend.modules.usuarios import secretos
from backend.modules.usuarios.models import Usuario
from backend.modules.usuarios.services import UsuarioService

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


def _token_del_email(fake_email) -> str:
    html = fake_email.messages[-1]["html"]
    return re.search(r"/set-password\?token=([A-Za-z0-9_\-]+)", html).group(1)


def _alta_con_magic_link(db_session) -> Usuario:
    return UsuarioService.crear_usuario(
        db_session,
        {
            "email": f"magic-{secrets.token_hex(4)}@example.com",
            "nombre": "Magic",
            "apellido": "Link",
            "rol": "usuario",
            "activo": True,
            "solicitar_password": True,
        },
        "test",
    )


def test_el_alta_guarda_el_hash_y_manda_el_token_en_claro(db_session, fake_email):
    usuario = _alta_con_magic_link(db_session)
    token = _token_del_email(fake_email)
    assert usuario.magic_link_token == secretos.hash_magic_link(token)
    assert token not in usuario.magic_link_token


def test_el_link_del_email_establece_la_contrasena_una_sola_vez(client, db_session, fake_email):
    usuario = _alta_con_magic_link(db_session)
    token = _token_del_email(fake_email)

    r = client.get(f"/api/v1/usuarios/magic-link/validar/{token}")
    assert r.status_code == 200 and r.json()["email"] == usuario.email
    # el hash guardado no sirve como token: hay que tener el link del email
    assert client.get(f"/api/v1/usuarios/magic-link/validar/{usuario.magic_link_token}").status_code == 400

    r = client.post(
        "/api/v1/usuarios/magic-link/set-password",
        json={"token": token, "password": "una-clave-nueva-larga", "confirmar_password": "una-clave-nueva-larga"},
    )
    assert r.status_code == 200, r.text
    db_session.refresh(usuario)
    assert usuario.verify_password("una-clave-nueva-larga") and usuario.magic_link_token is None
    r = client.post(
        "/api/v1/usuarios/magic-link/set-password",
        json={"token": token, "password": "otra-clave-nueva-larga", "confirmar_password": "otra-clave-nueva-larga"},
    )
    assert r.status_code == 400


def test_reenviar_genera_un_link_nuevo_y_el_anterior_deja_de_valer(client, db_session, fake_email):
    usuario = _alta_con_magic_link(db_session)
    anterior = _token_del_email(fake_email)
    assert UsuarioService.reenviar_magic_link(db_session, str(usuario.id))
    nuevo = _token_del_email(fake_email)
    assert nuevo != anterior
    assert client.get(f"/api/v1/usuarios/magic-link/validar/{anterior}").status_code == 400
    assert client.get(f"/api/v1/usuarios/magic-link/validar/{nuevo}").status_code == 200


def test_un_link_pendiente_en_claro_sigue_andando_despues_de_hashearlo(client, data_factory, db_session):
    """Lo que hace la migración con los pendientes de antes del cambio: el link que el usuario tiene sigue valiendo."""
    usuario = data_factory.usuario()
    viejo = secrets.token_urlsafe(32)
    usuario.magic_link_token = viejo
    db_session.flush()
    assert client.get(f"/api/v1/usuarios/magic-link/validar/{viejo}").status_code == 400, "en claro ya no se busca"

    usuario.magic_link_token = secretos.hash_magic_link(viejo)
    db_session.flush()
    assert client.get(f"/api/v1/usuarios/magic-link/validar/{viejo}").status_code == 200


def test_las_contrasenas_que_no_coinciden_dan_422(client, db_session, fake_email):
    """Antes el validador usaba la firma de Pydantic v1 y tiraba TypeError (500) en cualquier pedido."""
    _alta_con_magic_link(db_session)
    token = _token_del_email(fake_email)
    r = client.post(
        "/api/v1/usuarios/magic-link/set-password",
        json={"token": token, "password": "una-clave-nueva-larga", "confirmar_password": "otra-distinta-larga"},
    )
    assert r.status_code == 422 and "no coinciden" in r.text


def test_cambiar_la_contrasena_de_un_usuario_valida_la_confirmacion(client, data_factory):
    from backend.tests.helpers.auth import auth_headers

    usuario = data_factory.usuario(password="la-clave-actual-larga", rol="admin")
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    headers = auth_headers(usuario, empresa)
    r = client.put(
        f"/api/v1/usuarios/{usuario.id}/password",
        headers=headers,
        json={
            "password_actual": "la-clave-actual-larga",
            "password_nueva": "una-clave-nueva-larga",
            "confirmar_password": "otra-distinta-larga",
        },
    )
    assert r.status_code == 422 and "no coinciden" in r.text
    r = client.put(
        f"/api/v1/usuarios/{usuario.id}/password",
        headers=headers,
        json={
            "password_actual": "la-clave-actual-larga",
            "password_nueva": "una-clave-nueva-larga",
            "confirmar_password": "una-clave-nueva-larga",
        },
    )
    assert r.status_code == 200, r.text
