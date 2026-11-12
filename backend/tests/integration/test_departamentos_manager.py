"""Manager de un departamento (PG-19): tiene que ser un empleado de la empresa activa.

Antes, un manager_id que no era empleado llegaba a la FK: 409 «Ya existe un departamento con ese nombre» en el alta y
500 en la edición. Ahora el servicio lo valida y responde 422 sin guardar nada.
"""

import uuid

import pytest

from backend.modules.nomina.models import Departamento
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

URL = "/api/v1/nomina/departamentos"


@pytest.fixture
def entorno(data_factory):
    empresa = data_factory.empresa()
    admin = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(admin, empresa)
    return {
        "headers": auth_headers(admin, empresa),
        "empresa": empresa,
        "empleado": data_factory.empleado(empresa),
        "ajeno": data_factory.empleado(data_factory.empresa()),
    }


def _departamentos(db_session, empresa, nombre):
    return db_session.query(Departamento).filter_by(empresa_id=empresa.id, nombre=nombre).count()


@pytest.mark.parametrize("manager", ["inexistente", "ajeno", "no-es-uuid"])
def test_alta_con_un_manager_que_no_es_empleado_de_la_empresa_da_422(client, db_session, entorno, manager):
    manager_id = {"inexistente": str(uuid.uuid4()), "ajeno": str(entorno["ajeno"].id), "no-es-uuid": "abc"}[manager]

    respuesta = client.post(URL, headers=entorno["headers"], json={"nombre": "Ventas", "manager_id": manager_id})

    assert respuesta.status_code == 422, respuesta.text
    assert "manager" in respuesta.json()["detail"]
    assert _departamentos(db_session, entorno["empresa"], "Ventas") == 0


def test_alta_con_manager_de_la_empresa_o_sin_manager(client, entorno):
    con = client.post(
        URL, headers=entorno["headers"], json={"nombre": "Ventas", "manager_id": str(entorno["empleado"].id)}
    )
    sin = client.post(URL, headers=entorno["headers"], json={"nombre": "Compras", "manager_id": ""})

    assert con.status_code == 201, con.text
    assert con.json()["manager_id"] == str(entorno["empleado"].id)
    assert sin.status_code == 201, sin.text
    assert sin.json()["manager_id"] is None


def test_edicion_con_un_manager_inexistente_da_422_y_no_cambia_nada(client, entorno):
    alta = client.post(
        URL, headers=entorno["headers"], json={"nombre": "Ventas", "manager_id": str(entorno["empleado"].id)}
    )
    departamento = alta.json()["id"]

    for manager_id in (str(uuid.uuid4()), str(entorno["ajeno"].id)):
        respuesta = client.put(
            f"{URL}/{departamento}", headers=entorno["headers"], json={"nombre": "Ventas B", "manager_id": manager_id}
        )
        assert respuesta.status_code == 422, respuesta.text

    actual = client.get(f"{URL}/{departamento}", headers=entorno["headers"]).json()
    assert (actual["nombre"], actual["manager_id"]) == ("Ventas", str(entorno["empleado"].id))


def test_edicion_cambia_o_quita_el_manager(client, data_factory, entorno):
    alta = client.post(URL, headers=entorno["headers"], json={"nombre": "Ventas"})
    departamento = alta.json()["id"]
    otro = data_factory.empleado(entorno["empresa"])

    cambiado = client.put(f"{URL}/{departamento}", headers=entorno["headers"], json={"manager_id": str(otro.id)})
    quitado = client.put(f"{URL}/{departamento}", headers=entorno["headers"], json={"manager_id": None})

    assert cambiado.status_code == 200 and cambiado.json()["manager_id"] == str(otro.id)
    assert quitado.status_code == 200 and quitado.json()["manager_id"] is None
