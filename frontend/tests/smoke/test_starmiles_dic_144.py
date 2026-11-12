import pytest


def _set_admin_session(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {
            "id": "admin-id",
            "email": "admin@example.com",
            "nombre": "Admin",
            "rol": "admin",
        }


def _set_user_session(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {
            "id": "user-id",
            "email": "user@example.com",
            "nombre": "User",
            "rol": "usuario",
        }


ACCIONES_CON_MOTIVO = (
    (
        "/starmiles/aprobador/inscripciones/inscripcion-id/cancelar",
        "/starmiles/inscripciones/inscripcion-id/cancelar",
        {"comentario_aprobador": "El desafio se cancela por duplicado"},
    ),
    (
        "/starmiles/aprobador/inscripciones/inscripcion-id/revocar",
        "/starmiles/inscripciones/inscripcion-id/revocar",
        {"comentario_aprobador": "La aprobacion se revoca por duplicado"},
    ),
    (
        "/starmiles/aprobador/canjes/canje-id/rechazar-y-reintegrar",
        "/starmiles/canjes/canje-id/rechazar-y-reintegrar",
        {"comentario": "Se reintegran millas antes de revocar"},
    ),
)


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("ruta, endpoint, payload", ACCIONES_CON_MOTIVO)
def test_dic_144_actions_require_a_reason(frontend_client, fake_api, ruta, endpoint, payload):
    _set_admin_session(frontend_client)

    response = frontend_client.post(ruta, data={"comentario": "  "})

    assert response.status_code == 400
    assert fake_api.calls == []


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("ruta, endpoint, payload", ACCIONES_CON_MOTIVO)
def test_dic_144_actions_forward_reason_and_token(
    frontend_client,
    fake_api,
    ruta,
    endpoint,
    payload,
):
    _set_admin_session(frontend_client)
    fake_api.respond("PUT", endpoint, {"id": "updated-id"})

    response = frontend_client.post(ruta, data={"comentario": next(iter(payload.values()))})

    assert response.status_code == 200
    assert fake_api.calls[-1] == {
        "method": "PUT",
        "endpoint": endpoint,
        "data": payload,
        "token": "test-token",
    }


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_dic_144_action_rejects_submodule_permission_without_starmiles_module(
    frontend_client,
    fake_api,
):
    _set_user_session(frontend_client)
    fake_api.respond(
        "GET",
        "/permisos/mis-permisos",
        {"permisos": {"starmiles.aprobar_inscripciones": True}},
    )
    fake_api.respond("GET", "/menus", {"menus": []})

    response = frontend_client.post(
        "/starmiles/aprobador/inscripciones/inscripcion-id/cancelar",
        data={"comentario": "Cancelar por duplicado"},
    )

    assert response.status_code == 403
    assert fake_api.calls[0] == {
        "method": "GET",
        "endpoint": "/permisos/mis-permisos",
        "data": None,
        "token": "test-token",
    }
    assert not any(call["method"] == "PUT" for call in fake_api.calls)
