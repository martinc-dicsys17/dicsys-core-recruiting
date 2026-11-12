import pytest


@pytest.mark.frontend
@pytest.mark.smoke
def test_login_page_renders_without_a_live_backend(frontend_client):
    response = frontend_client.get("/login")

    assert response.status_code == 200


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_root_redirects_to_login_without_session(frontend_client):
    response = frontend_client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_successful_login_persists_session_from_fake_backend(
    frontend_client,
    fake_api,
):
    fake_api.respond(
        "POST",
        "/auth/login",
        {
            "access_token": "test-token",
            "user": {
                "id": "user-id",
                "email": "dev@example.com",
                "nombre": "Dev",
            },
            "empresas": [
                {
                    "id": "company-id",
                    "razon_social": "Company Test SA",
                    "nombre_fantasia": "Company Test",
                    "logo": None,
                }
            ],
            "requiere_seleccion_empresa": False,
        },
    )

    response = frontend_client.post(
        "/login",
        data={
            "email": "dev@example.com",
            "password": "secret",
        },
    )

    assert response.status_code == 302
    with frontend_client.session_transaction() as session:
        assert session["token"] == "test-token"
        assert session["user"]["email"] == "dev@example.com"
        assert session["empresa_id"] == "company-id"
