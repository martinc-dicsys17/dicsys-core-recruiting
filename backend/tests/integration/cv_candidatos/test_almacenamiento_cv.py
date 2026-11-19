"""Almacenamiento físico de los CV archivados (CV_STORAGE_DIR) y su lectura desde Parámetros > Archivos de CV.

Producción daba 0 archivos porque ./data/cv era de root y el backend (uid 1000) no podía crear las carpetas: el
archivado fallaba en el log y Parámetros leía carpetas inexistentes como vacías. Estas pruebas cubren la preparación
de las carpetas, el recorrido carga -> archivo físico -> conteo, y que un problema de acceso no se informe como cero.
"""

import os
import sys
from pathlib import Path

import pytest

from backend.modules.recruiting.services import CandidatoService
from backend.tests.integration.cv_candidatos.test_carga_cv_email import (  # noqa: F401
    CV_VALIDO,
    _subir,
    escenario,
)

URL_RESUMEN = "/api/v1/recruiting/parametros/archivos-cv"
CARPETAS = ("cv_procesados_ok", "cv_duplicados", "cv_errores")

sin_permisos_posix = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="los permisos POSIX no restringen a root ni aplican en Windows",
)


@pytest.fixture
def raiz(tmp_path) -> Path:
    """La raíz configurada por el conftest de la carpeta (CV_STORAGE_DIR aislado en tmp_path)."""
    ruta = Path(CandidatoService._raiz_cv_storage())
    assert ruta == tmp_path / "cv_storage"
    return ruta


@pytest.fixture
def solo_lectura():
    """Deja carpetas en 0555 durante la prueba y les devuelve los permisos al terminar (para limpiar tmp_path)."""
    rutas = []

    def aplicar(ruta: Path) -> Path:
        ruta.chmod(0o555)
        rutas.append(ruta)
        return ruta

    yield aplicar
    for ruta in rutas:
        ruta.chmod(0o755)


def _resumen(client, headers):
    r = client.get(URL_RESUMEN, headers=headers)
    return r, ({c["carpeta"]: c for c in r.json()} if r.status_code == 200 else {})


# --- Preparación al arrancar ---


@pytest.mark.integration
def test_preparar_crea_las_tres_carpetas_en_la_ruta_configurada(raiz):
    assert not raiz.exists()
    assert CandidatoService.preparar_cv_storage() is None
    assert sorted(p.name for p in raiz.iterdir()) == sorted(CARPETAS)
    assert all((raiz / c).is_dir() for c in CARPETAS)
    assert CandidatoService.preparar_cv_storage() is None  # idempotente: no falla ni duplica


@pytest.mark.integration
@sin_permisos_posix
def test_preparar_informa_una_raiz_sin_permisos(raiz, solo_lectura):
    raiz.mkdir()
    solo_lectura(raiz)  # como el bind mount de root que dejó Docker en producción
    problema = CandidatoService.preparar_cv_storage()
    assert problema and "no existe y no se puede crear" in problema
    assert list(raiz.iterdir()) == []


# --- Recorrido completo: carga desde Candidatos -> archivo físico -> Parámetros ---


@pytest.mark.integration
def test_cv_cargado_desde_candidatos_se_encuentra_y_se_cuenta_en_parametros(client, escenario, raiz):  # noqa: F811
    headers, _ = escenario
    assert _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf").status_code == 201

    archivo = raiz / "cv_procesados_ok" / "Laura Gomez.pdf"
    assert archivo.is_file() and archivo.read_bytes() == CV_VALIDO  # existe físicamente en CV_STORAGE_DIR

    r, carpetas = _resumen(client, headers)
    assert r.status_code == 200, r.text
    assert carpetas["cv_procesados_ok"]["cantidad_archivos"] == 1
    assert carpetas["cv_procesados_ok"]["tamano_total_bytes"] == len(CV_VALIDO)
    assert carpetas["cv_duplicados"]["cantidad_archivos"] == 0
    assert carpetas["cv_errores"]["cantidad_archivos"] == 0

    detalle = client.get(f"{URL_RESUMEN}/cv_procesados_ok", headers=headers)
    assert detalle.status_code == 200, detalle.text
    assert [a["nombre"] for a in detalle.json()["archivos"]] == ["Laura Gomez.pdf"]


@pytest.mark.integration
def test_parametros_cuenta_lo_que_hay_en_disco(client, escenario, raiz):  # noqa: F811
    headers, _ = escenario
    (raiz / "cv_errores").mkdir(parents=True)
    (raiz / "cv_errores" / "a.pdf").write_bytes(b"12345")
    (raiz / "cv_errores" / "b.pdf").write_bytes(b"123")
    (raiz / "cv_errores" / ".motivos.jsonl").write_text("{}\n")  # índice oculto: no cuenta

    r, carpetas = _resumen(client, headers)
    assert r.status_code == 200, r.text
    assert (carpetas["cv_errores"]["cantidad_archivos"], carpetas["cv_errores"]["tamano_total_bytes"]) == (2, 8)


# --- Directorios inexistentes y errores de acceso ---


@pytest.mark.integration
def test_parametros_sin_carpetas_creadas_todavia_informa_cero(client, escenario, raiz):  # noqa: F811
    headers, _ = escenario
    assert not raiz.exists()  # instalación nueva: la primera carga las crea
    r, carpetas = _resumen(client, headers)
    assert r.status_code == 200, r.text
    assert all(carpetas[c]["cantidad_archivos"] == 0 for c in CARPETAS)


@pytest.mark.integration
@sin_permisos_posix
def test_parametros_con_raiz_sin_permisos_da_error_y_no_cero(client, escenario, raiz, solo_lectura):  # noqa: F811
    headers, _ = escenario
    raiz.mkdir()
    solo_lectura(raiz)  # el caso de producción: raíz de root, sin subcarpetas

    r, _ = _resumen(client, headers)
    assert r.status_code == 503
    assert "almacenamiento de CV no está disponible" in r.json()["detail"]
    assert client.get(f"{URL_RESUMEN}/cv_procesados_ok", headers=headers).status_code == 503


@pytest.mark.integration
@sin_permisos_posix
def test_parametros_con_subcarpeta_sin_escritura_da_error(client, escenario, raiz, solo_lectura):  # noqa: F811
    headers, _ = escenario
    (raiz / "cv_procesados_ok").mkdir(parents=True)
    (raiz / "cv_procesados_ok" / "cv.pdf").write_bytes(b"x")
    solo_lectura(raiz / "cv_procesados_ok")  # se lista, pero ningún CV nuevo podría archivarse ahí

    r, _ = _resumen(client, headers)
    assert r.status_code == 503


@pytest.mark.integration
def test_parametros_con_raiz_que_es_un_archivo_da_error(client, escenario, raiz):  # noqa: F811
    headers, _ = escenario
    raiz.write_bytes(b"")
    r, _ = _resumen(client, headers)
    assert r.status_code == 503


@pytest.mark.integration
def test_carpeta_no_valida_sigue_siendo_404(client, escenario):  # noqa: F811
    headers, _ = escenario
    assert client.get(f"{URL_RESUMEN}/otra", headers=headers).status_code == 404
