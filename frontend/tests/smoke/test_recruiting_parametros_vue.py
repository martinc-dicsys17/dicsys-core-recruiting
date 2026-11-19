"""Recruiting → Parámetros (ítem «parametros») en la interfaz Vue: las URLs de siempre exigen el permiso y redirigen a
la SPA conservando sus parámetros; las URLs de la SPA exigen el mismo permiso (el historial, además, ser
administrador), también con barra final; la limpieza de datos va por la ruta de Flask (no por el proxy JSON, que corta
a los 10 s) y el proxy /api/v1 reenvía el navegador para la auditoría. El backend valida el acceso de verdad."""

from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

from app import create_app

pytestmark = [pytest.mark.frontend]

# (URL de siempre, ruta de la SPA)
PANTALLAS = [
    ("/recruiting/parametros", "/v2/recruiting/parametros"),
    ("/recruiting/parametros/skills", "/v2/recruiting/parametros/skills"),
    ("/recruiting/parametros/habilidades", "/v2/recruiting/parametros/habilidades"),
    ("/recruiting/parametros/provincias", "/v2/recruiting/parametros/provincias"),
    ("/recruiting/parametros/ciudades", "/v2/recruiting/parametros/ciudades"),
    ("/recruiting/parametros/lideres", "/v2/recruiting/parametros/lideres"),
    ("/recruiting/parametros/reclutadores", "/v2/recruiting/parametros/reclutadores"),
    ("/recruiting/parametros/perfiles-profesionales", "/v2/recruiting/parametros/perfiles-profesionales"),
    ("/recruiting/parametros/motivos-blacklist", "/v2/recruiting/parametros/motivos-blacklist"),
    ("/recruiting/parametros/archivos-cv", "/v2/recruiting/parametros/archivos-cv"),
]
HISTORIAL = "/recruiting/parametros/historial-cargas-cv"
HISTORIAL_SPA = f"/v2{HISTORIAL}"
LIMPIAR = "/recruiting/parametros/archivos-cv/limpiar-bd"
RESUMEN = {
    "registros": {"recruiting_candidatos": 3},
    "archivos": {"cv_procesados_ok": 2},
    "total_registros": 3,
    "total_archivos": 2,
}


def _sesion(client, fake_api, *permisos, rol="usuario"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def _con_item(client, fake_api, rol="usuario"):
    _sesion(client, fake_api, "recruiting", "recruiting.parametros", rol=rol)


def _destino(respuesta):
    assert respuesta.status_code == 302
    destino = urlsplit(respuesta.headers["Location"])
    return destino.path, parse_qsl(destino.query)


# --- URLs de siempre: permiso y redirección -------------------------------------------------------------------------


@pytest.mark.parametrize("legacy, spa", PANTALLAS)
def test_la_url_de_siempre_redirige_a_la_spa(frontend_client, fake_api, legacy, spa):
    _con_item(frontend_client, fake_api)

    assert _destino(frontend_client.get(legacy)) == (spa, [])
    assert not [c for c in fake_api.calls if c["endpoint"].startswith("/recruiting/parametros")]  # los datos los pide Vue


@pytest.mark.parametrize("legacy, spa", [PANTALLAS[0], PANTALLAS[4], PANTALLAS[9]])
def test_la_redireccion_conserva_los_parametros_de_la_url(frontend_client, fake_api, legacy, spa):
    _con_item(frontend_client, fake_api)

    ruta, consulta = _destino(frontend_client.get(f"{legacy}?provincia_id=3&q=villa&vacio="))

    assert ruta == spa
    assert consulta == [("provincia_id", "3"), ("q", "villa")]  # sin los parámetros vacíos


@pytest.mark.parametrize("consulta", ["ruta=otra", "_external=1", "_scheme=http", "_anchor=x", "_method=POST"])
def test_un_parametro_con_nombre_reservado_de_url_for_no_rompe_la_redireccion(frontend_client, fake_api, consulta):
    _con_item(frontend_client, fake_api)

    ruta, conservados = _destino(frontend_client.get(f"/recruiting/parametros/skills?{consulta}&q=java"))

    assert ruta == "/v2/recruiting/parametros/skills" and conservados == [("q", "java")]


@pytest.mark.parametrize("legacy", [p[0] for p in PANTALLAS] + [HISTORIAL])
def test_sin_el_item_parametros_la_url_de_siempre_responde_403(frontend_client, fake_api, legacy):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    assert frontend_client.get(legacy).status_code == 403


def test_el_historial_de_siempre_es_solo_para_administradores(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get(HISTORIAL).status_code == 403


def test_el_administrador_va_al_historial_de_la_spa_conservando_los_filtros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, rol="admin")

    ruta, consulta = _destino(frontend_client.get(f"{HISTORIAL}?resultado=parcial"))

    assert ruta == HISTORIAL_SPA and consulta == [("resultado", "parcial")]


# --- URLs de la SPA -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("spa", [p[1] for p in PANTALLAS] + [HISTORIAL_SPA])
def test_la_spa_sin_sesion_redirige_al_login(frontend_client, spa):
    respuesta = frontend_client.get(spa)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("spa", [p[1] for p in PANTALLAS] + [HISTORIAL_SPA])
def test_la_spa_sin_el_item_parametros_responde_403(frontend_client, fake_api, spa):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    assert frontend_client.get(spa).status_code == 403


@pytest.mark.parametrize("spa", [p[1] for p in PANTALLAS])
def test_la_spa_abre_con_el_item(frontend_client, fake_api, spa):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(spa)

    assert respuesta.status_code == 200
    assert b'id="dicsys-bootstrap"' in respuesta.data


def test_el_historial_de_la_spa_responde_403_a_quien_no_es_administrador(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get(HISTORIAL_SPA).status_code == 403


def test_el_historial_de_la_spa_abre_para_el_administrador_y_avisa_que_lo_es(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, rol="admin")

    respuesta = frontend_client.get(HISTORIAL_SPA)

    assert respuesta.status_code == 200
    assert b'"esAdmin": true' in respuesta.data


@pytest.mark.parametrize("variante", [f"{HISTORIAL_SPA}/", f"{HISTORIAL_SPA}//", "/v2/recruiting/parametros/skills/"])
def test_con_barra_final_redirige_a_la_ruta_que_controla_el_permiso(frontend_client, fake_api, variante):
    _con_item(frontend_client, fake_api)

    ruta, consulta = _destino(frontend_client.get(f"{variante}?pagina=2"))

    assert ruta == variante.rstrip("/") and consulta == [("pagina", "2")]


def test_con_barra_final_el_historial_sigue_respondiendo_403(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(f"{HISTORIAL_SPA}/", follow_redirects=True)

    assert respuesta.status_code == 403


def test_la_raiz_de_la_spa_no_redirige(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get("/v2/").status_code == 200


# --- Limpieza de datos (ruta de Flask, administradores) -------------------------------------------------------------


def test_la_limpieza_reenvia_la_confirmacion_y_devuelve_el_resumen(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, rol="admin")
    fake_api.respond("POST", LIMPIAR, RESUMEN)

    respuesta = frontend_client.post(LIMPIAR, headers={"Accept": "application/json"})

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"success": True, "resumen": RESUMEN}
    llamada = next(c for c in fake_api.calls if c["endpoint"] == LIMPIAR)
    assert llamada["method"] == "POST" and llamada["data"] == {"confirmar": True} and llamada["token"] == "test-token"


def test_la_limpieza_es_solo_para_administradores(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.post(LIMPIAR, headers={"Accept": "application/json"})

    assert respuesta.status_code == 403 and respuesta.get_json()["success"] is False
    assert not [c for c in fake_api.calls if c["endpoint"] == LIMPIAR]


def test_el_error_de_la_limpieza_llega_con_su_detalle(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, rol="admin")
    fake_api.respond("POST", LIMPIAR, {"detail": "Debés confirmar la limpieza para ejecutarla"}, 400)

    respuesta = frontend_client.post(LIMPIAR, headers={"Accept": "application/json"})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"success": False, "error": "Debés confirmar la limpieza para ejecutarla"}


# --- Proxy /api/v1: el navegador para la auditoría ------------------------------------------------------------------


@pytest.fixture
def proxy_http(monkeypatch):
    solicitudes = []

    def backend(peticion):
        solicitudes.append(peticion)
        return httpx.Response(200, json={"match_minimo_porcentaje": 60})

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(config={"TESTING": True, "SECRET_KEY": "frontend-test-secret", "API_URL": "http://backend.test"})
    return app, solicitudes


def test_el_proxy_reenvia_el_navegador_y_no_las_cabeceras_de_cliente_que_manda_el_navegador(proxy_http):
    app, solicitudes = proxy_http
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["token"] = "test-token"

    respuesta = cliente.put(
        "/api/v1/recruiting/parametros/config",
        json={"match_minimo_porcentaje": 60},
        headers={"User-Agent": "Navegador/1.0", "X-Cliente-User-Agent": "falso", "X-Cliente-IP": "6.6.6.6"},
    )

    assert respuesta.status_code == 200
    cabeceras = solicitudes[0].headers
    assert cabeceras["X-Cliente-User-Agent"] == "Navegador/1.0"
    assert cabeceras["X-Cliente-IP"] != "6.6.6.6"
    assert cabeceras["Authorization"] == "Bearer test-token"


def test_el_proxy_recorta_un_navegador_demasiado_largo(proxy_http):
    app, solicitudes = proxy_http
    cliente = app.test_client()
    with cliente.session_transaction() as sesion:
        sesion["token"] = "test-token"

    cliente.get("/api/v1/recruiting/parametros/config", headers={"User-Agent": "x" * 800})

    assert solicitudes[0].headers["X-Cliente-User-Agent"] == "x" * 500
