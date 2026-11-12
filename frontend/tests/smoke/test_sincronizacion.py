"""Configuración → Sincronización y Parámetros contra el contrato de los pilotos (F07-P08): listados paginados, el error
de un proceso que no corre y los logs con el detalle separado."""

import pytest

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]

HX = {"HX-Request": "true"}
PROCESO = {
    "id": "p-1",
    "codigo": "sync_nomina_odoo",
    "nombre": "Nómina desde Odoo",
    "descripcion": "",
    "tipo_origen": "odoo",
    "activo": False,
    "ultima_ejecucion": None,
    "ultimo_resultado": None,
    "registros_procesados": 0,
    "registros_actualizados": 0,
    "registros_creados": 0,
    "registros_errores": 0,
}
PAGINA = {"total": 1, "pagina": 1, "por_pagina": 100, "total_paginas": 1}


def _sesion(client, fake_api, *permisos):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": "usuario"}
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def test_ejecutar_un_proceso_que_no_corre_muestra_el_error_de_la_api(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "configuracion", "configuracion.actualizacion_datos")
    fake_api.respond("POST", "/sincronizacion/procesos/p-1/ejecutar", {"detail": "El proceso está desactivado"}, 409)
    fake_api.respond("GET", "/sincronizacion/procesos?por_pagina=100", {"items": [PROCESO], **PAGINA})

    html = frontend_client.post("/configuracion/sincronizacion/p-1/ejecutar", headers=HX).get_data(as_text=True)

    assert "El proceso está desactivado" in html and "bg-red-50" in html
    assert "Nómina desde Odoo" in html


def test_los_logs_muestran_solo_los_errores_del_detalle(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "configuracion", "configuracion.actualizacion_datos")
    fake_api.respond("GET", "/sincronizacion/procesos/p-1", PROCESO)
    log = {
        "id": "l-1",
        "proceso_id": "p-1",
        "fecha_inicio": "2026-10-15T10:00:00",
        "fecha_fin": "2026-10-15T10:01:00",
        "resultado": "error",
        "mensaje": "1 error",
        "registros_procesados": 2,
        "registros_actualizados": 1,
        "registros_creados": 0,
        "registros_errores": 1,
        "ejecutado_por": "user@example.com",
        "detalle_errores": [{"tipo": "DNI duplicado", "dni": "30111222"}],
        "actualizaciones": [{"dni": "40111222"}],
    }
    fake_api.respond("GET", "/sincronizacion/procesos/p-1/logs?por_pagina=20", {"items": [log], **PAGINA})

    html = frontend_client.get("/configuracion/sincronizacion/p-1/logs", headers=HX).get_data(as_text=True)

    assert "DNI duplicado" in html and "30111222" in html
    assert "actualizaciones" not in html and "40111222" not in html


def test_parametros_pide_todos_en_una_pagina(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "configuracion", "configuracion.parametros")
    fake_api.respond("GET", "/parametros?por_pagina=100", {"items": [], "categorias": [], **PAGINA, "total": 0})

    assert frontend_client.get("/parametros", headers=HX).status_code == 200
    assert any(c["endpoint"] == "/parametros?por_pagina=100" for c in fake_api.calls)


def test_los_logs_sin_htmx_vuelven_a_la_pantalla_de_procesos(frontend_client, fake_api):
    """PG-33: sin HTMX la ruta hacía render de una plantilla que no existe (500)."""
    _sesion(frontend_client, fake_api, "configuracion", "configuracion.actualizacion_datos")

    respuesta = frontend_client.get("/configuracion/sincronizacion/p-1/logs")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/configuracion/sincronizacion")
    assert not any("/logs" in c["endpoint"] for c in fake_api.calls)
