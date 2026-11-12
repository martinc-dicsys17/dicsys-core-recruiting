"""Edicion del catalogo conserva referencias y la unicidad por empresa."""

import uuid

import pytest

from backend.modules.innovacion.licencias_models import Proveedor
from backend.tests.helpers.auth import auth_headers

PROVEEDORES = "/api/v1/innovacion/proveedores"
HERRAMIENTAS = "/api/v1/innovacion/herramientas"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def acceso_catalogo(data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    return auth_headers(usuario, empresa), empresa.id


def test_editar_proveedor_actualiza_nombre_sin_perder_herramientas(client, acceso_catalogo):
    headers, _ = acceso_catalogo
    herramienta = client.post(
        HERRAMIENTAS,
        headers=headers,
        json={
            "nombre": "Sora",
            "proveedor_nombre": "OenAI",
        },
    ).json()

    response = client.put(f"{PROVEEDORES}/{herramienta['proveedor_id']}", headers=headers, json={"nombre": " OpenAI "})

    assert response.status_code == 200
    assert response.json() == {"id": herramienta["proveedor_id"], "nombre": "OpenAI"}
    actualizada = client.get(HERRAMIENTAS, headers=headers).json()[0]
    assert actualizada["id"] == herramienta["id"]
    assert actualizada["proveedor_id"] == herramienta["proveedor_id"]
    assert actualizada["proveedor"] == "OpenAI"
    assert client.delete(f"{PROVEEDORES}/{herramienta['proveedor_id']}", headers=headers).status_code == 204
    assert client.get(HERRAMIENTAS, headers=headers).json() == []


def test_editar_proveedor_rechaza_nombre_vigente_y_permite_nombre_dado_de_baja(client, db_session, acceso_catalogo):
    headers, _ = acceso_catalogo
    bueno = client.post(PROVEEDORES, headers=headers, json={"nombre": "OpenAI"}).json()
    otro = client.post(PROVEEDORES, headers=headers, json={"nombre": "OenAI"}).json()
    ruta = f"{PROVEEDORES}/{otro['id']}"

    response = client.put(ruta, headers=headers, json={"nombre": "  OPENAI  "})
    assert response.status_code == 409
    assert db_session.get(Proveedor, uuid.UUID(otro["id"])).nombre == "OenAI"
    assert client.delete(f"{PROVEEDORES}/{bueno['id']}", headers=headers).status_code == 204
    response = client.put(ruta, headers=headers, json={"nombre": "OpenAI"})
    assert response.status_code == 200
    assert response.json()["id"] == otro["id"]
    # La busqueda posterior debe elegir el vigente, sin revivir el tombstone.
    existente = client.post(PROVEEDORES, headers=headers, json={"nombre": "OPENAI"}).json()
    assert existente["id"] == otro["id"]
    assert db_session.get(Proveedor, uuid.UUID(bueno["id"])).deleted_at is not None


def test_editar_proveedor_no_admite_ajenos_borrados_o_ids_invalidos(client, db_session, acceso_catalogo, data_factory):
    headers, _ = acceso_catalogo
    ajena = data_factory.empresa()
    ajeno = Proveedor(empresa_id=ajena.id, nombre="Ajeno", nombre_normalizado="ajeno")
    db_session.add(ajeno)
    db_session.flush()
    propio = client.post(PROVEEDORES, headers=headers, json={"nombre": "Propio"}).json()
    assert client.delete(f"{PROVEEDORES}/{propio['id']}", headers=headers).status_code == 204
    for id in (str(ajeno.id), propio["id"], "invalido"):
        assert client.put(f"{PROVEEDORES}/{id}", headers=headers, json={"nombre": "Robado"}).status_code == 404


def test_editar_herramienta_modifica_todos_los_campos_del_catalogo(client, acceso_catalogo):
    headers, _ = acceso_catalogo
    herramienta = client.post(HERRAMIENTAS, headers=headers, json={"nombre": "ChatGTP"}).json()
    response = client.put(
        f"{HERRAMIENTAS}/{herramienta['id']}",
        headers=headers,
        json={
            "nombre": "ChatGPT",
            "proveedor_nombre": "OpenAI",
            "costo_referencia": "20.50",
            "moneda": "USD",
        },
    )
    assert response.status_code == 200
    assert response.json()["id"] == herramienta["id"]
    assert response.json()["nombre"] == "ChatGPT"
    assert response.json()["proveedor"] == "OpenAI"
    assert response.json()["costo_referencia"] == 20.5
    assert response.json()["moneda"] == "USD"
