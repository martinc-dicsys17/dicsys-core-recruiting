"""Gestion de Licencias vive bajo innovacion, con permiso propio de submodulo."""

import pytest

from backend.tests.helpers.auth import auth_headers

LICENCIAS_ENDPOINT = "/api/v1/innovacion/licencias/por-empleado"
ENDPOINT_VIEJO = "/api/v1/administracion/licencias"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_licencias_ya_no_responde_bajo_administracion(client):
    response = client.get(ENDPOINT_VIEJO)

    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_licencias_rechaza_permiso_viejo_de_admin_contable(client, data_factory):
    """El permiso migro de clave: la vieja no debe seguir abriendo la puerta."""
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.licencias"])

    response = client.get(
        LICENCIAS_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_licencias_rechaza_modulo_innovacion_sin_el_submodulo(client, data_factory):
    """Acceder a Innovacion no alcanza: el submodulo se otorga aparte."""
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.resumen"])

    response = client.get(
        LICENCIAS_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_licencias_permite_grupo_con_modulo_y_submodulo(client, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])

    response = client.get(
        LICENCIAS_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
