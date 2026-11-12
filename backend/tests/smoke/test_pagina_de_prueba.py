"""Página de prueba de la sesión del navegador (F07-P12): se sirve solo con la bandera y llama a endpoints que existen."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import create_app

pytestmark = [pytest.mark.smoke]

PAGINA = Path(__file__).resolve().parents[2] / "prueba" / "sesion.html"


def _cliente(monkeypatch, prendida: bool) -> TestClient:
    monkeypatch.setattr(settings, "pagina_de_prueba_de_sesion", prendida)
    return TestClient(create_app(testing=True))


def test_sin_la_bandera_no_se_sirve(monkeypatch):
    assert _cliente(monkeypatch, False).get("/prueba/sesion.html").status_code == 404


def test_con_la_bandera_se_sirve_en_el_origen_de_la_api(monkeypatch):
    r = _cliente(monkeypatch, True).get("/prueba/sesion.html")

    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "Prueba de la sesión del navegador" in r.text


def test_cada_llamada_de_la_pagina_es_una_operacion_de_la_api(monkeypatch):
    paths = _cliente(monkeypatch, False).get("/openapi.json").json()["paths"]
    llamadas = set(re.findall(r"pedir\('(\w+)', '([^']+)'", PAGINA.read_text(encoding="utf-8")))

    assert len(llamadas) == 9, llamadas
    for metodo, ruta in llamadas:
        assert metodo.lower() in paths.get(f"/api/v1{ruta}", {}), f"{metodo} /api/v1{ruta} no está en la API"
    # la descarga arma la ruta con el id del recibo
    assert "get" in paths["/api/v1/recibos/descargar/{recibo_id}/{tipo}"]
