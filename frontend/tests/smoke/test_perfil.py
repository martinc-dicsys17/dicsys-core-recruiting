"""Perfil: muestra el email corporativo de la ficha y el secundario de la cuenta (F22)."""

import pytest

pytestmark = [pytest.mark.frontend]


def _sesion(client):
    with client.session_transaction() as sesion:
        sesion["token"] = "test-token"
        sesion["user"] = {"id": "u1", "email": "ana@dicsys.ai", "nombre": "Ana", "rol": "usuario", "dni": 30111222}


def test_el_perfil_muestra_el_email_corporativo_secundario(frontend_client, fake_api):
    _sesion(frontend_client)
    fake_api.respond("GET", "/menus", {"menus": []})
    fake_api.respond("GET", "/nomina/carreras/todos", [])
    fake_api.respond(
        "GET",
        "/auth/me/perfil",
        {
            "id": "u1",
            "email": "ana@dicsys.ai",
            "email_secundario": "ana@dicsys.com",
            "totp_enabled": False,
            "empleado": {"id": "e1", "apellido": "Pérez", "nombre": "Ana", "email_corporativo": "ana@dicsys.ai"},
        },
    )

    pagina = frontend_client.get("/perfil").get_data(as_text=True)

    assert "Email Corporativo Secundario" in pagina
    assert "ana@dicsys.com" in pagina and "ana@dicsys.ai" in pagina
