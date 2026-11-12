import pytest

from backend.tests.helpers.auth import auth_headers

PROTECTED_ENDPOINT = "/api/v1/nomina/departamentos/todos"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_protected_endpoint_rejects_requests_without_token(client):
    response = client.get(PROTECTED_ENDPOINT)

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_protected_endpoint_rejects_user_without_permission(
    client,
    data_factory,
):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_protected_endpoint_rejects_user_with_submodule_but_without_module(
    client,
    data_factory,
):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["nomina.departamentos"])

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_protected_endpoint_allows_user_with_module_permissions(
    client,
    data_factory,
):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(
        grupo,
        [
            "nomina",
            "nomina.departamentos",
        ],
    )

    response = client.get(
        PROTECTED_ENDPOINT,
        headers=auth_headers(usuario, empresa),
    )

    assert response.status_code == 200
    assert response.json() == []
