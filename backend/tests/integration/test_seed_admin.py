"""Admin que crea el seed en una base vacía: sin contraseña fija en el código (F02-P04)."""

import pytest

from backend.core.config import settings
from backend.core.seed_data import ADMIN_DEFAULT_SEED
from backend.modules.usuarios.services import UsuarioService

pytestmark = [pytest.mark.integration]


def test_el_seed_no_trae_contrasena():
    assert "password" not in ADMIN_DEFAULT_SEED


def test_el_admin_usa_seed_admin_password(db_session, monkeypatch):
    monkeypatch.setattr(settings, "seed_admin_password", "clave-de-desarrollo-123")
    admin = UsuarioService.crear_usuario_admin_default(db_session)
    assert admin is not None and admin.email == ADMIN_DEFAULT_SEED["email"] and admin.rol == "admin"
    assert admin.verify_password("clave-de-desarrollo-123")
    assert not admin.verify_password("admin")


def test_sin_seed_admin_password_la_contrasena_es_aleatoria(db_session, monkeypatch):
    monkeypatch.setattr(settings, "seed_admin_password", "")
    admin = UsuarioService.crear_usuario_admin_default(db_session)
    assert admin is not None
    assert not admin.verify_password("admin") and not admin.verify_password("")


def test_con_usuarios_no_crea_el_admin(db_session, data_factory):
    data_factory.usuario()
    assert UsuarioService.crear_usuario_admin_default(db_session) is None
