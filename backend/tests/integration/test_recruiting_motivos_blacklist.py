"""Catálogo de motivos de Blacklist (GET /api/v1/recruiting/blacklist/motivos): mismo permiso que los motivos de
descarte (ítem gestion_busquedas), lectura desde la base y orden de carga."""

import uuid

import pytest

from backend.modules.recruiting.models import RecruitingMotivoBlacklist
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/blacklist/motivos"
URL_DESCARTE = "/api/v1/recruiting/motivos-descarte?etapa=SCREENING"
MOTIVOS = [
    "Conducta inapropiada",
    "Datos falsos en el CV",
    "Abandono del proceso",
    "Incumplimiento de acuerdos",
    "Conflicto de intereses",
    "Otro motivo",
]


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def motivos(db_session):
    """create_all no corre la migración: se cargan los seis como lo hace la 0007."""
    db_session.add_all([RecruitingMotivoBlacklist(id=n, motivo=m) for n, m in enumerate(MOTIVOS, start=1)])
    db_session.commit()


def _usuario_con_permisos(data_factory, empresa, permisos):
    usuario = data_factory.usuario()
    grupo = data_factory.grupo(nombre=f"Recruiting {uuid.uuid4().hex[:6]}")
    data_factory.permisos(grupo, permisos)
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    return usuario


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401


def test_sin_el_item_gestion_busquedas_responde_403(client, data_factory, empresa):
    usuario = _usuario_con_permisos(data_factory, empresa, ["recruiting", "recruiting.candidatos"])
    headers = auth_headers(usuario, empresa)
    assert client.get(URL_DESCARTE, headers=headers).status_code == 403  # igual que los motivos de descarte
    assert client.get(URL, headers=headers).status_code == 403


def test_devuelve_los_seis_motivos_en_orden_con_id(client, data_factory, empresa, motivos):
    usuario = _usuario_con_permisos(data_factory, empresa, ["recruiting", "recruiting.gestion_busquedas"])
    respuesta = client.get(URL, headers=auth_headers(usuario, empresa))

    assert respuesta.status_code == 200
    assert respuesta.json() == [{"id": n, "motivo": m} for n, m in enumerate(MOTIVOS, start=1)]


def test_el_admin_accede_y_la_lista_vacia_es_una_lista(client, data_factory, empresa):
    admin = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(admin, empresa)
    respuesta = client.get(URL, headers=auth_headers(admin, empresa))

    assert respuesta.status_code == 200
    assert respuesta.json() == []
