"""El catalogo de herramientas es lo que evita los duplicados por tipeo."""

import pytest

from backend.tests.helpers.auth import auth_headers

HERRAMIENTAS = "/api/v1/innovacion/herramientas"
PROVEEDORES = "/api/v1/innovacion/proveedores"


@pytest.fixture
def acceso(data_factory):
    """Usuario con el modulo y el submodulo de licencias otorgados."""
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    return auth_headers(usuario, empresa)


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_crea_herramienta_con_proveedor_y_costo(client, acceso):
    response = client.post(
        HERRAMIENTAS,
        headers=acceso,
        json={
            "nombre": "ChatGPT Pro",
            "proveedor_nombre": "OpenAI",
            "costo_referencia": 100,
            "moneda": "USD",
        },
    )

    assert response.status_code == 201
    cuerpo = response.json()
    assert cuerpo["nombre"] == "ChatGPT Pro"
    assert cuerpo["proveedor"] == "OpenAI"
    assert cuerpo["costo_referencia"] == 100.0
    assert cuerpo["activo"] is True


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize(
    "duplicado",
    [
        "ChatGPT Pro",  # identico
        "chatgpt pro",  # distinta capitalizacion
        "  CHATGPT   PRO ",  # espacios de mas
    ],
)
def test_rechaza_duplicados_por_nombre_plegado(client, acceso, duplicado):
    """Lo que hoy produce 'ChatGPT Pro' y 'Chatgpt pro' como herramientas distintas."""
    primera = client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "ChatGPT Pro"})
    assert primera.status_code == 201

    segunda = client.post(HERRAMIENTAS, headers=acceso, json={"nombre": duplicado})

    assert segunda.status_code == 409
    assert "ya existe" in segunda.json()["detail"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_rechaza_duplicado_con_acentos(client, acceso):
    assert client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Atlassián"}).status_code == 201

    response = client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Atlassian"})

    assert response.status_code == 409


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_catalogo_solo_devuelve_la_empresa_activa(client, acceso, data_factory):
    """Cada empresa ve su propio catalogo."""
    client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Jira", "proveedor_nombre": "Atlassian"})

    otro_usuario = data_factory.usuario()
    otra_empresa = data_factory.empresa()
    otro_grupo = data_factory.grupo()
    data_factory.asignar_empresa(otro_usuario, otra_empresa)
    data_factory.asignar_grupo(otro_usuario, otro_grupo, otra_empresa)
    data_factory.permisos(otro_grupo, ["innovacion", "innovacion.licencias"])

    propio = client.get(HERRAMIENTAS, headers=acceso).json()
    ajeno = client.get(HERRAMIENTAS, headers=auth_headers(otro_usuario, otra_empresa)).json()

    assert [h["nombre"] for h in propio] == ["Jira"]
    assert ajeno == []


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_proveedor_repetido_no_se_duplica(client, acceso):
    client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Jira", "proveedor_nombre": "Atlassian"})
    client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Confluence", "proveedor_nombre": "Atlassian"})
    client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Claude Code", "proveedor_nombre": "Anthropic"})
    client.post(HERRAMIENTAS, headers=acceso, json={"nombre": "Sin proveedor"})

    response = client.get(PROVEEDORES, headers=acceso)

    assert response.status_code == 200
    # Un proveedor por nombre plegado: Atlassian no se duplica entre las dos
    # herramientas, y la que no declara proveedor no agrega ninguno.
    assert [p["nombre"] for p in response.json()] == ["Anthropic", "Atlassian"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_catalogo_exige_el_permiso_del_submodulo(client, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.resumen"])

    response = client.get(HERRAMIENTAS, headers=auth_headers(usuario, empresa))

    assert response.status_code == 403
