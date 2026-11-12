import pytest

from backend.tests.helpers.auth import auth_headers


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_invalid_login_returns_unauthorized(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "missing@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_login_with_one_company_returns_a_final_access_token(client, data_factory):
    password = "correct-horse-battery-staple"
    usuario = data_factory.usuario(password=password)
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": usuario.email,
            "password": password,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requiere_seleccion_empresa"] is False
    assert payload["empresas"][0]["id"] == str(empresa.id)
    assert payload["access_token"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_user_cannot_select_an_unassigned_company(client, data_factory):
    usuario = data_factory.usuario()
    assigned_company = data_factory.empresa()
    unassigned_company = data_factory.empresa()
    data_factory.asignar_empresa(usuario, assigned_company)

    response = client.post(
        "/api/v1/auth/seleccionar-empresa",
        headers=auth_headers(usuario),
        json={"empresa_id": str(unassigned_company.id)},
    )

    assert response.status_code == 403
