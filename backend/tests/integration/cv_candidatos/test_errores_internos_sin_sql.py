"""Errores internos (500) de la carga de CV: la respuesta no expone SQL ni detalles tecnicos y el log conserva la causa."""

import logging

import pytest
from sqlalchemy import event

from backend.modules.recruiting import services as recruiting_services
from backend.modules.recruiting.services import MENSAJE_ERROR_INTERNO, CandidatoService
from backend.tests.integration.cv_candidatos.test_carga_cv_email import CV_VALIDO, URL_MASIVO, _pdf, _subir, escenario  # noqa: F401
from backend.tests.integration.cv_candidatos.test_carga_individual_archivado_cv import CV_DISTINTO, _actualizar  # noqa: F401

SQL_FILTRADO = (
    '(psycopg2.errors.UndefinedColumn) column "columna_secreta" does not exist\n'
    "SQL: INSERT INTO candidatos (columna_secreta) VALUES (%(p)s) [parameters: {'p': 'x'}]"
)
PALABRAS_PROHIBIDAS = ("INSERT", "SELECT", "INTO candidatos", "columna_secreta", "psycopg2", "parameters", "Traceback")


def _sin_detalles(texto):
    for palabra in PALABRAS_PROHIBIDAS:
        assert palabra not in texto, palabra


def test_individual_500_inesperado_no_expone_el_error(client, escenario, monkeypatch, caplog):  # noqa: F811
    headers, _ = escenario

    async def falla(*args, **kwargs):
        raise RuntimeError(SQL_FILTRADO)

    monkeypatch.setattr(CandidatoService, "crear_desde_cv", staticmethod(falla))
    with caplog.at_level(logging.ERROR):
        r = _subir(client, headers, CV_VALIDO, "a.pdf")
    assert r.status_code == 500
    assert r.json() == {"detail": MENSAJE_ERROR_INTERNO}
    _sin_detalles(r.text)
    assert "columna_secreta" in caplog.text  # el detalle tecnico queda en el log


@pytest.mark.integration
def test_actualizacion_con_fallo_de_persistencia_no_expone_sql(client, escenario, db_session, caplog):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201
    assert _subir(client, headers, CV_DISTINTO, "nuevo.pdf").status_code == 409

    def _rechazar(session, flush_context, instances):
        raise RuntimeError(SQL_FILTRADO)

    event.listen(db_session, "before_flush", _rechazar)
    try:
        with caplog.at_level(logging.ERROR):
            r = _actualizar(client, headers, CV_DISTINTO, "nuevo.pdf")
    finally:
        event.remove(db_session, "before_flush", _rechazar)
    assert r.status_code == 500
    _sin_detalles(r.text)
    assert "columna_secreta" in caplog.text


@pytest.mark.integration
def test_masivo_error_otro_y_persistencia_no_exponen_detalles(client, escenario, monkeypatch, caplog):  # noqa: F811
    headers, _ = escenario

    def falla(db, empresa_id, contenido, nombre_archivo, usuario, current_user):
        if nombre_archivo == "uno.pdf":
            raise RuntimeError(SQL_FILTRADO)
        raise recruiting_services.CVPersistenciaError("dos@example.com", RuntimeError(SQL_FILTRADO))

    monkeypatch.setattr(CandidatoService, "procesar_cv_bytes", staticmethod(falla))
    files = [("archivos", (n, _pdf(n, "dos@example.com"), "application/pdf")) for n in ("uno.pdf", "dos.pdf")]
    with caplog.at_level(logging.ERROR):
        r = client.post(URL_MASIVO, headers=headers, files=files)
    assert r.status_code == 200
    body = r.json()
    _sin_detalles(r.text)
    por_archivo = {x["archivo"]: x for x in body["resultados"]}
    assert (
        por_archivo["uno.pdf"]["resultado"] == "error_otro"
        and por_archivo["uno.pdf"]["mensaje"] == MENSAJE_ERROR_INTERNO
    )
    assert por_archivo["dos.pdf"]["resultado"] == "error_persistencia"
    assert body["resumen"]["errores_otros"] == 1 and body["resumen"]["errores_persistencia"] == 1
    assert body["creados"] == 0
    assert "columna_secreta" in caplog.text


def test_errores_esperados_mantienen_mensaje_y_codigo(client, escenario):  # noqa: F811
    headers, _ = escenario
    r = _subir(client, headers, b"", "vacio.pdf")
    assert r.status_code == 422 and r.json()["detail"] != MENSAJE_ERROR_INTERNO
    _subir(client, headers, CV_VALIDO, "ok.pdf")
    r = _subir(client, headers, CV_DISTINTO, "otro.pdf")
    assert r.status_code == 409 and r.json()["requiere_comparacion"] is True
