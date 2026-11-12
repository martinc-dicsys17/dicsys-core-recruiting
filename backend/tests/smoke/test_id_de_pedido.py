"""X-Request-ID (F06-P06): cada pedido tiene un id, el que llega o uno nuevo, y va en la respuesta y en los logs."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

from backend.core.pedido import ID_PEDIDO, FiltroIdDePedido
from backend.main import create_app

pytestmark = [pytest.mark.smoke]


@pytest.fixture
def cliente():
    app = create_app(testing=True)

    @app.get("/_id-del-pedido")
    def id_del_pedido():
        return {"id": ID_PEDIDO.get()}

    return TestClient(app)


def test_sin_cabecera_genera_uno_y_es_el_del_pedido(cliente):
    r = cliente.get("/_id-del-pedido")

    assert re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])
    assert r.json()["id"] == r.headers["x-request-id"]


def test_el_que_llega_se_usa_y_vuelve(cliente):
    r = cliente.get("/_id-del-pedido", headers={"X-Request-ID": "flask-1b2c.3_d"})

    assert r.headers["x-request-id"] == "flask-1b2c.3_d" == r.json()["id"]


@pytest.mark.parametrize("raro", ["con espacio", "x" * 129, "<script>", "a\\b"])
def test_uno_sin_forma_de_id_se_reemplaza(cliente, raro):
    r = cliente.get("/_id-del-pedido", headers={"X-Request-ID": raro})

    assert r.headers["x-request-id"] != raro and re.fullmatch(r"[0-9a-f]{32}", r.headers["x-request-id"])


def test_tambien_lo_llevan_los_errores(cliente):
    r = cliente.get("/api/v1/auth/me", headers={"X-Request-ID": "pedido-401"})

    assert r.status_code == 401 and r.headers["x-request-id"] == "pedido-401"


def test_los_logs_llevan_el_id_del_pedido_y_fuera_de_uno_un_guion():
    filtro = FiltroIdDePedido()
    registro = logging.LogRecord("x", logging.INFO, __file__, 1, "hola", None, None)

    token = ID_PEDIDO.set("abc123")
    try:
        filtro.filter(registro)
        assert registro.id_pedido == "abc123"
    finally:
        ID_PEDIDO.reset(token)
    filtro.filter(registro)
    assert registro.id_pedido == "-"
