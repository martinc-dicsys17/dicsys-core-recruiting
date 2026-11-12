"""Recruiting → Manager Dashboard: el administrador ve este dashboard en lugar del convencional, el resto no entra, y la
pantalla pide sus datos al backend (que valida el acceso)."""

import pytest

pytestmark = [pytest.mark.frontend]

MANAGER = "/recruiting/dashboard/manager"
DATOS = "/recruiting/dashboard/manager/datos"
PERMISOS = ("recruiting", "recruiting.dashboard")


def _sesion(client, fake_api, *permisos, rol="usuario", email="user@example.com"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": email, "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def test_el_admin_que_entra_por_el_dashboard_va_al_manager_dashboard(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, rol="admin", email="admin@admin.com")

    for ruta in ("/recruiting/dashboard", "/recruiting/"):
        respuesta = frontend_client.get(ruta)
        assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith(MANAGER)
    assert not any(c["endpoint"] == "/recruiting/dashboard" for c in fake_api.calls)  # no pide el dashboard común


def test_el_admin_ve_la_pantalla_del_manager_dashboard(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, rol="admin", email="admin@admin.com")

    respuesta = frontend_client.get(MANAGER)
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert 'data-testid="recruiting-manager-dashboard"' in html and "Manager Dashboard" in html
    assert 'x-data="managerDashboard()"' in html and DATOS in html
    for seccion in (
        "Alertas de gestión",
        "Embudo del proceso",
        "Calidad por usuario externo",
        "Tiempos y demoras",
        "Comparativa de usuarios externos",
        "Umbrales de alertas",
    ):
        assert seccion in html


def test_el_recruiter_sigue_viendo_el_dashboard_convencional(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, *PERMISOS)
    fake_api.respond(
        "GET",
        "/recruiting/dashboard",
        {
            "kpis": {
                "busquedas_activas": 1,
                "total_candidatos": 2,
                "postulaciones_en_proceso": 3,
                "skills_catalogo": 4,
                "habilidades_catalogo": 5,
            },
            "avisos": [],
            "resumen_operativo": {"tasa_candidatos_proceso": 0, "busquedas_totales": 1},
        },
    )

    respuesta = frontend_client.get("/recruiting/dashboard")

    assert respuesta.status_code == 200 and 'data-testid="recruiting-dashboard"' in respuesta.get_data(as_text=True)


def test_el_recruiter_no_entra_al_manager_dashboard_por_su_url(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, *PERMISOS)

    respuesta = frontend_client.get(MANAGER)

    assert respuesta.status_code == 403
    assert "managerDashboard" not in respuesta.get_data(as_text=True)


def test_el_email_admin_no_alcanza_sin_el_rol(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, *PERMISOS, email="admin@admin.com")

    assert frontend_client.get(MANAGER).status_code == 403


def test_el_proxy_devuelve_lo_que_responde_el_backend_con_los_filtros(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, rol="admin")
    fake_api.respond("GET", "/recruiting/manager-dashboard?dias_estancado=9", {"resumen": {"postulaciones": 2}})

    respuesta = frontend_client.get(DATOS + "?dias_estancado=9")

    assert respuesta.status_code == 200 and respuesta.get_json() == {"resumen": {"postulaciones": 2}}
    assert {
        "method": "GET",
        "endpoint": "/recruiting/manager-dashboard?dias_estancado=9",
        "data": None,
        "token": "test-token",
    } in fake_api.calls


def test_el_proxy_traslada_el_403_del_backend_a_quien_no_es_admin(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, *PERMISOS)
    fake_api.respond("GET", "/recruiting/manager-dashboard", {"detail": "Acceso denegado - se requiere rol admin"}, 403)

    respuesta = frontend_client.get(DATOS)

    assert respuesta.status_code == 403
    assert respuesta.get_json() == {"error": "Acceso denegado - se requiere rol admin"}


def test_el_proxy_sin_permiso_del_item_ni_llama_al_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    assert frontend_client.get(DATOS).status_code == 403
    assert not any(c["endpoint"].startswith("/recruiting/manager-dashboard") for c in fake_api.calls)


def test_sin_sesion_va_al_login(frontend_client):
    for ruta in (MANAGER, DATOS):
        respuesta = frontend_client.get(ruta)
        assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/login")
