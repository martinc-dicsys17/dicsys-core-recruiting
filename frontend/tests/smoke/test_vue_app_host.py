import json
import re

import pytest

from modulos.vue_app import app_module as vue_app

INDICE_COMPILADO = (
    '<!doctype html><html><body><div id="app"></div>'
    f'{vue_app.MARCADOR_BOOTSTRAP}</body></html>'
)

MENUS = {
    "items": [
        {
            "codigo": "recruiting",
            "nombre": "Recruiting",
            "icono": "user-check",
            "items": [
                {"codigo": "candidatos", "nombre": "Candidatos", "icono": "users", "ruta": "recruiting.candidatos", "items": []},
            ],
        }
    ]
}


def _iniciar_sesion(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "dev@example.com", "nombre": "Dev", "rol": "admin"}


@pytest.mark.frontend
@pytest.mark.smoke
def test_la_spa_vue_exige_sesion(frontend_client):
    response = frontend_client.get("/v2/recruiting/blacklist")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


@pytest.mark.frontend
@pytest.mark.smoke
def test_la_spa_vue_se_sirve_con_los_datos_de_la_sesion(frontend_client, fake_api, monkeypatch):
    monkeypatch.setattr(vue_app, "_leer_indice", lambda: INDICE_COMPILADO)
    fake_api.respond("GET", "/menus", MENUS)
    _iniciar_sesion(frontend_client)

    response = frontend_client.get("/v2/recruiting/blacklist")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<div id="app"></div>' in html
    bloque = re.search(r'<script id="dicsys-bootstrap" type="application/json">(.*?)</script>', html, re.S)
    datos = json.loads(bloque.group(1))
    assert datos["origen"] == "servidor"
    assert datos["usuario"]["email"] == "dev@example.com"
    items = datos["menus"][0]["items"]
    assert {"nombre": "Candidatos", "icono": "users", "url": "/recruiting/candidatos", "vue": False} in items
    assert {"nombre": "Blacklist", "icono": "user-x", "url": "/v2/recruiting/blacklist", "vue": True} in items


@pytest.mark.frontend
@pytest.mark.smoke
def test_la_spa_vue_avisa_si_no_esta_compilada(frontend_client, monkeypatch):
    monkeypatch.setattr(vue_app, "_leer_indice", lambda: None)
    _iniciar_sesion(frontend_client)

    response = frontend_client.get("/v2/recruiting/blacklist")

    assert response.status_code == 503
    assert "npm run build" in response.get_data(as_text=True)


@pytest.mark.frontend
@pytest.mark.smoke
def test_el_menu_actual_muestra_el_acceso_vue_sin_alterar_los_items_existentes(frontend_client, fake_api):
    fake_api.respond("GET", "/menus", MENUS)
    fake_api.respond("GET", "/recruiting/parametros/config", {})
    _iniciar_sesion(frontend_client)

    html = frontend_client.get("/recruiting/parametros").get_data(as_text=True)

    assert 'href="/recruiting/candidatos"' in html
    acceso = re.search(r'<a href="/v2/recruiting/blacklist".*?</a>', html, re.S).group(0)
    assert "Blacklist" in acceso and ">VUE<" in acceso and "bg-emerald-50/70" in acceso


@pytest.mark.frontend
@pytest.mark.smoke
def test_el_compilado_versionado_esta_completo_y_flask_lo_sirve(frontend_client, fake_api):
    """El despliegue no compila Vue: frontend/static/vue debe venir en el repositorio con todos sus recursos."""
    with frontend_client.application.app_context():
        indice = vue_app._leer_indice()
    assert indice is not None and vue_app.MARCADOR_BOOTSTRAP in indice

    recursos = re.findall(r'(?:src|href)="(/static/vue/[^"]+)"', indice)
    assert any(r.endswith(".js") for r in recursos) and any(r.endswith(".css") for r in recursos)
    for recurso in recursos:
        respuesta = frontend_client.get(recurso)
        assert respuesta.status_code == 200, recurso
        respuesta.close()


def test_nuevo_candidato_vue_exige_el_item_candidatos_en_el_acceso_directo(frontend_client, fake_api):
    """/v2/recruiting/candidatos/nuevo respeta el permiso de la URL original; el resto de /v2 sigue pidiendo solo sesion."""
    ruta = "/v2/recruiting/candidatos/nuevo"
    assert frontend_client.get(ruta).status_code == 302  # sin sesion: al login

    fake_api.respond("GET", "/menus", {"items": []})
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {"recruiting": True, "recruiting.dashboard": True}})
    with frontend_client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": "usuario"}
    assert frontend_client.get(ruta).status_code == 403
    assert frontend_client.get("/v2/recruiting/blacklist").status_code == 200  # el host general no cambia

    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {"recruiting": True, "recruiting.candidatos": True}})
    assert frontend_client.get(ruta).status_code == 200
