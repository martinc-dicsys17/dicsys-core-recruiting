"""El puente Flask conserva los campos y errores del ABM de catalogo."""

import pytest


@pytest.fixture(autouse=True)
def sesion_catalogo(frontend_client):
    with frontend_client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "nombre": "Test", "email": "test@example.com", "rol": "admin"}


@pytest.mark.parametrize("status", [200, 404, 409, 422])
def test_editar_proveedor_conserva_respuesta_backend(frontend_client, fake_api, status):
    respuesta = {"id": "p-id", "nombre": "OpenAI"} if status == 200 else {"detail": "Nombre ocupado"}
    fake_api.respond("PUT", "/innovacion/proveedores/p-id", respuesta, status=status)

    response = frontend_client.put("/innovacion/proveedores/p-id", json={"nombre": " OpenAI "})

    assert response.status_code == status
    assert response.json == respuesta
    assert fake_api.calls[-1]["data"] == {"nombre": "OpenAI"}
    assert fake_api.calls[-1]["token"] == "test-token"


def test_editar_herramienta_envia_nombre_proveedor_costo_y_moneda(frontend_client, fake_api):
    fake_api.respond("PUT", "/innovacion/herramientas/h-id", {"id": "h-id"})

    response = frontend_client.put(
        "/innovacion/herramientas/h-id",
        json={
            "nombre": " ChatGPT ",
            "proveedor_nombre": " OpenAI ",
            "costo_referencia": "20,50",
            "moneda": "USD",
        },
    )

    assert response.status_code == 200
    assert fake_api.calls[-1]["data"] == {
        "nombre": "ChatGPT",
        "proveedor_nombre": "OpenAI",
        "costo_referencia": "20.50",
        "moneda": "USD",
    }


def test_editar_herramienta_permite_quitar_proveedor_y_costo(frontend_client, fake_api):
    fake_api.respond("PUT", "/innovacion/herramientas/h-id", {"id": "h-id"})
    response = frontend_client.put(
        "/innovacion/herramientas/h-id",
        json={
            "proveedor_id": "",
            "costo_referencia": "",
        },
    )
    assert response.status_code == 200
    assert fake_api.calls[-1]["data"] == {"proveedor_id": None, "costo_referencia": None}


def test_costo_invalido_de_herramienta_no_se_borra_silenciosamente(frontend_client, fake_api):
    fake_api.respond("POST", "/innovacion/herramientas", {"detail": "Costo invalido"}, status=422)
    response = frontend_client.post(
        "/innovacion/herramientas",
        json={
            "nombre": "ChatGPT",
            "costo_referencia": "abc",
        },
    )
    assert response.status_code == 422
    assert fake_api.calls[-1]["data"]["costo_referencia"] == "abc"
