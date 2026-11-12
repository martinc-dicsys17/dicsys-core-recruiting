"""Carga masiva: un nombre de archivo repetido dentro de la misma operacion es un duplicado por nombre.

El primer archivo de cada nombre se procesa normalmente; los siguientes (individuales o dentro de un ZIP) no se procesan, no crean
candidatos, no se comparan por contenido y se archivan en cv_duplicados con sufijo, sin sobrescribir nada.
"""

import io
import os
import zipfile

import pytest

from backend.modules.recruiting.models import Candidato
from backend.tests.integration.cv_candidatos.test_carga_cv_email import URL_MASIVO, _pdf, escenario  # noqa: F401


def _cv(nombre, email, puesto="Analista QA"):
    return _pdf(nombre, puesto, email, "Cordoba, Argentina")


def _archivos(tmp_path, carpeta):
    ruta = tmp_path / "cv_storage" / carpeta
    return sorted(os.listdir(ruta)) if ruta.exists() else []


def _leer(tmp_path, carpeta, nombre):
    return (tmp_path / "cv_storage" / carpeta / nombre).read_bytes()


def _masivo(client, headers, partes):
    files = [("archivos", (nombre, contenido, "application/octet-stream")) for nombre, contenido in partes]
    r = client.post(URL_MASIVO, headers=headers, files=files)
    assert r.status_code == 200
    return r.json()


def _zip(entradas):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nombre, contenido in entradas:
            z.writestr(nombre, contenido)
    return buffer.getvalue()


def _emails(db_session, empresa):  # noqa: F811
    return sorted(c.email for c in db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).all())


CVS = [_cv(f"Persona {i}", f"persona{i}@example.com") for i in range(1, 5)]


def _verificar_cuatro_cv_pdf(body, tmp_path, db_session, empresa):  # noqa: F811
    # Contadores: 1 creado y 3 duplicados archivados, sin errores
    resumen = body["resumen"]
    assert (resumen["total_archivos"], resumen["creados"], resumen["duplicados_omitidos"]) == (4, 1, 3)
    assert (
        sum(v for k, v in resumen.items() if k not in ("lote_id", "total_archivos", "creados", "duplicados_omitidos"))
        == 0
    )
    assert body["procesados_exitosamente"] == 1 and body["fallidos"] == []
    # Solo se creo el candidato del primer archivo
    assert _emails(db_session, empresa) == ["persona1@example.com"]
    # El primero va a su destino normal y los repetidos a cv_duplicados, todos con su contenido original y sin sobrescribir
    assert _archivos(tmp_path, "cv_procesados_ok") == ["cv.pdf"]
    assert _leer(tmp_path, "cv_procesados_ok", "cv.pdf") == CVS[0]
    assert _archivos(tmp_path, "cv_duplicados") == ["cv.pdf", "cv_1.pdf", "cv_2.pdf"]
    assert [_leer(tmp_path, "cv_duplicados", n) for n in ("cv.pdf", "cv_1.pdf", "cv_2.pdf")] == CVS[1:]
    assert _archivos(tmp_path, "cv_errores") == []


@pytest.mark.integration
def test_cuatro_archivos_con_el_mismo_nombre_en_una_seleccion(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    body = _masivo(client, headers, [("cv.pdf", c) for c in CVS])
    _verificar_cuatro_cv_pdf(body, tmp_path, db_session, empresa)
    repetidos = [r for r in body["resultados"] if r["resultado"] == "duplicado"]
    assert len(repetidos) == 3 and all("nombre repetido" in r["mensaje"] for r in repetidos)


@pytest.mark.integration
def test_cuatro_archivos_con_el_mismo_nombre_dentro_de_un_zip(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    zip_cvs = _zip([(f"carpeta{i}/cv.pdf", c) for i, c in enumerate(CVS, 1)])
    body = _masivo(client, headers, [("lote.zip", zip_cvs)])
    _verificar_cuatro_cv_pdf(body, tmp_path, db_session, empresa)


@pytest.mark.integration
def test_nombre_repetido_entre_un_individual_y_un_zip_de_la_misma_carga(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    otro = _cv("Otra Persona", "otra@example.com")
    zip_cvs = _zip([("dentro/cv.pdf", CVS[1]), ("dentro/otro.pdf", otro)])
    body = _masivo(client, headers, [("cv.pdf", CVS[0]), ("lote.zip", zip_cvs)])
    assert (body["resumen"]["creados"], body["resumen"]["duplicados_omitidos"]) == (2, 1)
    assert _emails(db_session, empresa) == ["otra@example.com", "persona1@example.com"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["cv.pdf", "otro.pdf"]
    assert _archivos(tmp_path, "cv_duplicados") == ["cv.pdf"]
    assert _leer(tmp_path, "cv_duplicados", "cv.pdf") == CVS[1]


@pytest.mark.integration
def test_el_repetido_no_se_procesa_aunque_este_corrupto_o_vacio(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    corrupto = b"%PDF-1.4\n" + os.urandom(500)
    body = _masivo(client, headers, [("cv.pdf", CVS[0]), ("cv.pdf", corrupto), ("cv.pdf", b"")])
    assert (
        body["resumen"]["creados"],
        body["resumen"]["duplicados_omitidos"],
        body["resumen"]["sin_email"],
        body["resumen"]["errores_lectura"],
    ) == (1, 2, 0, 0)
    assert _emails(db_session, empresa) == ["persona1@example.com"]
    assert _archivos(tmp_path, "cv_duplicados") == ["cv.pdf", "cv_1.pdf"]
    assert (
        _leer(tmp_path, "cv_duplicados", "cv.pdf") == corrupto and _leer(tmp_path, "cv_duplicados", "cv_1.pdf") == b""
    )
    assert _archivos(tmp_path, "cv_errores") == []


@pytest.mark.integration
def test_el_duplicado_por_email_sigue_funcionando_con_nombres_distintos(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    mismo_email = _cv("Persona Uno", "persona1@example.com", "Desarrollador Backend")
    body = _masivo(client, headers, [("uno.pdf", CVS[0]), ("dos.pdf", mismo_email)])
    assert (body["resumen"]["creados"], body["resumen"]["duplicados_omitidos"]) == (1, 1)
    repetido = [r for r in body["resultados"] if r["resultado"] == "duplicado"][0]
    assert "Ya existe un candidato" in repetido["mensaje"] and "nombre repetido" not in repetido["mensaje"]
    assert _emails(db_session, empresa) == ["persona1@example.com"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["uno.pdf"] and _archivos(tmp_path, "cv_duplicados") == [
        "dos.pdf"
    ]


@pytest.mark.integration
def test_la_regla_no_aplica_entre_cargas_distintas(client, escenario, db_session, tmp_path):  # noqa: F811
    headers, empresa = escenario
    primera = _masivo(client, headers, [("cv.pdf", CVS[0])])
    segunda = _masivo(client, headers, [("cv.pdf", CVS[1])])  # misma carga distinta: el nombre no cuenta como repetido
    assert primera["resumen"]["creados"] == 1 and segunda["resumen"]["creados"] == 1
    assert _emails(db_session, empresa) == ["persona1@example.com", "persona2@example.com"]
    assert _archivos(tmp_path, "cv_procesados_ok") == ["cv.pdf", "cv_1.pdf"]  # sufijo: no se sobrescribe
    assert _archivos(tmp_path, "cv_duplicados") == []
