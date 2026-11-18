"""Recruiting → Pipeline (ítem «gestion_busquedas»): la vista global, la selección individual y el Pipeline de una
búsqueda son pantallas Vue. Acá se prueba que las URLs de siempre exigen el permiso y redirigen conservando sus
parámetros, que las URLs de la SPA exigen el mismo permiso y que la ruta que mueve de etapa, descarta o reingresa
reenvía al backend igual que antes. El backend valida el acceso de verdad."""

from urllib.parse import parse_qsl, urlsplit

import pytest

pytestmark = [pytest.mark.frontend]

ID_OP = "33333333-3333-3333-3333-333333333333"
ID_CAND = "55555555-5555-5555-5555-555555555555"
ETAPA = f"/recruiting/oportunidades/{ID_OP}/candidatos/{ID_CAND}/etapa"


def _sesion(client, fake_api, *permisos, rol="usuario"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def _con_item(client, fake_api):
    _sesion(client, fake_api, "recruiting", "recruiting.gestion_busquedas")


def _destino(respuesta):
    assert respuesta.status_code == 302
    destino = urlsplit(respuesta.headers["Location"])
    return destino.path, dict(parse_qsl(destino.query))


# --- Permisos -------------------------------------------------------------------------------------------------------

RUTAS = [
    "/recruiting/gestion-busquedas",
    "/recruiting/asignar-candidato",
    f"/recruiting/oportunidades/{ID_OP}/pipeline",
    "/v2/recruiting/gestion-busquedas",
    "/v2/recruiting/asignar-candidato",  # alias: es la URL que arma Flask para el ítem del menú
    f"/v2/recruiting/oportunidades/{ID_OP}/pipeline",
]


@pytest.mark.parametrize("ruta", RUTAS)
def test_sin_sesion_redirige_al_login(frontend_client, ruta):
    respuesta = frontend_client.get(ruta)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("ruta", RUTAS)
def test_sin_el_item_pipeline_responde_403(frontend_client, fake_api, ruta):
    # Con Búsquedas y Candidatos, pero sin Pipeline: ni la URL de siempre ni la de la SPA abren
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.oportunidades", "recruiting.candidatos")
    assert frontend_client.get(ruta).status_code == 403


@pytest.mark.parametrize("ruta", RUTAS[3:])
def test_las_urls_de_la_spa_abren_con_el_item(frontend_client, fake_api, ruta):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(ruta)

    assert respuesta.status_code == 200
    assert b'id="dicsys-bootstrap"' in respuesta.data


def test_el_administrador_entra_sin_el_item(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, rol="admin")
    assert frontend_client.get("/v2/recruiting/gestion-busquedas").status_code == 200


def test_la_ruta_de_etapa_tambien_exige_el_item(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.oportunidades")
    assert frontend_client.put(ETAPA, json={"etapa_actual": "Screening"}).status_code == 403
    assert frontend_client.post(ETAPA, data={"etapa_actual": "Screening"}).status_code == 403


# --- Redirecciones a la pantalla Vue ---------------------------------------------------------------------------------


def test_la_vista_global_redirige_conservando_el_filtro(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    ruta, query = _destino(frontend_client.get("/recruiting/gestion-busquedas?alcance_candidatos=propios"))

    assert ruta == "/v2/recruiting/gestion-busquedas"
    assert query == {"alcance_candidatos": "propios"}
    # Flask no pide datos: los pide la pantalla Vue a la API
    prefijos = ("/recruiting/pipeline", "/recruiting/oportunidades")
    assert not [c for c in fake_api.calls if c["endpoint"].startswith(prefijos)]


def test_la_seleccion_individual_redirige_conservando_la_vista(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    ruta, query = _destino(frontend_client.get("/recruiting/asignar-candidato?vista=individual&alcance_candidatos="))

    assert ruta == "/v2/recruiting/gestion-busquedas"
    assert query == {"vista": "individual"}


def test_sin_parametros_redirige_limpio(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get("/recruiting/gestion-busquedas")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/v2/recruiting/gestion-busquedas")


def test_el_pipeline_de_una_busqueda_redirige_conservando_los_parametros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    ruta, query = _destino(
        frontend_client.get(
            f"/recruiting/oportunidades/{ID_OP}/pipeline?etapas=Oferta,Examen&columna=Oferta&alcance_candidatos=propios"
        )
    )

    assert ruta == f"/v2/recruiting/oportunidades/{ID_OP}/pipeline"
    assert query == {"etapas": "Oferta,Examen", "columna": "Oferta", "alcance_candidatos": "propios"}
    # Flask no pide la búsqueda ni sus candidatos: los pide la pantalla Vue a la API
    assert not [c for c in fake_api.calls if c["endpoint"].startswith("/recruiting/")]


def test_el_id_que_no_es_uuid_responde_404(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get("/recruiting/oportunidades/no-es-un-uuid/pipeline").status_code == 404


def test_el_atajo_pipeline_lleva_al_de_la_primera_busqueda_abierta(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond(
        "GET",
        "/recruiting/oportunidades?por_pagina=20",
        {"items": [{"id": "x", "estado": "Ganada"}, {"id": ID_OP, "estado": "Abierta"}]},
    )

    respuesta = frontend_client.get("/recruiting/pipeline")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/recruiting/oportunidades/{ID_OP}/pipeline")


# --- Mover de etapa, descartar y reingresar (ruta de Flask que usa la pantalla Vue) -------------------------------


def test_mover_de_etapa_reenvia_el_cuerpo_al_backend(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    respuesta_backend = {"ok": True, "id": "g1", "etapa_actual": "Entrevista Líder Dicsys", "estado": "En proceso"}
    fake_api.respond("PUT", ETAPA, respuesta_backend)

    respuesta = frontend_client.put(
        ETAPA,
        json={
            "etapa_actual": "Entrevista Líder Dicsys",
            "estado": "En proceso",
            "feedback_etapa": None,
            "pretension_salarial_bruta_ars": 1500000,
        },
    )

    assert respuesta.status_code == 200 and respuesta.get_json() == respuesta_backend
    llamada = [c for c in fake_api.calls if c["method"] == "PUT"][0]
    # Lo vacío no viaja (como antes): el backend lo toma como ausente
    assert llamada["data"] == {
        "etapa_actual": "Entrevista Líder Dicsys",
        "estado": "En proceso",
        "pretension_salarial_bruta_ars": 1500000,
    }


def test_el_error_del_backend_llega_a_la_pantalla_con_su_codigo(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond("PUT", ETAPA, {"detail": "La búsqueda está Ganada y cerrada"}, 409)

    respuesta = frontend_client.put(ETAPA, json={"etapa_actual": "Descartados", "estado": "Descartado"})

    assert respuesta.status_code == 409
    assert respuesta.get_json() == {"success": False, "error": "La búsqueda está Ganada y cerrada"}


def test_un_adjunto_de_otro_formato_se_rechaza_sin_llamar_al_backend(frontend_client, fake_api):
    from io import BytesIO

    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.post(
        ETAPA,
        data={"etapa_actual": "Oferta", "estado": "En proceso", "archivo": (BytesIO(b"x"), "programa.exe")},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"success": False, "error": "Tipo de archivo no permitido (.exe)."}
    assert not [c for c in fake_api.calls if c["method"] == "PUT"]
