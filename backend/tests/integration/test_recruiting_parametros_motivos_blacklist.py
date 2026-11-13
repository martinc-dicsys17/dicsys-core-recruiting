"""ABM de motivos de Blacklist en Parámetros de Recruiting (/api/v1/recruiting/parametros/motivos-blacklist): permiso del
ítem «parametros» (y nada para EXTERNOS), listado, alta, edición y baja sobre recruiting_motivos_blacklist, con nombres
sin tildes y sin duplicados equivalentes."""

import uuid

import pytest
from sqlalchemy import text

from backend.modules.recruiting.models import RecruitingMotivoBlacklist
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/parametros/motivos-blacklist"
PERMISOS = ["recruiting", "recruiting.parametros"]
MOTIVOS = ["Conducta inapropiada", "Datos falsos en el CV", "Otro motivo"]


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def usuario_con_grupo(data_factory, empresa):
    def crear(permisos=PERMISOS, nombre_grupo=None):
        usuario = data_factory.usuario()
        grupo = data_factory.grupo(nombre=nombre_grupo or f"Recruiting {uuid.uuid4().hex[:6]}")
        data_factory.permisos(grupo, permisos)
        data_factory.asignar_empresa(usuario, empresa)
        data_factory.asignar_grupo(usuario, grupo, empresa)
        return usuario

    return crear


@pytest.fixture
def cabeceras(usuario_con_grupo, empresa):
    return auth_headers(usuario_con_grupo(), empresa)


@pytest.fixture
def motivos(db_session):
    """create_all no corre la migración: se cargan algunos como lo hace la 0007."""
    filas = [RecruitingMotivoBlacklist(id=n, motivo=m) for n, m in enumerate(MOTIVOS, start=1)]
    db_session.add_all(filas)
    db_session.flush()
    db_session.execute(  # con ids explícitos la secuencia no avanza: la 0007 también la deja en el máximo
        text("SELECT setval(pg_get_serial_sequence('recruiting_motivos_blacklist', 'id'), :maximo)"),
        {"maximo": len(filas)},
    )
    db_session.commit()
    return filas


def _textos(db_session):
    db_session.expire_all()
    return [m.motivo for m in db_session.query(RecruitingMotivoBlacklist).order_by(RecruitingMotivoBlacklist.id)]


# --- Permisos -------------------------------------------------------------------------------------------------------


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={"motivo": "Nuevo"}).status_code == 401


def test_sin_el_item_parametros_responde_403_en_todas_las_operaciones(client, usuario_con_grupo, empresa, motivos):
    cabeceras = auth_headers(usuario_con_grupo(permisos=["recruiting", "recruiting.candidatos"]), empresa)

    assert client.get(URL, headers=cabeceras).status_code == 403
    assert client.post(URL, json={"motivo": "Nuevo"}, headers=cabeceras).status_code == 403
    assert client.put(f"{URL}/1", json={"motivo": "Nuevo"}, headers=cabeceras).status_code == 403
    assert client.delete(f"{URL}/1", headers=cabeceras).status_code == 403


def test_el_grupo_externos_no_entra_aunque_tenga_el_item(client, usuario_con_grupo, empresa):
    externo = usuario_con_grupo(nombre_grupo="EXTERNOS")
    respuesta = client.get(URL, headers=auth_headers(externo, empresa))

    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés acceso a Parámetros de Recruiting"


# --- Listado --------------------------------------------------------------------------------------------------------


def test_lista_los_motivos_por_id(client, cabeceras, motivos):
    respuesta = client.get(URL, headers=cabeceras)

    assert respuesta.status_code == 200
    assert respuesta.json() == [{"id": n, "motivo": m} for n, m in enumerate(MOTIVOS, start=1)]


def test_la_lista_vacia_es_una_lista(client, cabeceras):
    assert client.get(URL, headers=cabeceras).json() == []


# --- Alta -----------------------------------------------------------------------------------------------------------


def test_alta_guarda_el_motivo_sin_tildes_y_con_los_espacios_colapsados(client, cabeceras, db_session, motivos):
    respuesta = client.post(URL, json={"motivo": "  Falta   de   ética  "}, headers=cabeceras)

    assert respuesta.status_code == 201
    assert respuesta.json()["motivo"] == "Falta de etica"
    assert _textos(db_session)[-1] == "Falta de etica"


def test_alta_conserva_la_enie(client, cabeceras):
    assert client.post(URL, json={"motivo": "Daño a la imagen"}, headers=cabeceras).json()["motivo"] == "Daño a la imagen"


@pytest.mark.parametrize("repetido", ["Otro motivo", "OTRO MOTIVO", "otro  motivo", "Ótro motivo"])
def test_alta_de_un_motivo_equivalente_a_uno_existente_responde_409(client, cabeceras, db_session, motivos, repetido):
    respuesta = client.post(URL, json={"motivo": repetido}, headers=cabeceras)

    assert respuesta.status_code == 409
    assert "Otro motivo" in respuesta.json()["detail"]
    assert _textos(db_session) == MOTIVOS


@pytest.mark.parametrize("cuerpo", [{}, {"motivo": ""}, {"motivo": "   "}, {"motivo": "x" * 151}])
def test_alta_invalida_no_guarda_nada(client, cabeceras, db_session, motivos, cuerpo):
    respuesta = client.post(URL, json=cuerpo, headers=cabeceras)

    assert respuesta.status_code in (400, 422)
    assert _textos(db_session) == MOTIVOS


# --- Edición --------------------------------------------------------------------------------------------------------


def test_edicion_cambia_el_texto_y_conserva_el_id(client, cabeceras, db_session, motivos):
    respuesta = client.put(f"{URL}/2", json={"motivo": "Datos falsos en la documentación"}, headers=cabeceras)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"id": 2, "motivo": "Datos falsos en la documentacion"}
    assert _textos(db_session) == [MOTIVOS[0], "Datos falsos en la documentacion", MOTIVOS[2]]


def test_edicion_con_el_mismo_texto_no_es_duplicado(client, cabeceras, motivos):
    assert client.put(f"{URL}/1", json={"motivo": "Conducta inapropiada"}, headers=cabeceras).status_code == 200


def test_edicion_a_un_texto_de_otro_motivo_responde_409(client, cabeceras, db_session, motivos):
    respuesta = client.put(f"{URL}/1", json={"motivo": "otro motivo"}, headers=cabeceras)

    assert respuesta.status_code == 409
    assert _textos(db_session) == MOTIVOS


def test_edicion_de_un_motivo_inexistente_responde_404(client, cabeceras, motivos):
    respuesta = client.put(f"{URL}/999", json={"motivo": "Nuevo"}, headers=cabeceras)

    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Motivo no encontrado."


def test_el_id_debe_ser_entero(client, cabeceras):
    assert client.put(f"{URL}/abc", json={"motivo": "Nuevo"}, headers=cabeceras).status_code == 422


# --- Baja -----------------------------------------------------------------------------------------------------------


def test_baja_elimina_el_motivo(client, cabeceras, db_session, motivos):
    respuesta = client.delete(f"{URL}/2", headers=cabeceras)

    assert respuesta.status_code == 200
    assert respuesta.json() == {"message": "Motivo eliminado correctamente."}
    assert _textos(db_session) == [MOTIVOS[0], MOTIVOS[2]]


def test_baja_de_un_motivo_inexistente_responde_404(client, cabeceras, db_session, motivos):
    assert client.delete(f"{URL}/999", headers=cabeceras).status_code == 404
    assert _textos(db_session) == MOTIVOS


def test_el_catalogo_para_el_combo_de_vue_refleja_el_abm(client, usuario_con_grupo, empresa, motivos):
    """El combo de Blacklist (item gestion_busquedas) lee la misma tabla que edita Parámetros."""
    abm = auth_headers(usuario_con_grupo(), empresa)
    combo = auth_headers(usuario_con_grupo(permisos=["recruiting", "recruiting.gestion_busquedas"]), empresa)

    client.post(URL, json={"motivo": "Suplantacion de identidad"}, headers=abm)
    client.delete(f"{URL}/3", headers=abm)

    motivos_combo = [m["motivo"] for m in client.get("/api/v1/recruiting/blacklist/motivos", headers=combo).json()]
    assert motivos_combo == ["Conducta inapropiada", "Datos falsos en el CV", "Suplantacion de identidad"]
