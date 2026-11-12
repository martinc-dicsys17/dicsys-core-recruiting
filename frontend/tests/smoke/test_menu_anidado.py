"""El sidebar dibuja el tercer nivel: un ítem que agrupa hijos."""

import pytest


def _set_session(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": "usuario"}


def _menus(fake_api, padre_ruta):
    fake_api.respond(
        "GET",
        "/menus",
        {
            "items": [
                {
                    "codigo": "admin_contable",
                    "nombre": "Administración",
                    "icono": "calculator",
                    "orden": 5,
                    "items": [
                        {
                            "codigo": "padre",
                            "nombre": "Grupo padre",
                            "icono": "truck",
                            "ruta": padre_ruta,
                            "es_link": bool(padre_ruta),
                            "orden": 1,
                            "items": [
                                {
                                    "codigo": "hijo",
                                    "nombre": "Hijo visible",
                                    "icono": "clipboard-check",
                                    "ruta": "administracion.clientes_list",
                                    "es_link": True,
                                    "orden": 1,
                                    "items": [],
                                }
                            ],
                        }
                    ],
                }
            ]
        },
    )


def _pagina(frontend_client, fake_api):
    fake_api.respond(
        "GET",
        "/notificaciones-internas/historial?pagina=1&por_pagina=20",
        {"items": [], "total": 0, "pagina": 1, "por_pagina": 20, "total_paginas": 1},
    )
    return frontend_client.get("/notificaciones").get_data(as_text=True)


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_padre_sin_ruta_es_rotulo_y_el_hijo_es_link(frontend_client, fake_api):
    _set_session(frontend_client)
    _menus(fake_api, None)

    html = _pagina(frontend_client, fake_api)

    assert "Grupo padre" in html
    assert 'href="/administracion/clientes"' in html
    assert "Hijo visible" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_padre_con_ruta_es_link(frontend_client, fake_api):
    _set_session(frontend_client)
    _menus(fake_api, "administracion.export_recibos_list")

    html = _pagina(frontend_client, fake_api)

    assert 'href="/administracion/export-recibos"' in html
    assert "Hijo visible" in html
