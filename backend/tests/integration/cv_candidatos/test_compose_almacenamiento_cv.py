"""El compose de producción deja el almacenamiento de CV preparado y consistente entre servicios.

Sin esto, una carpeta del host creada por Docker como root deja al backend (uid 1000) sin poder archivar CV, y
Parámetros > Archivos de CV informa 0 (lo que pasó en producción con ./data/cv).
"""

import re
from pathlib import Path

import pytest
import yaml

from backend.modules.recruiting.services import CandidatoService

RAIZ_REPO = Path(__file__).resolve().parents[4]
COMPOSE = RAIZ_REPO / "docker-compose.yml"  # en el contenedor de tests lo monta docker-compose.test.yml
DOCKERFILE = RAIZ_REPO / "backend" / "Dockerfile"
SERVICIOS_CON_CV = ("backend", "scheduler")


@pytest.fixture(scope="module")
def compose() -> dict:
    if not COMPOSE.exists():
        pytest.fail(f"No se encontró {COMPOSE}: montarlo en el contenedor de tests (docker-compose.test.yml)")
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _uid_del_backend() -> str:
    m = re.search(r"useradd --uid (\d+)", DOCKERFILE.read_text(encoding="utf-8"))
    assert m, "el Dockerfile del backend debe crear su usuario con un uid fijo"
    return m.group(1)


def _comando(servicio: dict) -> str:
    cmd = servicio["command"]
    return cmd if isinstance(cmd, str) else " ".join(cmd)


def test_cv_storage_init_crea_las_carpetas_de_cv_y_las_da_al_uid_del_backend(compose):
    init = compose["cv-storage-init"]
    assert init["user"] == "0:0" and init["restart"] == "no"
    assert "./data/cv:/data/cv" in init["volumes"]
    comando = _comando(init)
    for carpeta in (
        CandidatoService.CARPETA_CV_OK,
        CandidatoService.CARPETA_CV_DUPLICADOS,
        CandidatoService.CARPETA_CV_ERRORES,
    ):
        assert f"/data/cv/{carpeta}" in comando
    uid = _uid_del_backend()
    m = re.search(r"chown -R (\d+):(\d+) ([^\n]+)", comando)
    assert m and m.group(1) == uid and m.group(2) == uid
    assert "/data/cv" in m.group(3).split()
    assert not re.search(r"\brm\b|\bmv\b", comando)  # nunca borra ni mueve CV existentes


def test_backend_y_scheduler_esperan_a_cv_storage_init(compose):
    for nombre in SERVICIOS_CON_CV:
        assert compose[nombre]["depends_on"]["cv-storage-init"]["condition"] == "service_completed_successfully"


def test_backend_y_scheduler_usan_el_mismo_almacenamiento_de_cv(compose):
    for nombre in SERVICIOS_CON_CV:
        servicio = compose[nombre]
        destino = servicio["environment"]["CV_STORAGE_DIR"]
        assert destino == "/data/cv"
        assert f"./data/cv:{destino}" in servicio["volumes"], f"{nombre}: CV_STORAGE_DIR sin bind mount persistente"
