import pytest


def _set_session(client, *, rol="usuario"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {
            "id": "user-id",
            "email": "user@example.com",
            "nombre": "Test",
            "rol": rol,
        }


def _menus_response(fake_api):
    fake_api.respond("GET", "/menus", {"menus": []})


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_notification_history_renders_personal_records(frontend_client, fake_api):
    _set_session(frontend_client)
    _menus_response(fake_api)
    fake_api.respond(
        "GET",
        "/notificaciones-internas/historial?pagina=1&por_pagina=20",
        {
            "items": [
                {
                    "id": "notification-id",
                    "tipo": "info",
                    "titulo": "Aviso personal",
                    "mensaje": "Mensaje recibido por el usuario.",
                    "origen": "tests.frontend",
                    "leida_at": None,
                    "deleted_at": None,
                    "created_at": "2026-07-14T12:00:00",
                }
            ],
            "total": 1,
            "pagina": 1,
            "por_pagina": 20,
            "total_paginas": 1,
        },
    )

    response = frontend_client.get("/notificaciones")

    assert response.status_code == 200
    assert b"Aviso personal" in response.data
    assert b"Auditoria" not in response.data


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_notification_delete_proxy_forwards_the_current_user_token(
    frontend_client,
    fake_api,
):
    _set_session(frontend_client)
    fake_api.respond("DELETE", "/notificaciones-internas/notification-id", {"ok": True})

    response = frontend_client.post("/notificaciones-internas/notification-id/eliminar")

    assert response.status_code == 200
    assert fake_api.calls[-1] == {
        "method": "DELETE",
        "endpoint": "/notificaciones-internas/notification-id",
        "data": None,
        "token": "test-token",
    }


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_notification_audit_page_is_hidden_from_non_administrators(
    frontend_client,
    fake_api,
):
    _set_session(frontend_client)

    response = frontend_client.get("/notificaciones/auditoria")

    assert response.status_code == 403
    assert fake_api.calls == []


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_notification_audit_page_renders_for_administrators(frontend_client, fake_api):
    _set_session(frontend_client, rol="admin")
    _menus_response(fake_api)
    fake_api.respond(
        "GET",
        "/notificaciones-internas/auditoria?pagina=1&por_pagina=20",
        {
            "items": [
                {
                    "id": "notification-id",
                    "tipo": "warning",
                    "titulo": "Registro de evidencia",
                    "mensaje": "Notificacion eliminada logicamente.",
                    "origen": "tests.frontend",
                    "leida_at": "2026-07-14T12:01:00",
                    "deleted_at": "2026-07-14T12:02:00",
                    "created_at": "2026-07-14T12:00:00",
                    "usuario_email": "recipient@example.com",
                    "usuario_nombre": "Recipient Test",
                }
            ],
            "total": 1,
            "pagina": 1,
            "por_pagina": 20,
            "total_paginas": 1,
        },
    )

    response = frontend_client.get("/notificaciones/auditoria")

    assert response.status_code == 200
    assert b"recipient@example.com" in response.data
    assert b"Eliminada" in response.data
