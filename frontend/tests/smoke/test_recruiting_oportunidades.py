"""Recruiting → Búsquedas (oportunidades): permisos de las rutas, listado con sus filtros y paginación, formulario de alta,
ficha (ver y editar), asignaciones y candidatos de la búsqueda (reenvío al backend). El backend valida el acceso de
verdad: acá se prueba lo que la pantalla pide, muestra y reenvía."""

from urllib.parse import parse_qsl, urlsplit

import pytest

pytestmark = [pytest.mark.frontend]

ID_OP = "33333333-3333-3333-3333-333333333333"
ID_EXTERNO = "44444444-4444-4444-4444-444444444444"
ID_CAND = "55555555-5555-5555-5555-555555555555"

PERMISOS_INTERNO = {
    "puede_crear_busquedas": True,
    "puede_eliminar_busquedas": True,
    "puede_ver_lider_tipo_fecha_busqueda": True,
    "puede_ver_smart_matching": True,
    "puede_asignar_candidatos": True,
    "puede_asignar_reclutador": True,
    "puede_administrar_externos": True,
    "es_externo": False,
}
PERMISOS_EXTERNO = {clave: False for clave in PERMISOS_INTERNO} | {"es_externo": True}

OPORTUNIDAD = {
    "id": ID_OP,
    "empresa_id": "22222222-2222-2222-2222-222222222222",
    "id_busqueda": "OP-1001",
    "cliente": "Acme SA",
    "titulo": "Desarrollador Python",
    "estado": "Abierta",
    "recruiter_nombre": "Marcela Gomez",
    "lider_nombre": "Lucia Paz",
    "fecha_asignacion": "2026-11-10T12:00:00",
    "fecha_creacion": "2026-11-01",
    "dias_abierta": 12,
    "dias_reclutador": 3,
    "area": "Operaciones / IT",
    "puesto": "Backend Developer",
    "seniority": "Senior",
    "modalidad": "Hibrido",
    "vacantes": 1,
    "rango": "$ 1.000.000 - 2.000.000",
    "prioridad": "Critica",
    "tipo": "Efectiva",
    "skills": ["Python", "SQL"],
    "habilidades": ["Liderazgo"],
    "skills_deseadas": ["Docker"],
    "descripcion": "Equipo de plataforma",
    "candidatos_pipeline": 4,
    "coordinando_entrevista": 1,
    "entrevistados_rrhh": 2,
    "presentacion_lider": 0,
    "feedback_lider": 0,
    "presentacion_cliente": 0,
    "q_activos": 3,
    "creador_id": None,
    "recruiter_id": None,
    "lider_id": None,
    "externo_id": None,
    "externo_nombre": None,
    "externo_email": None,
    "activo": True,
    "created_at": "2026-11-01T12:00:00",
    "updated_at": "2026-11-10T12:00:00",
}

CANDIDATO_EN_BUSQUEDA = {
    "id": ID_CAND,
    "gestion_id": "66666666-6666-6666-6666-666666666666",
    "candidato_id": ID_CAND,
    "oportunidad_id": ID_OP,
    "codigo": "C-1001",
    "nombre": "Beto Rios",
    "nombre_pila": "Beto",
    "apellido": "Rios",
    "email": "beto@example.com",
    "telefono": None,
    "ubicacion": None,
    "headline": "Backend Developer",
    "seniority": "Senior",
    "etapa": "Candidato",
    "etapa_actual": "Candidato",
    "estado": "En proceso",
    "motivo_descarte": None,
    "feedback_etapa": None,
    "pretension_salarial_bruta_ars": None,
    "fecha_cambio_etapa": "2026-11-10T12:00:00",
    "created_at": "2026-11-10T12:00:00",
    "updated_at": "2026-11-10T12:00:00",
    "cv_url": None,
    "linkedin_url": None,
    "es_anonimo": False,
    "es_externo": False,
    "presentado_por": "Ana Lopez",
}

SUGERIDO = {
    "id": "77777777-7777-7777-7777-777777777777",
    "codigo": "C-2002",
    "nombre": "Julia",
    "apellido": "Mendez",
    "nombre_completo": "Julia Mendez",
    "email": "julia@example.com",
    "headline": "Backend Developer",
    "seniority": "Senior",
    "skills": ["Python"],
    "habilidades": [],
    "skills_coincidentes": ["Python"],
    "habilidades_coincidentes": [],
    "porcentaje_match": 50,
    "match_porcentaje": 50,
    "ya_asignado": False,
}


def _pagina(items, total=None, pagina=1, por_pagina=20):
    total = len(items) if total is None else total
    return {
        "items": items,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": max(1, -(-total // por_pagina)),
    }


def _sesion(client, fake_api, *permisos, rol="usuario", acciones=PERMISOS_INTERNO):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})
    fake_api.respond("GET", "/recruiting/oportunidades/permisos", acciones)


def _con_item(client, fake_api, **kwargs):
    _sesion(client, fake_api, "recruiting", "recruiting.oportunidades", **kwargs)


def _catalogos(fake_api):
    fake_api.respond("GET", "/recruiting/skills", [{"id": "s1", "nombre": "Python", "categoria": "Lenguajes"}])
    fake_api.respond("GET", "/recruiting/habilidades", [{"id": "h1", "nombre": "Liderazgo", "activo": True}])
    fake_api.respond("GET", "/recruiting/candidatos/perfiles-puesto", ["Backend Developer", "QA Tester"])
    fake_api.respond("GET", "/recruiting/lideres", [{"id": "l1", "nombre": "Lucia Paz", "activo": True}])
    fake_api.respond("GET", "/recruiting/reclutadores", [{"id": "r1", "nombre": "Marcela Gomez", "activo": True}])
    fake_api.respond(
        "GET",
        "/recruiting/externos-disponibles",
        [{"id": ID_EXTERNO, "nombre": "Externo Uno", "email": "externo@example.com"}],
    )


def _listado(
    fake_api,
    respuesta,
    status=200,
    endpoint="/recruiting/oportunidades?pagina=1&por_pagina=20&estado=Abierta&tipo=Efectiva",
):
    _catalogos(fake_api)
    fake_api.respond("GET", endpoint, respuesta, status)


def _detalle(fake_api, op=OPORTUNIDAD, candidatos=(CANDIDATO_EN_BUSQUEDA,), sugeridos=(SUGERIDO,)):
    _catalogos(fake_api)
    fake_api.respond("GET", f"/recruiting/oportunidades/{ID_OP}", op)
    fake_api.respond("GET", f"/recruiting/oportunidades/{ID_OP}/candidatos", list(candidatos))
    fake_api.respond("GET", f"/recruiting/oportunidades/{ID_OP}/candidatos-compatibles", list(sugeridos))
    fake_api.respond("GET", "/recruiting/config", {"match_minimo_porcentaje": 60})


def _llamadas(fake_api, metodo, prefijo):
    return [c for c in fake_api.calls if c["method"] == metodo and c["endpoint"].startswith(prefijo)]


# --- Permisos de las rutas ------------------------------------------------------------------------------------------

RUTAS_GET = ["/recruiting/oportunidades", "/recruiting/oportunidades/nueva", f"/recruiting/oportunidades/{ID_OP}"]


@pytest.mark.parametrize("ruta", RUTAS_GET)
def test_sin_sesion_redirige_al_login(frontend_client, ruta):
    respuesta = frontend_client.get(ruta)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("ruta", RUTAS_GET)
def test_sin_el_item_oportunidades_responde_403(frontend_client, fake_api, ruta):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    assert frontend_client.get(ruta).status_code == 403


def test_las_acciones_de_escritura_tambien_exigen_el_item(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    base = f"/recruiting/oportunidades/{ID_OP}"
    assert frontend_client.post("/recruiting/oportunidades", json={"titulo": "X"}).status_code == 403
    assert frontend_client.put(base, json={"rango": "x"}).status_code == 403
    assert frontend_client.post(f"{base}/asignar").status_code == 403
    assert frontend_client.post(f"{base}/desasignar").status_code == 403
    assert frontend_client.post(f"{base}/reclutador", json={}).status_code == 403
    assert frontend_client.post(f"{base}/externo", json={}).status_code == 403
    assert frontend_client.delete(f"{base}/externo").status_code == 403
    assert frontend_client.post(f"{base}/candidatos", json={}).status_code == 403


# --- Listado y alta: pantallas Vue (las URLs originales redirigen) -------------------------------------------------


def test_el_listado_redirige_a_la_pantalla_vue_conservando_los_filtros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(
        "/recruiting/oportunidades?pagina=2&por_pagina=50&estado=Ganada&tipo=Todas&busqueda=ana perez&otro=x"
    )

    assert respuesta.status_code == 302
    destino = urlsplit(respuesta.headers["Location"])
    assert destino.path == "/v2/recruiting/oportunidades"
    assert dict(parse_qsl(destino.query)) == {
        "pagina": "2",
        "por_pagina": "50",
        "estado": "Ganada",
        "tipo": "Todas",
        "busqueda": "ana perez",
    }
    # Flask no pide datos: los pide la pantalla Vue a la API
    assert not _llamadas(fake_api, "GET", "/recruiting/oportunidades?")


def test_el_listado_sin_parametros_redirige_limpio(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get("/recruiting/oportunidades")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/v2/recruiting/oportunidades")


def test_el_alta_redirige_a_la_pantalla_vue(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get("/recruiting/oportunidades/nueva")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/v2/recruiting/oportunidades/nueva")


@pytest.mark.parametrize("ruta", ["/v2/recruiting/oportunidades", "/v2/recruiting/oportunidades/nueva", f"/v2/recruiting/oportunidades/{ID_OP}"])
def test_las_urls_de_la_spa_exigen_el_item_oportunidades(frontend_client, fake_api, ruta):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    assert frontend_client.get(ruta).status_code == 403


def test_el_alta_reenvia_el_formulario_al_backend_con_sus_alias(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond("POST", "/recruiting/oportunidades", OPORTUNIDAD, 201)

    respuesta = frontend_client.post(
        "/recruiting/oportunidades",
        json={
            "titulo": "  Desarrollador Python ",
            "cliente": "Acme SA",
            "hm": "Lucia Paz",
            "reclutador": "",
            "vacantes": "2",
            "estado": "Abierta",
            "tipo": "Efectiva",
            "seniority": "",
            "skills": "Python, SQL,",
            "habilidades": ["Liderazgo"],
            "skills_deseadas": [],
            "descripcion": "  ",
            "fecha_asignacion": "2001-01-01",
        },
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_json()
    assert cuerpo["success"] is True and cuerpo["redirect"].endswith("/recruiting/oportunidades")
    enviado = _llamadas(fake_api, "POST", "/recruiting/oportunidades")[0]["data"]
    assert enviado["titulo"] == "Desarrollador Python" and enviado["lider_nombre"] == "Lucia Paz"
    assert enviado["recruiter_nombre"] is None and enviado["vacantes"] == 2
    assert enviado["skills"] == ["Python", "SQL"] and enviado["habilidades"] == ["Liderazgo"]
    assert enviado["descripcion"] is None
    assert "seniority" not in enviado and "fecha_asignacion" not in enviado


def test_el_alta_pasa_el_error_del_backend(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond(
        "POST",
        "/recruiting/oportunidades",
        {"detail": "Ya existe una búsqueda con este título para el cliente seleccionado"},
        400,
    )

    respuesta = frontend_client.post("/recruiting/oportunidades", json={"titulo": "X", "cliente": "Y"})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {
        "success": False,
        "ok": False,
        "error": "Ya existe una búsqueda con este título para el cliente seleccionado",
    }


# --- Ficha ----------------------------------------------------------------------------------------------------------


def test_la_ficha_redirige_a_la_pantalla_vue_conservando_los_parametros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}?edit=true&volver=/recruiting/oportunidades")

    assert respuesta.status_code == 302
    destino = urlsplit(respuesta.headers["Location"])
    assert destino.path == f"/v2/recruiting/oportunidades/{ID_OP}"
    assert dict(parse_qsl(destino.query)) == {"edit": "true", "volver": "/recruiting/oportunidades"}
    # Flask no pide datos: los pide la pantalla Vue a la API
    assert not _llamadas(fake_api, "GET", f"/recruiting/oportunidades/{ID_OP}")


def test_el_id_que_no_es_uuid_responde_404(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get("/recruiting/oportunidades/no-es-un-uuid").status_code == 404


def test_editar_lleva_a_la_ficha_en_modo_edicion(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}/editar")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/v2/recruiting/oportunidades/{ID_OP}?edit=true")


def test_la_edicion_envia_solo_lo_que_cambio(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond("PUT", f"/recruiting/oportunidades/{ID_OP}", OPORTUNIDAD)

    respuesta = frontend_client.put(
        f"/recruiting/oportunidades/{ID_OP}",
        json={"estado": "Cancelada", "reclutador": "Marcela Gomez", "skills": ["Go"]},
    )

    assert respuesta.status_code == 200 and respuesta.get_json()["success"] is True
    assert _llamadas(fake_api, "PUT", f"/recruiting/oportunidades/{ID_OP}")[0]["data"] == {
        "estado": "Cancelada",
        "recruiter_nombre": "Marcela Gomez",
        "skills": ["Go"],
    }


def test_la_edicion_pasa_el_error_del_backend_con_su_codigo(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond("PUT", f"/recruiting/oportunidades/{ID_OP}", {"detail": "La búsqueda está Ganada"}, 409)

    respuesta = frontend_client.put(f"/recruiting/oportunidades/{ID_OP}", json={"rango": "x"})

    assert respuesta.status_code == 409 and respuesta.get_json()["error"] == "La búsqueda está Ganada"


# --- Asignaciones y candidatos --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "metodo,sufijo,cuerpo,metodo_api,datos_api,mensaje",
    [
        ("post", "asignar", None, "POST", None, "Búsqueda asignada correctamente."),
        ("post", "desasignar", None, "POST", None, "Búsqueda desasignada correctamente. Queda libre para ser tomada."),
        (
            "post",
            "reclutador",
            {"recruiter_nombre": " Marcela Gomez "},
            "POST",
            {"recruiter_nombre": "Marcela Gomez"},
            "Reclutador asignado correctamente.",
        ),
        (
            "post",
            "externo",
            {"externo_id": ID_EXTERNO},
            "PUT",
            {"externo_id": ID_EXTERNO},
            "Usuario externo asignado correctamente.",
        ),
        ("delete", "externo", None, "DELETE", None, "Asignación del usuario externo quitada."),
    ],
)
def test_las_acciones_de_asignacion_se_reenvian_al_backend(
    frontend_client, fake_api, metodo, sufijo, cuerpo, metodo_api, datos_api, mensaje
):
    _con_item(frontend_client, fake_api)
    endpoint = f"/recruiting/oportunidades/{ID_OP}/{sufijo}"
    fake_api.respond(metodo_api, endpoint, OPORTUNIDAD)

    respuesta = getattr(frontend_client, metodo)(f"/recruiting/oportunidades/{ID_OP}/{sufijo}", json=cuerpo)

    assert respuesta.status_code == 200
    resultado = respuesta.get_json()
    assert resultado["success"] is True and resultado["ok"] is True and resultado["message"] == mensaje
    assert resultado["oportunidad"]["id"] == ID_OP
    assert _llamadas(fake_api, metodo_api, endpoint)[0]["data"] == datos_api


def test_el_error_de_una_asignacion_llega_a_la_pantalla_con_su_codigo(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond(
        "POST", f"/recruiting/oportunidades/{ID_OP}/reclutador", {"detail": "No tenés permisos para asignar"}, 403
    )

    respuesta = frontend_client.post(f"/recruiting/oportunidades/{ID_OP}/reclutador", json={"recruiter_nombre": "X"})

    assert respuesta.status_code == 403 and respuesta.get_json()["error"] == "No tenés permisos para asignar"


def test_postular_un_candidato_reenvia_la_asignacion(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    asignacion = {
        "id": "p1",
        "candidato_id": ID_CAND,
        "solicitud_id": ID_OP,
        "etapa": "Candidato",
        "estado": "En proceso",
    }
    fake_api.respond("POST", f"/recruiting/oportunidades/{ID_OP}/candidatos", asignacion, 201)

    cuerpo = {"candidato_id": ID_CAND, "etapa": "Candidato", "estado": "En proceso", "observaciones": None}
    respuesta = frontend_client.post(f"/recruiting/oportunidades/{ID_OP}/candidatos", json=cuerpo)

    assert respuesta.status_code == 201 and respuesta.get_json() == {"success": True, "data": asignacion}
    assert _llamadas(fake_api, "POST", f"/recruiting/oportunidades/{ID_OP}/candidatos")[0]["data"] == cuerpo


def test_postular_con_error_del_backend_lo_muestra(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    fake_api.respond(
        "POST",
        f"/recruiting/oportunidades/{ID_OP}/candidatos",
        {"detail": "El candidato ya está asignado a esta búsqueda."},
        400,
    )

    respuesta = frontend_client.post(f"/recruiting/oportunidades/{ID_OP}/candidatos", json={"candidato_id": ID_CAND})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {"success": False, "error": "El candidato ya está asignado a esta búsqueda."}
