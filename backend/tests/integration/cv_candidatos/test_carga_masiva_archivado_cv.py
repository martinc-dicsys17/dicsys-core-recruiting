"""Archivado de CV de la carga masiva segun el resultado final (cv_procesados_ok / cv_duplicados / cv_errores)."""

import os

import pytest

from backend.modules.recruiting.services import CandidatoService


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_STORAGE_DIR", str(tmp_path / "cv"))
    return tmp_path / "cv"


@pytest.mark.parametrize(
    "resultado,carpeta",
    [
        ("creado", "cv_procesados_ok"),
        ("duplicado", "cv_duplicados"),
        ("sin_email", "cv_errores"),
        ("error_persistencia", "cv_errores"),
        ("error_validacion", "cv_errores"),
        ("error_otro", "cv_errores"),
    ],
)
def test_clasifica_por_resultado_y_crea_carpetas(raiz, resultado, carpeta):
    CandidatoService._archivar_cv_masivo("Laura Gomez.pdf", b"contenido", resultado)
    assert (raiz / carpeta / "Laura Gomez.pdf").read_bytes() == b"contenido"
    assert [p.name for p in raiz.iterdir()] == [carpeta]


def test_nombre_repetido_no_sobrescribe(raiz):
    CandidatoService._archivar_cv_masivo("cv.pdf", b"uno", "creado")
    CandidatoService._archivar_cv_masivo("cv.pdf", b"dos", "creado")
    assert (raiz / "cv_procesados_ok" / "cv.pdf").read_bytes() == b"uno"
    assert (raiz / "cv_procesados_ok" / "cv_1.pdf").read_bytes() == b"dos"


def test_nombre_con_ruta_no_escapa_de_la_carpeta(raiz):
    CandidatoService._archivar_cv_masivo("../../fuera/cv.pdf", b"x", "sin_email")
    assert (raiz / "cv_errores" / "cv.pdf").exists()
    assert not (raiz.parent / "fuera").exists()


def test_error_de_escritura_no_interrumpe(tmp_path, monkeypatch):
    archivo = tmp_path / "es_un_archivo"
    archivo.write_bytes(b"")
    monkeypatch.setenv("CV_STORAGE_DIR", str(archivo))  # no se puede crear una carpeta dentro de un archivo
    CandidatoService._archivar_cv_masivo("cv.pdf", b"x", "creado")  # solo registra en el log, no lanza
    assert os.path.isfile(archivo)
