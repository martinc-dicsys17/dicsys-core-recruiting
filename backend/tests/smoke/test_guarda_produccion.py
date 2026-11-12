"""Guarda de arranque: en producción no se arranca con DEBUG ni con los secretos del .env.template (F02-P05)."""

import pytest
from pydantic import ValidationError

from backend.core.config import Settings

pytestmark = [pytest.mark.smoke]

PROPIA = dict(
    app_name="Dicsys Core",
    app_version="test",
    debug=False,
    host="0.0.0.0",
    port=6001,
    reload=False,
    secret_key="una-clave-propia-de-32-bytes-o-mas-0000",
    jwt_secret_key="otra-clave-propia-de-32-bytes-o-mas-00",
    jwt_algorithm="HS256",
    jwt_expire_minutes=30,
    database_url="postgresql://app:clave-propia@db:5432/core",
    cors_origins=["http://localhost"],
    environment="production",
)


def _settings(**cambios) -> Settings:
    return Settings(_env_file=None, **{**PROPIA, **cambios})


def test_produccion_con_configuracion_propia_arranca():
    assert _settings().environment == "production"


@pytest.mark.parametrize(
    "cambios,motivo",
    [
        ({"debug": True}, "DEBUG está activo"),
        ({"secret_key": "tu-clave-secreta-aqui-cambiar-en-produccion"}, "SECRET_KEY es el valor de ejemplo"),
        ({"jwt_secret_key": "jwt-secret-key-cambiar-en-produccion"}, "JWT_SECRET_KEY es el valor de ejemplo"),
        (
            {"database_url": "postgresql://postgres:postgres123@db:5432/core"},
            "DATABASE_URL usa la contraseña de ejemplo",
        ),
    ],
)
def test_produccion_no_arranca_con_debug_o_secretos_del_template(cambios, motivo):
    with pytest.raises(ValidationError, match=motivo):
        _settings(**cambios)


def test_los_problemas_se_informan_juntos():
    with pytest.raises(ValidationError) as error:
        _settings(debug=True, jwt_secret_key="jwt-secret-key-cambiar-en-produccion")
    assert "DEBUG está activo" in str(error.value) and "JWT_SECRET_KEY" in str(error.value)


@pytest.mark.parametrize("entorno", ["development", "testing"])
def test_fuera_de_produccion_no_se_controla(entorno):
    assert (
        _settings(
            environment=entorno,
            debug=True,
            secret_key="tu-clave-secreta-aqui-cambiar-en-produccion",
            jwt_secret_key="jwt-secret-key-cambiar-en-produccion",
        ).debug
        is True
    )
