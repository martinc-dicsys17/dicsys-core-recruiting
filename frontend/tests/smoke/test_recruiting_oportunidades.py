"""Recruiting → Búsquedas (oportunidades): permisos de las rutas, listado con sus filtros y paginación, formulario de alta,
ficha (ver y editar), asignaciones y candidatos de la búsqueda (reenvío al backend). El backend valida el acceso de
verdad: acá se prueba lo que la pantalla pide, muestra y reenvía."""

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


# --- Listado --------------------------------------------------------------------------------------------------------


def test_el_listado_muestra_las_busquedas_y_la_paginacion(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _listado(fake_api, _pagina([OPORTUNIDAD], total=41, por_pagina=20))

    respuesta = frontend_client.get("/recruiting/oportunidades")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Desarrollador Python" in html and "Acme SA" in html and "Marcela Gomez" in html
    assert ID_OP in html and "/recruiting/oportunidades/${op.id}" in html  # las filas las arma Alpine con estos datos
    assert "/recruiting/oportunidades/nueva" in html
    assert "Mostrando" in html and "41" in html and "Página 1 de 3" in html
    assert "pagina=2" in html
    assert {
        "method": "GET",
        "endpoint": "/recruiting/oportunidades?pagina=1&por_pagina=20&estado=Abierta&tipo=Efectiva",
        "data": None,
        "token": "test-token",
    } in fake_api.calls


def test_el_listado_pasa_los_filtros_al_backend(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    endpoint = "/recruiting/oportunidades?pagina=2&por_pagina=50&estado=Ganada&tipo=Todas&busqueda=ana+perez"
    _listado(fake_api, _pagina([], total=0, pagina=2, por_pagina=50), endpoint=endpoint)

    respuesta = frontend_client.get(
        "/recruiting/oportunidades?pagina=2&por_pagina=50&estado=Ganada&tipo=Todas&busqueda=ana perez"
    )
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "No se encontraron búsquedas con los filtros actuales" in html
    assert 'value="ana perez"' in html


def test_los_valores_de_filtro_invalidos_vuelven_a_los_predeterminados(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _listado(
        fake_api, _pagina([]), endpoint="/recruiting/oportunidades?pagina=1&por_pagina=100&estado=Abierta&tipo=Efectiva"
    )

    assert (
        frontend_client.get("/recruiting/oportunidades?estado=Inventado&tipo=Rara&por_pagina=5000&pagina=x").status_code
        == 200
    )


def test_la_pagina_siguiente_conserva_los_filtros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    endpoint = "/recruiting/oportunidades?pagina=1&por_pagina=20&estado=todos&tipo=Potencial&busqueda=java"
    _listado(fake_api, _pagina([OPORTUNIDAD], total=45), endpoint=endpoint)

    html = frontend_client.get("/recruiting/oportunidades?estado=todos&tipo=Potencial&busqueda=java").get_data(
        as_text=True
    )

    assert "estado=todos" in html and "tipo=Potencial" in html and "busqueda=java" in html and "pagina=2" in html


def test_el_listado_con_error_del_backend_avisa_y_no_muestra_ceros(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _listado(fake_api, {"detail": "Falla del servidor"}, status=500)

    html = frontend_client.get("/recruiting/oportunidades").get_data(as_text=True)

    assert "Falla del servidor" in html and "oportunidades-error" in html


def test_el_boton_nueva_busqueda_solo_con_permiso(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, acciones=PERMISOS_EXTERNO)
    _listado(fake_api, _pagina([OPORTUNIDAD]))

    html = frontend_client.get("/recruiting/oportunidades").get_data(as_text=True)

    assert "/recruiting/oportunidades/nueva" not in html
    assert "externos-disponibles" not in [c["endpoint"] for c in fake_api.calls]


def test_el_externo_no_elige_el_tipo_y_siempre_pide_las_efectivas(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, acciones=PERMISOS_EXTERNO)
    _listado(fake_api, _pagina([OPORTUNIDAD]))

    html = frontend_client.get("/recruiting/oportunidades?tipo=Potencial").get_data(as_text=True)

    assert 'name="tipo"' not in html
    assert _llamadas(fake_api, "GET", "/recruiting/oportunidades?")[0]["endpoint"].endswith("tipo=Efectiva")


def test_el_listado_ofrece_asignar_externo_y_cancelar_segun_los_permisos(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _listado(fake_api, _pagina([OPORTUNIDAD]))
    html = frontend_client.get("/recruiting/oportunidades").get_data(as_text=True)
    assert '@click="abrirModalExterno(op)"' in html and '@click="cancelarBusqueda(op)"' in html
    assert "Externo Uno" in html

    _con_item(
        frontend_client,
        fake_api,
        acciones={**PERMISOS_INTERNO, "puede_eliminar_busquedas": False, "puede_administrar_externos": False},
    )
    html = frontend_client.get("/recruiting/oportunidades").get_data(as_text=True)
    assert '@click="abrirModalExterno(op)"' not in html and '@click="cancelarBusqueda(op)"' not in html


# --- Formulario de alta ---------------------------------------------------------------------------------------------


def test_el_formulario_de_alta_trae_los_catalogos(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _catalogos(fake_api)

    respuesta = frontend_client.get("/recruiting/oportunidades/nueva")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Backend Developer" in html and "Lucia Paz" in html and "Marcela Gomez" in html
    assert "Python" in html and "Liderazgo" in html
    assert 'value="Hibrido"' in html and 'value="Critica"' in html


def test_sin_permiso_para_crear_el_formulario_redirige_al_listado(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, acciones=PERMISOS_EXTERNO)

    respuesta = frontend_client.get("/recruiting/oportunidades/nueva")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/recruiting/oportunidades")


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


def test_la_ficha_muestra_la_busqueda_sus_candidatos_y_las_sugerencias(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _detalle(fake_api)

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Desarrollador Python" in html and "Acme SA" in html
    assert "Beto Rios" in html and "Julia Mendez" in html
    assert "60%" in html  # umbral de Smart Matching de la empresa
    assert "Cargar CV" not in html  # la carga de CV desde la búsqueda es del grupo EXTERNOS y queda para después
    assert "Híbrido" in html and "Hibrido" in html


def test_una_busqueda_ganada_se_ve_sin_smart_matching_ni_acciones(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    _detalle(fake_api, op={**OPORTUNIDAD, "estado": "Ganada"})

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Julia Mendez" not in html
    assert not _llamadas(fake_api, "GET", f"/recruiting/oportunidades/{ID_OP}/candidatos-compatibles")
    assert not _llamadas(fake_api, "GET", "/recruiting/externos-disponibles")


def test_el_externo_no_ve_smart_matching(frontend_client, fake_api):
    _con_item(frontend_client, fake_api, acciones=PERMISOS_EXTERNO)
    _detalle(fake_api)

    html = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}").get_data(as_text=True)

    assert "Julia Mendez" not in html
    assert not _llamadas(fake_api, "GET", f"/recruiting/oportunidades/{ID_OP}/candidatos-compatibles")
    assert not _llamadas(fake_api, "GET", "/recruiting/config")


@pytest.mark.parametrize("status,mensaje", [(403, "no la tenés asignada"), (404, "no existe")])
def test_una_busqueda_inaccesible_vuelve_al_listado_con_un_aviso(frontend_client, fake_api, status, mensaje):
    _con_item(frontend_client, fake_api)
    fake_api.respond("GET", f"/recruiting/oportunidades/{ID_OP}", {"detail": "x"}, status)

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/recruiting/oportunidades")
    with frontend_client.session_transaction() as sesion:
        assert any(mensaje in texto for _, texto in sesion["_flashes"])


def test_el_id_que_no_es_uuid_responde_404(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)
    assert frontend_client.get("/recruiting/oportunidades/no-es-un-uuid").status_code == 404


def test_editar_lleva_a_la_ficha_en_modo_edicion(frontend_client, fake_api):
    _con_item(frontend_client, fake_api)

    respuesta = frontend_client.get(f"/recruiting/oportunidades/{ID_OP}/editar")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/recruiting/oportunidades/{ID_OP}?edit=true")


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
