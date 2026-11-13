"""Búsquedas de Recruiting (/api/v1/recruiting/oportunidades): permisos por ítem, listado con filtros y paginación,
visibilidad por grupo (EXTERNOS), alta, edición, asignaciones (reclutador, externo, tomar y liberar), candidatos de una
búsqueda (pipeline, Smart Matching, asignar y desvincular) y catálogos de solo lectura. Las reglas son las del
SolicitudService del módulo original (modulo-recluiter); lo propio del Core: permisos por ítem de menú, empresa activa
del JWT y contrato de la API (operation_id, paginación uniforme, errores {"detail": ...})."""

import uuid

import pytest

from backend.modules.recruiting.models import (
    Candidato,
    GestionBusqueda,
    Postulacion,
    RecruitingLider,
    RecruitingPerfilPuesto,
    RecruitingReclutador,
    RecrutingConfig,
    Solicitud,
)
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/oportunidades"
PERMISOS = ["recruiting", "recruiting.oportunidades"]


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def usuario_con_grupo(data_factory, empresa):
    externos = []  # el grupo EXTERNOS tiene nombre único: se crea una vez por prueba

    def crear(nombre_grupo="Recruiting", permisos=PERMISOS, empresa_del_usuario=None):
        destino = empresa_del_usuario or empresa
        usuario = data_factory.usuario()
        if nombre_grupo == "EXTERNOS" and externos:
            grupo = externos[0]
        else:
            grupo = data_factory.grupo(
                nombre=nombre_grupo if nombre_grupo == "EXTERNOS" else f"{nombre_grupo} {uuid.uuid4().hex[:6]}"
            )
            data_factory.permisos(grupo, permisos)
            if nombre_grupo == "EXTERNOS":
                externos.append(grupo)
        data_factory.asignar_empresa(usuario, destino)
        data_factory.asignar_grupo(usuario, grupo, destino)
        return usuario

    return crear


@pytest.fixture
def admin(data_factory, empresa):
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    return usuario


@pytest.fixture
def reclutador(usuario_con_grupo):
    return usuario_con_grupo("Recruiting")


@pytest.fixture
def externo(usuario_con_grupo):
    return usuario_con_grupo("EXTERNOS")


@pytest.fixture
def busqueda(db_session):
    def crear(empresa, *, cliente="Acme", titulo=None, estado="Abierta", tipo="Efectiva", externo=None, **extra):
        guardada = Solicitud(
            empresa_id=empresa.id,
            id_busqueda=f"OP-{uuid.uuid4().hex[:6].upper()}",
            cliente=cliente,
            titulo=titulo or f"Busqueda {uuid.uuid4().hex[:6]}",
            estado=estado,
            tipo=tipo,
            externo_id=externo.id if externo else None,
            **extra,
        )
        db_session.add(guardada)
        db_session.flush()
        return guardada

    return crear


@pytest.fixture
def candidato(db_session):
    def crear(empresa, *, nombre="Ana", apellido="Lopez", creador=None, skills=None):
        guardado = Candidato(
            empresa_id=empresa.id,
            nombre=nombre,
            apellido=apellido,
            email=f"{uuid.uuid4().hex}@example.com",
            estado="Activo",
            creador_id=creador.id if creador else None,
            skills=skills or [],
        )
        db_session.add(guardado)
        db_session.flush()
        return guardado

    return crear


def alta(**campos):
    base = {"cliente": "Acme", "titulo": f"Backend {uuid.uuid4().hex[:6]}"}
    return {**base, **campos}


# --- Permisos -------------------------------------------------------------------------------------------------------


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401


def test_sin_el_modulo_recruiting_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["configuracion"])
    assert client.get(URL, headers=auth_headers(usuario, empresa)).status_code == 403


def test_con_el_modulo_pero_sin_el_item_oportunidades_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["recruiting", "recruiting.candidatos"])
    respuesta = client.get(URL, headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés acceso a 'oportunidades'"


def test_los_catalogos_y_el_resto_de_las_rutas_exigen_el_item_oportunidades(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["recruiting", "recruiting.candidatos"])
    headers = auth_headers(usuario, empresa)
    for ruta in ("lideres", "reclutadores", "config", "externos-disponibles", "oportunidades/permisos"):
        assert client.get(f"/api/v1/recruiting/{ruta}", headers=headers).status_code == 403, ruta
    assert client.get(f"{URL}/{uuid.uuid4()}/candidatos", headers=headers).status_code == 403


def test_el_admin_entra_sin_permisos_de_grupo(client, admin, empresa):
    assert client.get(URL, headers=auth_headers(admin, empresa)).status_code == 200


def test_permisos_del_reclutador_y_del_externo(client, reclutador, externo, empresa):
    interno = client.get(f"{URL}/permisos", headers=auth_headers(reclutador, empresa)).json()
    assert interno == {
        "puede_crear_busquedas": True,
        "puede_eliminar_busquedas": True,
        "puede_ver_lider_tipo_fecha_busqueda": True,
        "puede_ver_smart_matching": True,
        "puede_asignar_candidatos": True,
        "puede_asignar_reclutador": True,
        "puede_administrar_externos": True,
        "es_externo": False,
    }
    limitado = client.get(f"{URL}/permisos", headers=auth_headers(externo, empresa)).json()
    assert limitado.pop("es_externo") is True
    assert not any(limitado.values())


# --- Listado --------------------------------------------------------------------------------------------------------


def test_listado_con_paginacion_uniforme_y_solo_la_empresa_activa(client, admin, empresa, data_factory, busqueda):
    otra = data_factory.empresa()
    for i in range(3):
        busqueda(empresa, titulo=f"Propia {i}")
    busqueda(otra, titulo="De otra empresa")
    cuerpo = client.get(URL, headers=auth_headers(admin, empresa), params={"por_pagina": 2}).json()
    assert set(cuerpo) == {"items", "total", "pagina", "por_pagina", "total_paginas"}
    assert (cuerpo["total"], cuerpo["total_paginas"], len(cuerpo["items"])) == (3, 2, 2)
    todos = client.get(URL, headers=auth_headers(admin, empresa)).json()["items"]
    assert "De otra empresa" not in {o["titulo"] for o in todos}


def test_listado_excluye_bajas_y_trae_el_orden_mas_reciente_primero(client, admin, empresa, busqueda, db_session):
    vieja = busqueda(empresa, titulo="Vieja")
    nueva = busqueda(empresa, titulo="Nueva")
    baja = busqueda(empresa, titulo="Baja", activo=False)
    db_session.flush()
    titulos = [o["titulo"] for o in client.get(URL, headers=auth_headers(admin, empresa)).json()["items"]]
    assert baja.titulo not in titulos
    assert titulos.index(nueva.titulo) < titulos.index(vieja.titulo)


def test_filtros_de_estado_tipo_cliente_y_texto(client, admin, empresa, busqueda):
    busqueda(empresa, titulo="Java abierta", cliente="Globant", estado="Abierta", tipo="Efectiva")
    busqueda(empresa, titulo="Python ganada", cliente="Globant", estado="Ganada", tipo="Efectiva")
    busqueda(
        empresa, titulo="Go potencial", cliente="Mercado", estado="Abierta", tipo="Potencial", lider_nombre="Lucia"
    )
    headers = auth_headers(admin, empresa)

    def titulos(**params):
        return {o["titulo"] for o in client.get(URL, headers=headers, params=params).json()["items"]}

    assert titulos(estado="Ganada") == {"Python ganada"}
    assert titulos(estado="todos") == {"Java abierta", "Python ganada", "Go potencial"}
    assert titulos(tipo="Potencial") == {"Go potencial"}
    assert titulos(tipo="Todas", estado="Abierta") == {"Java abierta", "Go potencial"}
    assert titulos(cliente="Globant", estado="todos") == {"Java abierta", "Python ganada"}
    assert titulos(busqueda="python", estado="todos") == {"Python ganada"}
    assert titulos(busqueda="lucia", estado="todos") == {"Go potencial"}


def test_la_busqueda_por_texto_encuentra_por_id_de_busqueda_y_reclutador(client, admin, empresa, busqueda):
    buscada = busqueda(empresa, titulo="Con reclutador", recruiter_nombre="Marcela Gomez")
    busqueda(empresa, titulo="Otra")
    headers = auth_headers(admin, empresa)
    por_id = client.get(URL, headers=headers, params={"busqueda": buscada.id_busqueda}).json()["items"]
    por_reclutador = client.get(URL, headers=headers, params={"busqueda": "marcela"}).json()["items"]
    assert [o["titulo"] for o in por_id] == [o["titulo"] for o in por_reclutador] == ["Con reclutador"]


def test_el_externo_solo_ve_las_busquedas_que_tiene_asignadas(client, externo, empresa, busqueda):
    mia = busqueda(empresa, titulo="Mia", externo=externo)
    busqueda(empresa, titulo="Ajena")
    items = client.get(URL, headers=auth_headers(externo, empresa)).json()["items"]
    assert [o["titulo"] for o in items] == ["Mia"]
    assert items[0]["externo_id"] == str(externo.id)
    assert items[0]["id"] == str(mia.id)


def test_el_externo_no_busca_por_lider(client, externo, empresa, busqueda):
    busqueda(empresa, titulo="Mia", externo=externo, lider_nombre="Zulema")
    headers = auth_headers(externo, empresa)
    assert client.get(URL, headers=headers, params={"busqueda": "zulema"}).json()["total"] == 0


# --- Alta -----------------------------------------------------------------------------------------------------------


def test_alta_con_valores_por_defecto_y_codigo_generado(client, admin, empresa):
    respuesta = client.post(URL, headers=auth_headers(admin, empresa), json=alta(titulo="Dev Python"))
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "Abierta"
    assert cuerpo["tipo"] == "Efectiva"
    assert cuerpo["seniority"] == "Senior"
    assert cuerpo["modalidad"] == "Remoto"
    assert cuerpo["prioridad"] == "Alta"
    assert cuerpo["vacantes"] == 1
    assert cuerpo["id_busqueda"].startswith("OP-")
    assert cuerpo["empresa_id"] == str(empresa.id)
    assert cuerpo["creador_id"] == str(admin.id)
    assert cuerpo["recruiter_nombre"] is None and cuerpo["fecha_asignacion"] is None
    assert cuerpo["dias_abierta"] == 0


def test_alta_guarda_skills_habilidades_y_lista_desde_texto(client, admin, empresa):
    cuerpo = client.post(
        URL,
        headers=auth_headers(admin, empresa),
        json=alta(skills=["Python", " SQL ", ""], habilidades="Liderazgo, Comunicacion", skills_deseadas=["Docker"]),
    ).json()
    assert cuerpo["skills"] == ["Python", "SQL"]
    assert cuerpo["habilidades"] == ["Liderazgo", "Comunicacion"]
    assert cuerpo["skills_deseadas"] == ["Docker"]


def test_el_reclutador_que_crea_queda_como_responsable_con_fecha_de_asignacion(client, reclutador, empresa):
    cuerpo = client.post(URL, headers=auth_headers(reclutador, empresa), json=alta()).json()
    assert cuerpo["recruiter_id"] == str(reclutador.id)
    assert cuerpo["recruiter_nombre"].startswith(reclutador.nombre)
    assert cuerpo["fecha_asignacion"] is not None


def test_la_fecha_de_asignacion_del_cliente_se_ignora(client, admin, empresa):
    cuerpo = client.post(
        URL, headers=auth_headers(admin, empresa), json=alta(fecha_asignacion="2001-01-01T00:00:00")
    ).json()
    assert cuerpo["fecha_asignacion"] is None


def test_alta_duplicada_por_cliente_y_titulo_responde_400(client, admin, empresa):
    headers = auth_headers(admin, empresa)
    assert client.post(URL, headers=headers, json=alta(cliente="Acme", titulo="Dev")).status_code == 201
    repetida = client.post(URL, headers=headers, json=alta(cliente=" acme ", titulo="DEV "))
    assert repetida.status_code == 400
    assert repetida.json()["detail"] == "Ya existe una búsqueda con este título para el cliente seleccionado"


def test_alta_con_estado_invalido_responde_400(client, admin, empresa):
    respuesta = client.post(URL, headers=auth_headers(admin, empresa), json=alta(estado="Pausada"))
    assert respuesta.status_code == 400
    assert "Pausada" in respuesta.json()["detail"]


def test_alta_valida_el_puesto_contra_el_catalogo_y_guarda_el_nombre_canonico(client, admin, empresa, db_session):
    db_session.add(RecruitingPerfilPuesto(nombre="Desarrollador Python", activo=True))
    db_session.add(RecruitingPerfilPuesto(nombre="Perfil Inactivo", activo=False))
    db_session.flush()
    headers = auth_headers(admin, empresa)
    ok = client.post(URL, headers=headers, json=alta(puesto="desarrollador   python"))
    assert ok.status_code == 201 and ok.json()["puesto"] == "Desarrollador Python"
    assert client.post(URL, headers=headers, json=alta(puesto="Inventado")).status_code == 400
    assert client.post(URL, headers=headers, json=alta(puesto="Perfil Inactivo")).status_code == 400


def test_alta_con_tipo_invalido_o_datos_faltantes_responde_422(client, admin, empresa):
    headers = auth_headers(admin, empresa)
    assert client.post(URL, headers=headers, json=alta(tipo="Rara")).status_code == 422
    assert client.post(URL, headers=headers, json={"titulo": "Solo titulo"}).status_code == 422
    assert client.post(URL, headers=headers, json=alta(vacantes=0)).status_code == 422


def test_tipo_se_normaliza_sin_distinguir_mayusculas(client, admin, empresa):
    assert (
        client.post(URL, headers=auth_headers(admin, empresa), json=alta(tipo="potencial")).json()["tipo"]
        == "Potencial"
    )


def test_el_externo_no_crea_busquedas(client, externo, empresa):
    respuesta = client.post(URL, headers=auth_headers(externo, empresa), json=alta())
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Los usuarios del grupo EXTERNOS no pueden crear búsquedas"


# --- Ficha ----------------------------------------------------------------------------------------------------------


def test_ficha_de_una_busqueda_con_su_externo(client, admin, empresa, busqueda, externo):
    guardada = busqueda(empresa, externo=externo)
    cuerpo = client.get(f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa)).json()
    assert cuerpo["id"] == str(guardada.id)
    assert cuerpo["externo_email"] == externo.email


def test_una_busqueda_de_otra_empresa_responde_404(client, admin, empresa, data_factory, busqueda):
    ajena = busqueda(data_factory.empresa())
    assert client.get(f"{URL}/{ajena.id}", headers=auth_headers(admin, empresa)).status_code == 404
    assert client.put(f"{URL}/{ajena.id}", headers=auth_headers(admin, empresa), json={"rango": "x"}).status_code == 404


def test_id_mal_formado_responde_422_y_no_500(client, admin, empresa):
    assert client.get(f"{URL}/no-es-un-uuid", headers=auth_headers(admin, empresa)).status_code == 422


def test_el_externo_solo_abre_una_busqueda_asignada_a_el(client, externo, empresa, busqueda):
    asignada = busqueda(empresa, externo=externo)
    ajena = busqueda(empresa)
    headers = auth_headers(externo, empresa)
    assert client.get(f"{URL}/{asignada.id}", headers=headers).status_code == 200
    respuesta = client.get(f"{URL}/{ajena.id}", headers=headers)
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés acceso a esta búsqueda: no la tenés asignada."


def test_q_activos_sale_de_los_candidatos_vigentes_del_pipeline(
    client, admin, empresa, busqueda, candidato, db_session
):
    guardada = busqueda(empresa)
    for estado in ("En proceso", "Avanzó", "Descartado"):
        db_session.add(
            GestionBusqueda(
                empresa_id=empresa.id, oportunidad_id=guardada.id, candidato_id=candidato(empresa).id, estado=estado
            )
        )
    db_session.flush()
    cuerpo = client.get(f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa)).json()
    assert cuerpo["q_activos"] == 2


# --- Edición --------------------------------------------------------------------------------------------------------


def test_edicion_parcial_solo_cambia_lo_enviado(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, titulo="Original", rango="1000", modalidad="Remoto")
    respuesta = client.put(
        f"{URL}/{guardada.id}",
        headers=auth_headers(admin, empresa),
        json={"rango": "2000", "estado": "Suspendida", "skills": ["Go"], "descripcion": "  Texto  "},
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert (cuerpo["titulo"], cuerpo["modalidad"]) == ("Original", "Remoto")
    assert (cuerpo["rango"], cuerpo["estado"], cuerpo["skills"], cuerpo["descripcion"]) == (
        "2000",
        "Suspendida",
        ["Go"],
        "Texto",
    )


def test_un_tipo_o_vacantes_vacios_en_la_edicion_no_cambian_nada(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, tipo="Potencial", vacantes=3)
    respuesta = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa), json={"tipo": " ", "vacantes": None}
    )
    assert respuesta.status_code == 200
    assert (respuesta.json()["tipo"], respuesta.json()["vacantes"]) == ("Potencial", 3)


def test_la_descripcion_vacia_la_borra(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, descripcion="Algo")
    cuerpo = client.put(f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa), json={"descripcion": " "}).json()
    assert cuerpo["descripcion"] is None


def test_la_fecha_de_creacion_no_se_modifica(client, admin, empresa, busqueda):
    guardada = busqueda(empresa)
    original = client.get(f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa)).json()["fecha_creacion"]
    cuerpo = client.put(
        f"{URL}/{guardada.id}",
        headers=auth_headers(admin, empresa),
        json={"fecha_creacion": "2001-01-01", "rango": "x"},
    ).json()
    assert cuerpo["fecha_creacion"] == original


def test_una_busqueda_ganada_no_admite_cambios(client, admin, empresa, busqueda):
    ganada = busqueda(empresa, estado="Ganada")
    respuesta = client.put(f"{URL}/{ganada.id}", headers=auth_headers(admin, empresa), json={"rango": "x"})
    assert respuesta.status_code == 409
    assert "Ganada" in respuesta.json()["detail"]


def test_editar_conserva_un_puesto_historico_que_ya_no_esta_en_el_catalogo(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, puesto="Perfil Historico")
    respuesta = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa), json={"puesto": "perfil historico", "rango": "x"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["puesto"] == "Perfil Historico"


def test_cambiar_el_reclutador_por_edicion_exige_permiso_y_reinicia_la_fecha(
    client, admin, empresa, busqueda, usuario_con_grupo
):
    guardada = busqueda(empresa, recruiter_nombre="Ana")
    cuerpo = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa), json={"recruiter_nombre": "Beatriz"}
    ).json()
    assert cuerpo["recruiter_nombre"] == "Beatriz" and cuerpo["fecha_asignacion"] is not None

    lider = usuario_con_grupo("Lider")
    respuesta = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(lider, empresa), json={"recruiter_nombre": "Carla"}
    )
    assert respuesta.status_code == 403


def test_editar_sin_cambiar_el_reclutador_no_toca_la_asignacion(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, recruiter_nombre="Ana")
    cuerpo = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(admin, empresa), json={"recruiter_nombre": " ana ", "rango": "x"}
    ).json()
    assert cuerpo["recruiter_nombre"] == "Ana" and cuerpo["fecha_asignacion"] is None


def test_el_externo_no_cancela_una_busqueda_pero_si_edita_otros_datos(client, externo, empresa, busqueda):
    asignada = busqueda(empresa, externo=externo)
    headers = auth_headers(externo, empresa)
    cancelar = client.put(f"{URL}/{asignada.id}", headers=headers, json={"estado": "Cancelada"})
    assert cancelar.status_code == 403
    assert client.put(f"{URL}/{asignada.id}", headers=headers, json={"rango": "x"}).status_code == 200


def test_cancelar_cambia_el_estado_y_no_elimina(client, reclutador, empresa, busqueda, db_session):
    guardada = busqueda(empresa)
    respuesta = client.put(
        f"{URL}/{guardada.id}", headers=auth_headers(reclutador, empresa), json={"estado": "Cancelada"}
    )
    assert respuesta.status_code == 200 and respuesta.json()["estado"] == "Cancelada"
    db_session.refresh(guardada)
    assert guardada.deleted_at is None


# --- Asignaciones ---------------------------------------------------------------------------------------------------


def test_el_reclutador_toma_y_libera_su_busqueda(client, reclutador, empresa, busqueda):
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    tomada = client.post(f"{URL}/{guardada.id}/asignar", headers=headers).json()
    assert tomada["recruiter_id"] == str(reclutador.id) and tomada["fecha_asignacion"] is not None
    liberada = client.post(f"{URL}/{guardada.id}/desasignar", headers=headers).json()
    assert liberada["recruiter_id"] is None and liberada["recruiter_nombre"] is None
    assert liberada["fecha_asignacion"] is None


def test_volver_a_tomar_la_misma_busqueda_no_reinicia_la_fecha(client, reclutador, empresa, busqueda):
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    primera = client.post(f"{URL}/{guardada.id}/asignar", headers=headers).json()["fecha_asignacion"]
    segunda = client.post(f"{URL}/{guardada.id}/asignar", headers=headers).json()["fecha_asignacion"]
    assert primera == segunda


def test_no_se_toma_una_busqueda_asignada_a_otro_reclutador(client, usuario_con_grupo, empresa, busqueda):
    uno, otro = usuario_con_grupo("Recruiting"), usuario_con_grupo("Recruiting")
    guardada = busqueda(empresa)
    assert client.post(f"{URL}/{guardada.id}/asignar", headers=auth_headers(uno, empresa)).status_code == 200
    respuesta = client.post(f"{URL}/{guardada.id}/asignar", headers=auth_headers(otro, empresa))
    assert respuesta.status_code == 400
    assert client.post(f"{URL}/{guardada.id}/desasignar", headers=auth_headers(otro, empresa)).status_code == 403


def test_solo_un_reclutador_puede_tomar_una_busqueda(client, admin, empresa, busqueda):
    guardada = busqueda(empresa)
    respuesta = client.post(f"{URL}/{guardada.id}/asignar", headers=auth_headers(admin, empresa))
    assert respuesta.status_code == 403


def test_el_admin_libera_la_busqueda_de_cualquiera(client, admin, empresa, busqueda):
    guardada = busqueda(empresa, recruiter_nombre="Ana")
    cuerpo = client.post(f"{URL}/{guardada.id}/desasignar", headers=auth_headers(admin, empresa)).json()
    assert cuerpo["recruiter_nombre"] is None


def test_asignar_reclutador_del_catalogo(client, reclutador, empresa, busqueda, db_session):
    db_session.add(RecruitingReclutador(nombre="Marcela Gomez", activo=True))
    db_session.add(RecruitingReclutador(nombre="Inactivo Gomez", activo=False))
    db_session.flush()
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    ok = client.post(f"{URL}/{guardada.id}/reclutador", headers=headers, json={"recruiter_nombre": "marcela  gomez"})
    assert ok.status_code == 200
    assert ok.json()["recruiter_nombre"] == "Marcela Gomez" and ok.json()["fecha_asignacion"] is not None
    inactivo = client.post(
        f"{URL}/{guardada.id}/reclutador", headers=headers, json={"recruiter_nombre": "Inactivo Gomez"}
    )
    assert inactivo.status_code == 400
    assert (
        client.post(f"{URL}/{guardada.id}/reclutador", headers=headers, json={"recruiter_nombre": ""}).status_code
        == 422
    )


def test_reasignar_el_mismo_reclutador_no_cambia_la_fecha(client, reclutador, empresa, busqueda, db_session):
    db_session.add(RecruitingReclutador(nombre="Marcela Gomez", activo=True))
    db_session.flush()
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    cuerpo = {"recruiter_nombre": "Marcela Gomez"}
    primera = client.post(f"{URL}/{guardada.id}/reclutador", headers=headers, json=cuerpo).json()["fecha_asignacion"]
    segunda = client.post(f"{URL}/{guardada.id}/reclutador", headers=headers, json=cuerpo).json()["fecha_asignacion"]
    assert primera == segunda


def test_el_externo_no_asigna_reclutadores(client, externo, empresa, busqueda, db_session):
    db_session.add(RecruitingReclutador(nombre="Marcela Gomez", activo=True))
    db_session.flush()
    asignada = busqueda(empresa, externo=externo)
    respuesta = client.post(
        f"{URL}/{asignada.id}/reclutador",
        headers=auth_headers(externo, empresa),
        json={"recruiter_nombre": "Marcela Gomez"},
    )
    assert respuesta.status_code == 403


def test_asignar_reemplazar_y_quitar_el_usuario_externo(client, reclutador, empresa, busqueda, usuario_con_grupo):
    uno, otro = usuario_con_grupo("EXTERNOS"), usuario_con_grupo("EXTERNOS")
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    asignado = client.put(f"{URL}/{guardada.id}/externo", headers=headers, json={"externo_id": str(uno.id)})
    assert asignado.status_code == 200 and asignado.json()["externo_id"] == str(uno.id)
    reemplazado = client.put(f"{URL}/{guardada.id}/externo", headers=headers, json={"externo_id": str(otro.id)}).json()
    assert reemplazado["externo_id"] == str(otro.id)
    quitado = client.delete(f"{URL}/{guardada.id}/externo", headers=headers)
    assert quitado.status_code == 200 and quitado.json()["externo_id"] is None


def test_solo_se_asigna_a_usuarios_activos_del_grupo_externos(
    client, reclutador, empresa, busqueda, usuario_con_grupo, data_factory, db_session
):
    guardada = busqueda(empresa)
    headers = auth_headers(reclutador, empresa)
    no_externo = usuario_con_grupo("Recruiting")
    assert (
        client.put(f"{URL}/{guardada.id}/externo", headers=headers, json={"externo_id": str(no_externo.id)}).status_code
        == 400
    )
    inactivo = usuario_con_grupo("EXTERNOS")
    inactivo.activo = False
    db_session.flush()
    assert (
        client.put(f"{URL}/{guardada.id}/externo", headers=headers, json={"externo_id": str(inactivo.id)}).status_code
        == 400
    )
    assert (
        client.put(f"{URL}/{guardada.id}/externo", headers=headers, json={"externo_id": "no-uuid"}).status_code == 422
    )


def test_un_externo_de_otra_empresa_no_se_puede_asignar(
    client, reclutador, empresa, busqueda, data_factory, usuario_con_grupo
):
    otra = data_factory.empresa()
    ajeno = usuario_con_grupo("EXTERNOS", empresa_del_usuario=otra)
    guardada = busqueda(empresa)
    respuesta = client.put(
        f"{URL}/{guardada.id}/externo", headers=auth_headers(reclutador, empresa), json={"externo_id": str(ajeno.id)}
    )
    assert respuesta.status_code == 400


def test_administrar_externos_es_de_admin_y_grupos_de_recruiting(client, empresa, busqueda, usuario_con_grupo):
    guardada = busqueda(empresa)
    colaborador = usuario_con_grupo("Colaboradores")
    externo = usuario_con_grupo("EXTERNOS")
    cuerpo = {"externo_id": str(externo.id)}
    assert (
        client.put(f"{URL}/{guardada.id}/externo", headers=auth_headers(colaborador, empresa), json=cuerpo).status_code
        == 403
    )
    assert client.delete(f"{URL}/{guardada.id}/externo", headers=auth_headers(colaborador, empresa)).status_code == 403
    assert (
        client.get("/api/v1/recruiting/externos-disponibles", headers=auth_headers(colaborador, empresa)).status_code
        == 403
    )


def test_externos_disponibles_lista_los_habilitados_de_la_empresa(
    client, reclutador, empresa, usuario_con_grupo, data_factory
):
    uno = usuario_con_grupo("EXTERNOS")
    usuario_con_grupo("EXTERNOS", empresa_del_usuario=data_factory.empresa())
    usuario_con_grupo("Recruiting")
    items = client.get("/api/v1/recruiting/externos-disponibles", headers=auth_headers(reclutador, empresa)).json()
    assert [u["id"] for u in items] == [str(uno.id)]
    assert set(items[0]) == {"id", "nombre", "email"}


def test_una_busqueda_ganada_no_admite_asignaciones(client, reclutador, empresa, busqueda, usuario_con_grupo):
    ganada = busqueda(empresa, estado="Ganada")
    externo = usuario_con_grupo("EXTERNOS")
    headers = auth_headers(reclutador, empresa)
    assert client.post(f"{URL}/{ganada.id}/asignar", headers=headers).status_code == 409
    assert client.post(f"{URL}/{ganada.id}/desasignar", headers=headers).status_code == 409
    assert (
        client.put(f"{URL}/{ganada.id}/externo", headers=headers, json={"externo_id": str(externo.id)}).status_code
        == 409
    )


# --- Candidatos de la búsqueda --------------------------------------------------------------------------------------


def test_asignar_un_candidato_crea_postulacion_pipeline_y_actualiza_los_contadores(
    client, reclutador, empresa, busqueda, candidato, db_session
):
    guardada = busqueda(empresa)
    elegido = candidato(empresa, creador=reclutador)
    respuesta = client.post(
        f"{URL}/{guardada.id}/candidatos",
        headers=auth_headers(reclutador, empresa),
        json={"candidato_id": str(elegido.id)},
    )
    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert (cuerpo["candidato_id"], cuerpo["estado"], cuerpo["etapa"]) == (
        str(elegido.id),
        "En proceso",
        "Coordinando entrevista",
    )
    gestion = db_session.query(GestionBusqueda).filter_by(oportunidad_id=guardada.id, candidato_id=elegido.id).one()
    assert gestion.etapa_actual == "Candidato" and gestion.activo
    db_session.refresh(guardada)
    assert (guardada.candidatos_pipeline, guardada.coordinando_entrevista, guardada.q_activos) == (1, 1, 1)


def test_asignar_dos_veces_el_mismo_candidato_responde_400(client, reclutador, empresa, busqueda, candidato):
    guardada = busqueda(empresa)
    elegido = candidato(empresa, creador=reclutador)
    headers = auth_headers(reclutador, empresa)
    cuerpo = {"candidato_id": str(elegido.id)}
    assert client.post(f"{URL}/{guardada.id}/candidatos", headers=headers, json=cuerpo).status_code == 201
    repetido = client.post(f"{URL}/{guardada.id}/candidatos", headers=headers, json=cuerpo)
    assert repetido.status_code == 400
    assert "ya está asignado" in repetido.json()["detail"]


def test_solo_se_asignan_candidatos_a_busquedas_abiertas(client, reclutador, empresa, busqueda, candidato):
    elegido = candidato(empresa, creador=reclutador)
    headers = auth_headers(reclutador, empresa)
    for estado in ("Suspendida", "Cancelada", "Pre-ingreso", "Ganada"):
        guardada = busqueda(empresa, estado=estado)
        respuesta = client.post(
            f"{URL}/{guardada.id}/candidatos", headers=headers, json={"candidato_id": str(elegido.id)}
        )
        assert respuesta.status_code == 400, estado
        assert estado in respuesta.json()["detail"]


def test_no_se_asigna_un_candidato_de_otra_empresa(client, reclutador, empresa, busqueda, candidato, data_factory):
    guardada = busqueda(empresa)
    ajeno = candidato(data_factory.empresa())
    respuesta = client.post(
        f"{URL}/{guardada.id}/candidatos",
        headers=auth_headers(reclutador, empresa),
        json={"candidato_id": str(ajeno.id)},
    )
    assert respuesta.status_code == 404


def test_el_externo_no_asigna_candidatos_con_este_endpoint(client, externo, empresa, busqueda, candidato):
    asignada = busqueda(empresa, externo=externo)
    propio = candidato(empresa, creador=externo)
    respuesta = client.post(
        f"{URL}/{asignada.id}/candidatos", headers=auth_headers(externo, empresa), json={"candidato_id": str(propio.id)}
    )
    assert respuesta.status_code == 403


def test_el_pipeline_de_la_busqueda_lista_sus_candidatos(client, reclutador, empresa, busqueda, candidato):
    guardada = busqueda(empresa)
    elegido = candidato(empresa, nombre="Beto", apellido="Rios", creador=reclutador)
    headers = auth_headers(reclutador, empresa)
    client.post(f"{URL}/{guardada.id}/candidatos", headers=headers, json={"candidato_id": str(elegido.id)})
    items = client.get(f"{URL}/{guardada.id}/candidatos", headers=headers).json()
    assert len(items) == 1
    assert (items[0]["candidato_id"], items[0]["nombre"], items[0]["etapa_actual"], items[0]["es_anonimo"]) == (
        str(elegido.id),
        "Beto Rios",
        "Candidato",
        False,
    )


def test_el_externo_ve_anonimos_los_candidatos_que_no_presento(
    client, reclutador, externo, empresa, busqueda, candidato, db_session
):
    asignada = busqueda(empresa, externo=externo)
    ajeno = candidato(empresa, nombre="Secreto", apellido="Persona", creador=reclutador)
    propio = candidato(empresa, nombre="Propio", apellido="Externo", creador=externo)
    for c in (ajeno, propio):
        db_session.add(GestionBusqueda(empresa_id=empresa.id, oportunidad_id=asignada.id, candidato_id=c.id))
    db_session.flush()
    items = client.get(f"{URL}/{asignada.id}/candidatos", headers=auth_headers(externo, empresa)).json()
    por_id = {i["candidato_id"]: i for i in items}
    assert por_id[str(propio.id)]["nombre"] == "Propio Externo" and not por_id[str(propio.id)]["es_anonimo"]
    anonimo = por_id[str(ajeno.id)]
    assert anonimo["es_anonimo"] and "Secreto" not in anonimo["nombre"] and anonimo["email"] == "Oculto"
    assert anonimo["telefono"] is None and anonimo["cv_url"] is None


def test_los_candidatos_de_una_busqueda_ajena_o_de_otra_empresa_no_se_listan(
    client, externo, admin, empresa, busqueda, data_factory
):
    ajena = busqueda(empresa)
    assert client.get(f"{URL}/{ajena.id}/candidatos", headers=auth_headers(externo, empresa)).status_code == 403
    de_otra_empresa = busqueda(data_factory.empresa())
    assert client.get(f"{URL}/{de_otra_empresa.id}/candidatos", headers=auth_headers(admin, empresa)).status_code == 404


def test_smart_matching_ordena_por_coincidencia_y_excluye_asignados_y_sin_coincidencias(
    client, reclutador, empresa, busqueda, candidato
):
    guardada = busqueda(empresa, skills=["Python", "SQL"], habilidades=["Liderazgo"])
    total = candidato(empresa, nombre="Total", apellido="A", creador=reclutador, skills=["python", "sql"])
    parcial = candidato(empresa, nombre="Parcial", apellido="B", creador=reclutador, skills=["Python 3"])
    candidato(empresa, nombre="Ninguno", apellido="C", creador=reclutador, skills=["Cobol"])
    asignado = candidato(empresa, nombre="Asignado", apellido="D", creador=reclutador, skills=["Python", "SQL"])
    headers = auth_headers(reclutador, empresa)
    client.post(f"{URL}/{guardada.id}/candidatos", headers=headers, json={"candidato_id": str(asignado.id)})

    items = client.get(f"{URL}/{guardada.id}/candidatos-compatibles", headers=headers).json()
    assert [i["id"] for i in items] == [str(total.id), str(parcial.id)]
    assert (items[0]["porcentaje_match"], items[0]["match_porcentaje"]) == (66, 66)
    assert items[0]["skills_coincidentes"] == ["python", "sql"]
    assert items[1]["porcentaje_match"] == 33


def test_smart_matching_filtra_por_texto_y_sin_requisitos_sugiere_a_todos(
    client, reclutador, empresa, busqueda, candidato
):
    guardada = busqueda(empresa)
    candidato(empresa, nombre="Julia", apellido="Mendez", creador=reclutador)
    candidato(empresa, nombre="Pedro", apellido="Suarez", creador=reclutador)
    headers = auth_headers(reclutador, empresa)
    todos = client.get(f"{URL}/{guardada.id}/candidatos-compatibles", headers=headers).json()
    assert len(todos) == 2 and all(i["porcentaje_match"] == 100 for i in todos)
    filtrados = client.get(
        f"{URL}/{guardada.id}/candidatos-compatibles", headers=headers, params={"q": "mendez"}
    ).json()
    assert [i["nombre"] for i in filtrados] == ["Julia"]


def test_smart_matching_respeta_la_visibilidad_de_candidatos_y_la_empresa(
    client, usuario_con_grupo, empresa, busqueda, candidato, data_factory
):
    colaborador = usuario_con_grupo("Colaboradores")
    guardada = busqueda(empresa)
    propio = candidato(empresa, nombre="Propio", creador=colaborador)
    candidato(empresa, nombre="DeOtro", creador=usuario_con_grupo("Recruiting"))
    candidato(data_factory.empresa(), nombre="OtraEmpresa")
    items = client.get(f"{URL}/{guardada.id}/candidatos-compatibles", headers=auth_headers(colaborador, empresa)).json()
    assert [i["id"] for i in items] == [str(propio.id)]


def test_smart_matching_no_esta_disponible_para_el_externo(client, externo, empresa, busqueda):
    asignada = busqueda(empresa, externo=externo)
    respuesta = client.get(f"{URL}/{asignada.id}/candidatos-compatibles", headers=auth_headers(externo, empresa))
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "Los usuarios del grupo EXTERNOS no tienen acceso a Smart Matching"


def test_desvincular_quita_al_candidato_de_la_busqueda_y_conserva_su_ficha(
    client, reclutador, empresa, busqueda, candidato, db_session
):
    guardada = busqueda(empresa)
    elegido = candidato(empresa, creador=reclutador)
    headers = auth_headers(reclutador, empresa)
    client.post(f"{URL}/{guardada.id}/candidatos", headers=headers, json={"candidato_id": str(elegido.id)})

    respuesta = client.delete(f"{URL}/{guardada.id}/candidatos/{elegido.id}", headers=headers)
    assert respuesta.status_code == 200
    assert respuesta.json()["candidato_id"] == str(elegido.id) and respuesta.json()["ok"] is True
    db_session.expire_all()
    assert db_session.get(Candidato, elegido.id).deleted_at is None
    assert db_session.query(Postulacion).filter_by(solicitud_id=guardada.id, deleted_at=None).count() == 0
    assert client.get(f"{URL}/{guardada.id}/candidatos", headers=headers).json() == []
    assert (guardada.candidatos_pipeline, guardada.q_activos) == (0, 0)
    # Vuelve a poder asignarse
    assert (
        client.post(
            f"{URL}/{guardada.id}/candidatos", headers=headers, json={"candidato_id": str(elegido.id)}
        ).status_code
        == 201
    )


def test_desvincular_un_candidato_no_asignado_responde_404(client, reclutador, empresa, busqueda, candidato):
    guardada = busqueda(empresa)
    suelto = candidato(empresa, creador=reclutador)
    respuesta = client.delete(f"{URL}/{guardada.id}/candidatos/{suelto.id}", headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 404


def test_desvincular_de_una_busqueda_ganada_responde_409(client, reclutador, empresa, busqueda, candidato):
    ganada = busqueda(empresa, estado="Ganada")
    elegido = candidato(empresa, creador=reclutador)
    respuesta = client.delete(f"{URL}/{ganada.id}/candidatos/{elegido.id}", headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 409


# --- Catálogos ------------------------------------------------------------------------------------------------------


def test_lideres_y_reclutadores_devuelven_solo_los_activos_ordenados(client, reclutador, empresa, db_session):
    db_session.add_all(
        [
            RecruitingLider(nombre="Zoe Lider", activo=True),
            RecruitingLider(nombre="Ana Lider", activo=True),
            RecruitingLider(nombre="Baja Lider", activo=False),
            RecruitingReclutador(nombre="Mario Recluta", activo=True),
            RecruitingReclutador(nombre="Baja Recluta", activo=False),
        ]
    )
    db_session.flush()
    headers = auth_headers(reclutador, empresa)
    lideres = client.get("/api/v1/recruiting/lideres", headers=headers).json()
    assert [p["nombre"] for p in lideres] == ["Ana Lider", "Zoe Lider"]
    assert set(lideres[0]) == {"id", "nombre", "activo"}
    reclutadores = client.get("/api/v1/recruiting/reclutadores", headers=headers).json()
    assert [p["nombre"] for p in reclutadores] == ["Mario Recluta"]


def test_config_devuelve_50_por_defecto_y_el_umbral_de_la_empresa(
    client, reclutador, empresa, db_session, data_factory
):
    headers = auth_headers(reclutador, empresa)
    assert client.get("/api/v1/recruiting/config", headers=headers).json() == {"match_minimo_porcentaje": 50}
    db_session.add(RecrutingConfig(empresa_id=empresa.id, match_minimo_porcentaje=70))
    db_session.add(RecrutingConfig(empresa_id=data_factory.empresa().id, match_minimo_porcentaje=10))
    db_session.flush()
    assert client.get("/api/v1/recruiting/config", headers=headers).json() == {"match_minimo_porcentaje": 70}
