"""Configuración → Tareas programadas: pantalla, permiso y relay a la API (F19)."""

import pytest

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


def _sesion(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": "usuario"}


def _permisos(fake_api, *claves):
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {c: True for c in claves}})
    fake_api.respond("GET", "/menus", {"items": []})


def test_la_pantalla_exige_su_permiso_y_abre_en_la_pestana_pedida(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "configuracion", "configuracion.parametros")
    assert frontend_client.get("/tareas-programadas").status_code == 403

    _permisos(fake_api, "configuracion", "configuracion.tareas_programadas")
    html = frontend_client.get("/tareas-programadas?tab=historial").get_data(as_text=True)
    assert "Tareas programadas" in html and "tab: 'historial'" in html
    assert 'href="/parametros?categoria=Tareas+programadas"' in html  # el horario se edita en Parámetros
    assert "tab: 'tareas'" in frontend_client.get("/tareas-programadas?tab=otra").get_data(as_text=True)


def test_el_relay_solo_deja_pasar_las_rutas_de_la_pantalla(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "configuracion", "configuracion.tareas_programadas")
    fake_api.respond("GET", "/tareas", {"tareas": [], "alertas_configuradas": False, "parametro_alertas": "x"})
    fake_api.respond("GET", "/tareas/corridas?tarea=cumpleanos", [])
    fake_api.respond("POST", "/tareas/cumpleanos/ejecutar", {"id": "c-1", "estado": "pendiente"}, status=201)
    fake_api.respond("POST", "/tareas/envios/e-1/reintentar", {"id": "e-1", "estado": "pendiente"})

    assert frontend_client.get("/tareas-programadas/api").json["alertas_configuradas"] is False
    assert frontend_client.get("/tareas-programadas/api/corridas?tarea=cumpleanos").json == []
    assert frontend_client.post("/tareas-programadas/api/cumpleanos/ejecutar").status_code == 201
    assert frontend_client.post("/tareas-programadas/api/envios/e-1/reintentar").status_code == 200
    assert frontend_client.get("/tareas-programadas/api/otra-cosa").status_code == 404
    assert frontend_client.post("/tareas-programadas/api/corridas").status_code == 404
