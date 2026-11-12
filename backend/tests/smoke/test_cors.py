"""CORS para la SPA de Vite en desarrollo, sin el proxy de origen único (F07-P10)."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.core.config import Settings, settings
from backend.main import create_app
from backend.tests.smoke.test_guarda_produccion import PROPIA

pytestmark = [pytest.mark.smoke]

VITE = "http://localhost:5173"


@pytest.fixture
def cliente(monkeypatch):
    monkeypatch.setattr(settings, "cors_origins", [VITE])
    return TestClient(create_app(testing=True))


def _preflight(cliente, origen):
    return cliente.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-requested-with",
        },
    )


def test_vite_puede_pedir_el_refresh_con_credenciales_y_otro_origen_no(cliente):
    vite = _preflight(cliente, VITE)
    otro = _preflight(cliente, "https://otro.example")

    assert vite.status_code == 200
    assert vite.headers["access-control-allow-origin"] == VITE
    assert vite.headers["access-control-allow-credentials"] == "true"
    assert "x-requested-with" in vite.headers["access-control-allow-headers"].lower()
    assert otro.status_code == 400 and "access-control-allow-origin" not in otro.headers


def test_la_spa_en_otro_origen_puede_leer_el_retry_after_y_el_id_de_pedido(cliente):
    r = cliente.get("/", headers={"Origin": VITE})

    assert r.headers["access-control-allow-origin"] == VITE
    assert r.headers["access-control-expose-headers"] == "Retry-After, X-Request-ID"


def test_cors_origins_no_admite_el_comodin():
    with pytest.raises(ValidationError, match='CORS_ORIGINS no admite "\\*"'):
        Settings(_env_file=None, **{**PROPIA, "cors_origins": ["https://core.dicsys.ai", "*"]})
