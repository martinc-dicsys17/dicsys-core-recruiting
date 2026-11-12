"""Flujos de licencias que deben conservar respuesta, formulario y validación."""

import pytest

from tests.smoke.test_licencias_innovacion import _catalogos, _licencia, _set_session

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


@pytest.fixture(autouse=True)
def sesion_licencias(frontend_client):
    _set_session(frontend_client)


@pytest.mark.parametrize("status", [200, 201, 409])
def test_alta_proveedor_normaliza_nombre_y_conserva_error(frontend_client, fake_api, status):
    resultado = {"id": "p-id", "nombre": "OpenAI"} if status < 400 else {"detail": "Proveedor duplicado"}
    fake_api.respond("POST", "/innovacion/proveedores", resultado, status=status)

    response = frontend_client.post("/innovacion/proveedores", json={"nombre": " OpenAI "})

    assert response.status_code == (201 if status < 400 else status)
    assert response.json == resultado
    assert fake_api.calls[-1]["data"] == {"nombre": "OpenAI"}
    assert fake_api.calls[-1]["token"] == "test-token"


@pytest.mark.parametrize("costo", [None, 0, 12.5])
def test_alta_herramienta_preserva_costo_numerico_y_defaults(frontend_client, fake_api, costo):
    fake_api.respond("POST", "/innovacion/herramientas", {"id": "h-id"}, status=201)

    response = frontend_client.post(
        "/innovacion/herramientas",
        json={
            "nombre": " Editor ",
            "costo_referencia": costo,
        },
    )

    assert response.status_code == 201
    assert response.json == {"id": "h-id"}
    assert fake_api.calls[-1]["data"] == {
        "nombre": "Editor",
        "proveedor_id": None,
        "proveedor_nombre": None,
        "costo_referencia": costo,
        "moneda": "ARS",
    }


def test_editar_herramienta_conserva_rechazo_del_proveedor(frontend_client, fake_api):
    fake_api.respond("PUT", "/innovacion/herramientas/h-id", {"detail": "Proveedor inexistente"}, status=404)

    response = frontend_client.put("/innovacion/herramientas/h-id", json={"proveedor_id": "p-id"})

    assert response.status_code == 404
    assert response.json == {"detail": "Proveedor inexistente"}
    assert fake_api.calls[-1]["data"] == {"proveedor_id": "p-id"}


def test_alta_individual_anterior_no_esta_expuesta(frontend_client, fake_api):
    response = frontend_client.post("/innovacion/licencias/nuevo", data={"herramienta_id": "h-id"})

    # La ruta DELETE /licencias/<id> coincide, pero no admite POST.
    assert response.status_code == 405
    assert not fake_api.calls


@pytest.mark.parametrize("cuerpo", ["null", "[]", "false", "JSON inválido"])
def test_lote_requiere_objeto_json_antes_de_llamar_backend(frontend_client, fake_api, cuerpo):
    response = frontend_client.post("/innovacion/licencias/lote", data=cuerpo, content_type="application/json")

    assert response.status_code == 400
    assert response.json == {"detail": "Se requiere un objeto JSON con las licencias a asignar"}
    assert not fake_api.calls


def _responder_formulario(fake_api):
    _catalogos(fake_api)
    fake_api.respond("GET", "/innovacion/licencias/licencia-id", _licencia())
    fake_api.respond(
        "GET",
        "/nomina/empleados/buscar-select",
        [
            {"id": "empleado-id", "nombre": "Lescano, Tomas"},
        ],
    )


def test_editar_carga_licencia_y_catalogos(frontend_client, fake_api):
    _responder_formulario(fake_api)

    response = frontend_client.get("/innovacion/licencias/licencia-id/editar")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Claude Code" in html
    assert "Lescano, Tomas" in html
    assert "OC-2026-042" in html
    assert 'hx-post="/innovacion/licencias/licencia-id/editar"' in html
    assert {call["endpoint"] for call in fake_api.calls} == {
        "/innovacion/licencias/licencia-id",
        "/nomina/empleados/buscar-select",
        "/innovacion/herramientas",
        "/menus",
    }
    assert all(call["token"] == "test-token" for call in fake_api.calls)


@pytest.mark.parametrize("htmx", [True, False])
def test_editar_guarda_y_vuelve_al_listado(frontend_client, fake_api, htmx):
    fake_api.respond("PUT", "/innovacion/licencias/licencia-id", _licencia())

    response = frontend_client.post(
        "/innovacion/licencias/licencia-id/editar",
        data={"costo_mensual": "30,25"},
        headers={"HX-Request": "true"} if htmx else {},
    )

    assert response.status_code == (200 if htmx else 302)
    assert response.headers["HX-Redirect" if htmx else "Location"] == "/innovacion/licencias"
    assert fake_api.calls[-1]["data"]["costo_mensual"] == 30.25
    with frontend_client.session_transaction() as session:
        assert ("success", "Licencia actualizada exitosamente") in session["_flashes"]


def test_editar_rechazada_representa_formulario_y_error(frontend_client, fake_api):
    _responder_formulario(fake_api)
    fake_api.respond("PUT", "/innovacion/licencias/licencia-id", {"detail": "Fecha incompatible"}, status=422)

    response = frontend_client.post("/innovacion/licencias/licencia-id/editar", data={"fecha_fin": "2020-01-01"})

    assert response.status_code == 200
    assert "Fecha incompatible" in response.get_data(as_text=True)
    assert "OC-2026-042" in response.get_data(as_text=True)


@pytest.mark.parametrize("activa,status", [("true", 200), ("false", 200), ("false", 404)])
def test_toggle_refresca_solo_despues_de_guardar(frontend_client, fake_api, activa, status):
    ruta = f"/innovacion/licencias/licencia-id/activa/{activa}"
    fake_api.respond("PUT", ruta, {"detail": "Licencia no encontrada"}, status=status)

    response = frontend_client.put(ruta)

    assert fake_api.calls[-1]["endpoint"] == ruta
    if status == 200:
        assert response.status_code == 200
        assert response.data == b""
        assert response.headers["HX-Trigger"] == "licenciaEstadoCambiado"
    else:
        assert response.status_code == 400
        assert "Licencia no encontrada" in response.get_data(as_text=True)
        assert "HX-Trigger" not in response.headers


def test_lote_fecha_de_tipo_invalido_conserva_validacion_backend(frontend_client, fake_api):
    fake_api.respond("POST", "/innovacion/licencias/lote", {"detail": "Ingresá una fecha válida"}, status=422)

    response = frontend_client.post(
        "/innovacion/licencias/lote",
        json={
            "fecha_inicio": 20260906,
            "empleado_ids": ["empleado-id"],
        },
    )

    assert response.status_code == 422
    assert response.json == {"detail": "Ingresá una fecha válida"}
    assert fake_api.calls[-1]["data"]["fecha_inicio"] == 20260906


@pytest.mark.parametrize("status", [404, 500])
def test_editar_licencia_no_disponible_vuelve_al_listado(frontend_client, fake_api, status):
    fake_api.respond("GET", "/innovacion/licencias/licencia-id", {"detail": "No disponible"}, status=status)

    response = frontend_client.get("/innovacion/licencias/licencia-id/editar")

    assert response.status_code == 302
    assert response.headers["Location"] == "/innovacion/licencias"
    assert len(fake_api.calls) == 1
    with frontend_client.session_transaction() as session:
        assert ("error", "Licencia no encontrada") in session["_flashes"]
