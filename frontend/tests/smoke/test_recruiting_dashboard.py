"""Recruiting → Dashboard: permisos de la ruta, render de lo que devuelve GET /recruiting/dashboard y el error sin
datos inventados."""

import pytest

pytestmark = [pytest.mark.frontend]

DASHBOARD = {
    "kpis": {
        "busquedas_activas": 4,
        "total_candidatos": 25,
        "postulaciones_en_proceso": 7,
        "skills_catalogo": 140,
        "habilidades_catalogo": 12,
    },
    "avisos": [
        {
            "id": "sin_cands_b-1",
            "tipo": "busqueda_sin_candidatos",
            "titulo": "Búsqueda sin postulantes: Backend Python",
            "descripcion": "La búsqueda para ACME no tiene candidatos asignados en el embudo.",
            "tiempo": "3 días abierta",
            "icono": "alert-triangle",
            "color": "amber",
            "enlace": "/recruiting/oportunidades/b-1",
            "created_at": "2026-11-10T12:00:00",
        },
        {
            "id": "t-1",
            "tipo": "transicion",
            "titulo": "Cambio de etapa: Ana Perez",
            "descripcion": "Pasó a 'Entrevista'",
            "tiempo": "09/11 12:05",
            "icono": "arrow-right-circle",
            "color": "primary",
            "enlace": "/recruiting/candidatos/c-1",
            "created_at": "2026-11-09T15:05:00",
        },
    ],
    "resumen_operativo": {"tasa_candidatos_proceso": 28.0, "busquedas_totales": 9},
}


def _sesion(client, fake_api, *permisos, rol="usuario"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def test_muestra_los_indicadores_el_resumen_y_los_avisos(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    fake_api.respond("GET", "/recruiting/dashboard", DASHBOARD)

    respuesta = frontend_client.get("/recruiting/dashboard")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    for clave, valor in DASHBOARD["kpis"].items():
        assert f'data-testid="kpi-{clave}-valor">{valor}<' in html
    assert 'data-testid="resumen-tasa">28.0%<' in html
    assert 'data-testid="resumen-busquedas-totales">9<' in html
    assert "2 alertas" in html
    assert "Búsqueda sin postulantes: Backend Python" in html and "3 días abierta" in html
    assert "Cambio de etapa: Ana Perez" in html and "09/11 12:05" in html
    assert "140 skills en BD" in html and "Dicsys.AI" in html
    assert {"method": "GET", "endpoint": "/recruiting/dashboard", "data": None, "token": "test-token"} in fake_api.calls


def test_la_raiz_del_modulo_es_el_dashboard(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    fake_api.respond("GET", "/recruiting/dashboard", DASHBOARD)

    assert frontend_client.get("/recruiting/").status_code == 200


def test_sin_avisos_muestra_el_estado_vacio(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    fake_api.respond("GET", "/recruiting/dashboard", {**DASHBOARD, "avisos": []})

    html = frontend_client.get("/recruiting/dashboard").get_data(as_text=True)

    assert 'data-testid="avisos-vacio"' in html and "0 alertas" in html


def test_sin_el_permiso_del_item_no_entra(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get("/recruiting/dashboard")

    assert respuesta.status_code == 403
    assert not any(c["endpoint"] == "/recruiting/dashboard" for c in fake_api.calls)


def test_si_la_api_falla_muestra_el_error_sin_ceros(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    fake_api.respond("GET", "/recruiting/dashboard", {"detail": "No tenés acceso a 'dashboard'"}, 403)

    html = frontend_client.get("/recruiting/dashboard").get_data(as_text=True)

    assert 'data-testid="dashboard-error"' in html and "No tenés acceso a &#39;dashboard&#39;" in html
    assert 'data-testid="kpi-' not in html


def test_sin_sesion_va_al_login(frontend_client):
    respuesta = frontend_client.get("/recruiting/dashboard")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
