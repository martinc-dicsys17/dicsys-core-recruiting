"""Candidatos de Recruiting (/api/v1/recruiting/candidatos): permisos, listado con filtros y paginación, visibilidad por
grupo, alta, ficha, edición, baja, carga de CV (individual y masiva) y catálogos de solo lectura. Las reglas son las del
CandidatoService del módulo original (modulo-recluiter); lo propio del Core: permisos por ítem de menú, empresa activa
del JWT y contrato de la API (operation_id, paginación uniforme, errores {"detail": ...})."""

import asyncio
import io
import uuid
import zipfile
from datetime import datetime

import pymupdf
import pytest

from backend.modules.recruiting.models import Candidato, Ciudad, Provincia, RecruitingSkill
from backend.modules.recruiting.services import CandidatoService
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/candidatos"
PERMISOS = ["recruiting", "recruiting.candidatos"]


def pdf_de_cv(email: str, nombre: str = "Juan Perez") -> bytes:
    """Un PDF con texto digital: nombre, puesto, email, teléfono, ubicación y skills."""
    documento = pymupdf.open()
    pagina = documento.new_page()
    texto = f"{nombre}\nBackend Developer\n{email}\n+54 351 1234567\nCordoba, Argentina\nExperiencia con Python y SQL"
    pagina.insert_text((72, 72), texto, fontsize=12)
    contenido = documento.tobytes()
    documento.close()
    return contenido


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def usuario_con_grupo(data_factory, empresa):
    """Un usuario de la empresa en un grupo con el nombre dado y los permisos indicados."""

    def crear(nombre_grupo="Recruiting", permisos=PERMISOS, empresa_del_usuario=None):
        destino = empresa_del_usuario or empresa
        usuario = data_factory.usuario()
        grupo = data_factory.grupo(
            nombre=nombre_grupo if nombre_grupo == "EXTERNOS" else f"{nombre_grupo} {uuid.uuid4().hex[:6]}"
        )
        data_factory.asignar_empresa(usuario, destino)
        data_factory.asignar_grupo(usuario, grupo, destino)
        data_factory.permisos(grupo, permisos)
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
def candidato(db_session):
    def crear(empresa, *, nombre="Ana", apellido="Lopez", creador=None, estado="Activo", borrado=False, **extra):
        guardado = Candidato(
            empresa_id=empresa.id,
            nombre=nombre,
            apellido=apellido,
            email=f"{uuid.uuid4().hex}@example.com",
            estado=estado,
            creador_id=creador.id if creador else None,
            activo=not borrado,
            deleted_at=datetime(2026, 1, 1) if borrado else None,
            **extra,
        )
        db_session.add(guardado)
        db_session.flush()
        return guardado

    return crear


def alta(**campos):
    base = {"nombre": "Juan", "apellido": "Perez", "email": f"{uuid.uuid4().hex}@example.com"}
    return {**base, **campos}


# --- Permisos -------------------------------------------------------------------------------------------------------


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401


def test_sin_el_modulo_recruiting_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["configuracion"])
    assert client.get(URL, headers=auth_headers(usuario, empresa)).status_code == 403


def test_con_el_modulo_pero_sin_el_item_candidatos_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["recruiting", "recruiting.dashboard"])
    respuesta = client.get(URL, headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés acceso a 'candidatos'"


def test_los_catalogos_tambien_exigen_el_item_candidatos(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["recruiting", "recruiting.dashboard"])
    for ruta in ("skills", "habilidades", "niveles-seniority", "provincias", "ciudades", "candidatos/perfiles-puesto"):
        assert client.get(f"/api/v1/recruiting/{ruta}", headers=auth_headers(usuario, empresa)).status_code == 403, ruta


def test_el_admin_entra_sin_permisos_de_grupo(client, admin, empresa):
    assert client.get(URL, headers=auth_headers(admin, empresa)).status_code == 200


# --- Listado --------------------------------------------------------------------------------------------------------


def test_listado_con_paginacion_uniforme_y_solo_la_empresa_activa(client, admin, empresa, data_factory, candidato):
    otra = data_factory.empresa()
    for i in range(3):
        candidato(empresa, nombre=f"Nombre{i}")
    candidato(otra, nombre="DeOtraEmpresa")
    candidato(empresa, nombre="Baja", borrado=True)

    respuesta = client.get(URL, params={"por_pagina": 2}, headers=auth_headers(admin, empresa))
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert set(datos) == {"items", "total", "pagina", "por_pagina", "total_paginas"}
    assert (datos["total"], datos["por_pagina"], datos["total_paginas"], len(datos["items"])) == (3, 2, 2, 2)
    nombres = {c["nombre"] for c in client.get(URL, headers=auth_headers(admin, empresa)).json()["items"]}
    assert nombres == {"Nombre0", "Nombre1", "Nombre2"}


def test_listado_rechaza_por_pagina_fuera_de_rango(client, admin, empresa):
    assert client.get(URL, params={"por_pagina": 101}, headers=auth_headers(admin, empresa)).status_code == 422


def test_el_listado_filtra_por_texto_sin_distinguir_tildes_ni_mayusculas(client, admin, empresa, candidato):
    candidato(empresa, nombre="José", apellido="Gómez")
    candidato(empresa, nombre="Marta", apellido="Díaz")
    respuesta = client.get(URL, params={"busqueda": "jose gomez"}, headers=auth_headers(admin, empresa))
    assert [c["nombre"] for c in respuesta.json()["items"]] == ["José"]


def test_el_listado_filtra_por_estado_seniority_y_puesto(client, admin, empresa, candidato):
    candidato(empresa, nombre="A", estado="Rechazado", seniority="Senior", headline="QA Tester")
    candidato(empresa, nombre="B", estado="Activo", seniority="Junior", headline="Backend Developer")
    cabeceras = auth_headers(admin, empresa)
    por_estado = client.get(URL, params={"estado": "Rechazado"}, headers=cabeceras).json()["items"]
    assert [c["nombre"] for c in por_estado] == ["A"]
    por_seniority = client.get(URL, params={"seniority": "junior"}, headers=cabeceras).json()["items"]
    assert [c["nombre"] for c in por_seniority] == ["B"]
    por_puesto = client.get(URL, params={"puesto": "qa tester"}, headers=cabeceras).json()["items"]
    assert [c["nombre"] for c in por_puesto] == ["A"]


def test_el_listado_filtra_por_categoria_y_skill(client, admin, empresa, candidato, db_session):
    db_session.add(RecruitingSkill(nombre="Zorzal", categoria="Aves", activo=True))
    candidato(empresa, nombre="Con", skills=["Zorzal"])
    candidato(empresa, nombre="Sin", skills=["Otra"])
    cabeceras = auth_headers(admin, empresa)
    assert [c["nombre"] for c in client.get(URL, params={"categorias": "aves"}, headers=cabeceras).json()["items"]] == [
        "Con"
    ]
    assert client.get(URL, params={"categorias": "Inexistente"}, headers=cabeceras).json()["total"] == 0
    assert [c["nombre"] for c in client.get(URL, params={"skills": "Zorzal"}, headers=cabeceras).json()["items"]] == [
        "Con"
    ]


def test_el_grupo_de_recruiting_ve_todos_y_otro_usuario_solo_los_que_cargo(
    client, usuario_con_grupo, reclutador, empresa, candidato
):
    otro = usuario_con_grupo("Comercial")
    candidato(empresa, nombre="Propio", creador=otro)
    candidato(empresa, nombre="Ajeno", creador=reclutador)
    assert client.get(URL, headers=auth_headers(reclutador, empresa)).json()["total"] == 2
    visibles = client.get(URL, headers=auth_headers(otro, empresa)).json()["items"]
    assert [c["nombre"] for c in visibles] == ["Propio"]


def test_el_grupo_externos_ve_solo_los_candidatos_que_cargo(client, externo, reclutador, empresa, candidato):
    candidato(empresa, nombre="Propio", creador=externo)
    candidato(empresa, nombre="DeRecruiting", creador=reclutador)
    visibles = client.get(URL, headers=auth_headers(externo, empresa)).json()["items"]
    assert [c["nombre"] for c in visibles] == ["Propio"]


# --- Alta, ficha, edición y baja ------------------------------------------------------------------------------------


def test_alta_asigna_codigo_creador_y_empresa_del_token(client, reclutador, empresa, data_factory):
    otra = data_factory.empresa()
    respuesta = client.post(
        URL, json=alta(skills=["Python"], pretension_salarial=1500000), headers=auth_headers(reclutador, empresa)
    )
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["empresa_id"] == str(empresa.id) != str(otra.id)
    assert datos["creador_id"] == str(reclutador.id)
    assert datos["codigo"].startswith("C-")
    assert datos["estado"] == "Activo"
    assert datos["skills"] == ["Python"]
    assert datos["pretension_salarial"] == 1500000


def test_alta_con_provincia_y_ciudad_del_catalogo_arma_la_ubicacion(client, reclutador, empresa, db_session):
    provincia = Provincia(nombre=f"Provincia {uuid.uuid4().hex[:6]}")
    db_session.add(provincia)
    db_session.flush()
    ciudad = Ciudad(nombre="Ciudad Test", provincia_id=provincia.provincia_id)
    db_session.add(ciudad)
    db_session.flush()
    respuesta = client.post(
        URL,
        json=alta(provincia_id=provincia.provincia_id, ciudad_id=ciudad.ciudad_id),
        headers=auth_headers(reclutador, empresa),
    )
    assert respuesta.status_code == 201
    assert respuesta.json()["ubicacion"] == f"Ciudad Test, {provincia.nombre}"


def test_alta_con_una_ciudad_de_otra_provincia_responde_400(client, reclutador, empresa, db_session):
    una = Provincia(nombre=f"Una {uuid.uuid4().hex[:6]}")
    otra = Provincia(nombre=f"Otra {uuid.uuid4().hex[:6]}")
    db_session.add_all([una, otra])
    db_session.flush()
    ciudad = Ciudad(nombre="De la otra", provincia_id=otra.provincia_id)
    db_session.add(ciudad)
    db_session.flush()
    respuesta = client.post(
        URL,
        json=alta(provincia_id=una.provincia_id, ciudad_id=ciudad.ciudad_id),
        headers=auth_headers(reclutador, empresa),
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"] == "La ciudad seleccionada no pertenece a la provincia elegida."


def test_alta_valida_el_formato_del_email_con_el_422_del_core(client, reclutador, empresa):
    respuesta = client.post(URL, json=alta(email="no-es-un-email"), headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 422
    assert respuesta.json()["errores"][0]["campo"] == "email"


def test_alta_acepta_fecha_de_nacimiento_con_barras_y_descarta_la_que_no_entiende(client, reclutador, empresa):
    cabeceras = auth_headers(reclutador, empresa)
    con_barras = client.post(URL, json=alta(fecha_nacimiento="25/12/1990"), headers=cabeceras)
    assert con_barras.json()["fecha_nacimiento"] == "1990-12-25"
    ilegible = client.post(URL, json=alta(fecha_nacimiento="cualquier cosa"), headers=cabeceras)
    assert ilegible.status_code == 201 and ilegible.json()["fecha_nacimiento"] is None


def test_alta_con_el_email_de_un_candidato_de_otro_usuario_responde_400(client, usuario_con_grupo, empresa, candidato):
    dueño = usuario_con_grupo("Comercial")
    ajeno = usuario_con_grupo("Comercial")
    existente = candidato(empresa, creador=dueño)
    respuesta = client.post(URL, json=alta(email=existente.email), headers=auth_headers(ajeno, empresa))
    assert respuesta.status_code == 400
    assert "por otro usuario" in respuesta.json()["detail"]


def test_ficha_de_un_candidato(client, reclutador, empresa, candidato):
    guardado = candidato(empresa, nombre="Beto")
    respuesta = client.get(f"{URL}/{guardado.id}", headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Beto"


def test_ficha_de_otra_empresa_o_inexistente_responde_404(client, admin, empresa, data_factory, candidato):
    ajeno = candidato(data_factory.empresa())
    cabeceras = auth_headers(admin, empresa)
    assert client.get(f"{URL}/{ajeno.id}", headers=cabeceras).status_code == 404
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=cabeceras).status_code == 404


def test_un_id_mal_formado_responde_422_y_no_500(client, admin, empresa):
    assert client.get(f"{URL}/no-es-un-uuid", headers=auth_headers(admin, empresa)).status_code == 422


def test_ficha_de_un_candidato_que_cargo_otro_usuario_responde_403(client, usuario_con_grupo, empresa, candidato):
    dueño = usuario_con_grupo("Comercial")
    otro = usuario_con_grupo("Comercial")
    guardado = candidato(empresa, creador=dueño)
    assert client.get(f"{URL}/{guardado.id}", headers=auth_headers(otro, empresa)).status_code == 403
    assert client.get(f"{URL}/{guardado.id}", headers=auth_headers(dueño, empresa)).status_code == 200


def test_edicion_cambia_solo_lo_enviado(client, reclutador, empresa, candidato):
    guardado = candidato(empresa, nombre="Ana", apellido="Lopez", seniority="Junior")
    respuesta = client.put(
        f"{URL}/{guardado.id}",
        json={"seniority": "Senior", "habilidades": ["Liderazgo"]},
        headers=auth_headers(reclutador, empresa),
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert (datos["nombre"], datos["apellido"], datos["seniority"], datos["habilidades"]) == (
        "Ana",
        "Lopez",
        "Senior",
        ["Liderazgo"],
    )


def test_edicion_de_otra_empresa_responde_404(client, admin, empresa, data_factory, candidato):
    ajeno = candidato(data_factory.empresa())
    respuesta = client.put(f"{URL}/{ajeno.id}", json={"nombre": "X"}, headers=auth_headers(admin, empresa))
    assert respuesta.status_code == 404


def test_baja_es_logica_y_el_candidato_deja_de_listarse(client, reclutador, empresa, candidato, db_session):
    guardado = candidato(empresa)
    respuesta = client.delete(f"{URL}/{guardado.id}", headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True, "mensaje": "Candidato dado de baja correctamente"}
    db_session.refresh(guardado)
    assert guardado.activo is False and guardado.deleted_at is not None
    assert client.get(URL, headers=auth_headers(reclutador, empresa)).json()["total"] == 0


def test_el_grupo_externos_no_puede_eliminar_candidatos(client, externo, empresa, candidato):
    propio = candidato(empresa, creador=externo)
    respuesta = client.delete(f"{URL}/{propio.id}", headers=auth_headers(externo, empresa))
    assert respuesta.status_code == 403


def test_permisos_de_la_interfaz_segun_el_grupo(client, externo, reclutador, empresa):
    de_externo = client.get(f"{URL}/permisos", headers=auth_headers(externo, empresa)).json()
    de_recruiting = client.get(f"{URL}/permisos", headers=auth_headers(reclutador, empresa)).json()
    assert de_externo == {
        "puede_eliminar_candidatos": False,
        "puede_cargar_cv_general": False,
        "puede_carga_masiva": False,
    }
    assert de_recruiting == {
        "puede_eliminar_candidatos": True,
        "puede_cargar_cv_general": True,
        "puede_carga_masiva": True,
    }


# --- Carga de CV ----------------------------------------------------------------------------------------------------


def subir(client, ruta, contenido, nombre, cabeceras, tipo="application/pdf"):
    return client.post(f"{URL}/{ruta}", files={"archivo": (nombre, contenido, tipo)}, headers=cabeceras)


def test_cargar_cv_crea_el_candidato_con_los_datos_del_cv(client, reclutador, empresa):
    email = f"{uuid.uuid4().hex}@example.com"
    respuesta = subir(client, "cargar-cv", pdf_de_cv(email), "cv.pdf", auth_headers(reclutador, empresa))
    assert respuesta.status_code == 201, respuesta.text
    datos = respuesta.json()
    assert datos["ok"] is True
    candidato = datos["candidato"]
    assert candidato["email"] == email
    assert candidato["empresa_id"] == str(empresa.id)
    assert candidato["creador_id"] == str(reclutador.id)
    assert candidato["cv_url"]


def test_cargar_el_mismo_cv_dos_veces_responde_409_sin_duplicar(client, reclutador, empresa, db_session):
    email = f"{uuid.uuid4().hex}@example.com"
    cabeceras = auth_headers(reclutador, empresa)
    contenido = pdf_de_cv(email)
    assert subir(client, "cargar-cv", contenido, "cv.pdf", cabeceras).status_code == 201
    repetido = subir(client, "cargar-cv", contenido, "cv.pdf", cabeceras)
    assert repetido.status_code == 409
    assert "detail" in repetido.json() or repetido.json().get("error")
    assert db_session.query(Candidato).filter(Candidato.email == email).count() == 1


def test_cargar_un_cv_distinto_con_el_mismo_email_pide_comparar_y_no_guarda(client, reclutador, empresa, db_session):
    email = f"{uuid.uuid4().hex}@example.com"
    cabeceras = auth_headers(reclutador, empresa)
    assert subir(client, "cargar-cv", pdf_de_cv(email), "cv.pdf", cabeceras).status_code == 201
    distinto = subir(client, "cargar-cv", pdf_de_cv(email, nombre="Juan Pablo Perez"), "cv-nuevo.pdf", cabeceras)
    assert distinto.status_code == 409
    cuerpo = distinto.json()
    assert cuerpo["requiere_comparacion"] is True and cuerpo["ok"] is False
    assert cuerpo["actual"]["email"] == cuerpo["nuevo"]["email"] == email
    assert db_session.query(Candidato).filter(Candidato.email == email).count() == 1


def test_actualizar_cv_reemplaza_el_cv_del_candidato_existente(client, reclutador, empresa, db_session):
    email = f"{uuid.uuid4().hex}@example.com"
    cabeceras = auth_headers(reclutador, empresa)
    primero = subir(client, "cargar-cv", pdf_de_cv(email), "cv.pdf", cabeceras).json()["candidato"]
    actualizado = subir(client, "actualizar-cv", pdf_de_cv(email, nombre="Juan Pablo Perez"), "cv2.pdf", cabeceras)
    assert actualizado.status_code == 201, actualizado.text
    assert actualizado.json()["candidato"]["id"] == primero["id"]
    assert db_session.query(Candidato).filter(Candidato.email == email).count() == 1


def test_cargar_cv_sin_email_responde_422(client, reclutador, empresa):
    documento = pymupdf.open()
    documento.new_page().insert_text((72, 72), "Juan Perez\nBackend Developer", fontsize=12)
    contenido = documento.tobytes()
    respuesta = subir(client, "cargar-cv", contenido, "sin-email.pdf", auth_headers(reclutador, empresa))
    assert respuesta.status_code == 422
    assert "detail" in respuesta.json()


def test_cargar_cv_con_formato_no_admitido_responde_error_con_detail(client, reclutador, empresa):
    respuesta = subir(client, "cargar-cv", b"texto", "cv.txt", auth_headers(reclutador, empresa), tipo="text/plain")
    assert respuesta.status_code in (400, 422)
    assert isinstance(respuesta.json()["detail"], str)


def test_el_grupo_externos_no_carga_cv_desde_el_listado_general(client, externo, empresa):
    respuesta = subir(client, "cargar-cv", pdf_de_cv("a@example.com"), "cv.pdf", auth_headers(externo, empresa))
    assert respuesta.status_code == 403


def test_subir_cv_a_un_candidato_existente_guarda_la_url(client, reclutador, empresa, candidato):
    guardado = candidato(empresa)
    respuesta = subir(
        client, f"{guardado.id}/cv", pdf_de_cv("x@example.com"), "cv.pdf", auth_headers(reclutador, empresa)
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["cv_url"]


def test_subir_cv_a_un_candidato_de_otra_empresa_responde_404(client, admin, empresa, data_factory, candidato):
    ajeno = candidato(data_factory.empresa())
    respuesta = subir(client, f"{ajeno.id}/cv", pdf_de_cv("x@example.com"), "cv.pdf", auth_headers(admin, empresa))
    assert respuesta.status_code == 404


def test_subir_cv_con_mas_de_2_mb_responde_400(client, reclutador, empresa, candidato):
    guardado = candidato(empresa)
    grande = pdf_de_cv("x@example.com") + b"0" * (2 * 1024 * 1024)
    respuesta = subir(client, f"{guardado.id}/cv", grande, "cv.pdf", auth_headers(reclutador, empresa))
    assert respuesta.status_code == 400


# --- Carga masiva ---------------------------------------------------------------------------------------------------


def test_carga_masiva_sin_archivos_responde_400(client, reclutador, empresa):
    respuesta = client.post(f"{URL}/cargar-cv-masivo/iniciar", headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 400


def test_el_grupo_externos_no_puede_iniciar_una_carga_masiva(client, externo, empresa):
    respuesta = client.post(
        f"{URL}/cargar-cv-masivo/iniciar",
        files=[("archivos", ("cv.pdf", pdf_de_cv("a@example.com"), "application/pdf"))],
        headers=auth_headers(externo, empresa),
    )
    assert respuesta.status_code == 403


def test_el_estado_y_la_cancelacion_de_un_lote_inexistente_responden_404(client, reclutador, empresa):
    cabeceras = auth_headers(reclutador, empresa)
    assert client.get(f"{URL}/cargar-cv-masivo/{uuid.uuid4()}/estado", headers=cabeceras).status_code == 404
    assert client.post(f"{URL}/cargar-cv-masivo/{uuid.uuid4()}/cancelar", headers=cabeceras).status_code == 404


def test_iniciar_la_carga_masiva_devuelve_el_lote_y_solo_su_empresa_puede_consultarlo(
    client, reclutador, empresa, data_factory, usuario_con_grupo
):
    cabeceras = auth_headers(reclutador, empresa)
    iniciado = client.post(
        f"{URL}/cargar-cv-masivo/iniciar",
        files=[("archivos", ("cv.pdf", pdf_de_cv(f"{uuid.uuid4().hex}@example.com"), "application/pdf"))],
        headers=cabeceras,
    )
    assert iniciado.status_code == 202, iniciado.text
    lote = iniciado.json()
    assert lote["estado"] == "preparando" and lote["lote_id"]
    assert client.get(f"{URL}/cargar-cv-masivo/{lote['lote_id']}/estado", headers=cabeceras).status_code == 200
    otra = data_factory.empresa()
    de_otra_empresa = usuario_con_grupo("Recruiting", empresa_del_usuario=otra)
    ajeno = client.get(f"{URL}/cargar-cv-masivo/{lote['lote_id']}/estado", headers=auth_headers(de_otra_empresa, otra))
    assert ajeno.status_code in (403, 404)


def test_el_procesamiento_de_un_zip_crea_un_candidato_por_cv_y_resume_por_categoria(db_session, empresa, admin):
    class Archivo:
        def __init__(self, nombre, contenido):
            self.filename, self._contenido = nombre, contenido

        async def read(self):
            return self._contenido

    nuevo, repetido = f"{uuid.uuid4().hex}@example.com", f"{uuid.uuid4().hex}@example.com"
    zip_en_memoria = io.BytesIO()
    with zipfile.ZipFile(zip_en_memoria, "w") as zf:
        zf.writestr("uno.pdf", pdf_de_cv(nuevo))
        zf.writestr("dos.pdf", pdf_de_cv(repetido))
        zf.writestr("dos-copia.pdf", pdf_de_cv(repetido))
        zf.writestr("leeme.txt", b"no es un CV")
    resultado = asyncio.run(
        CandidatoService.procesar_carga_masiva_zip_rar(
            db=db_session,
            empresa_id=empresa.id,
            archivo=Archivo("lote.zip", zip_en_memoria.getvalue()),
            archivos=None,
            usuario=admin.email,
            current_user=admin,
        )
    )
    resumen = resultado["resumen"]
    assert resumen["creados"] == 2
    assert resumen["duplicados_omitidos"] == 1
    assert db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).count() == 2


# --- Catálogos de solo lectura --------------------------------------------------------------------------------------


def test_catalogos_para_el_formulario(client, reclutador, empresa, db_session):
    nombre_skill = f"Skill-{uuid.uuid4().hex[:6]}"
    db_session.add_all(
        [
            RecruitingSkill(nombre=nombre_skill, categoria="Lenguajes", activo=True),
            RecruitingSkill(nombre=f"Inactiva-{uuid.uuid4().hex[:6]}", activo=False),
        ]
    )
    provincia = Provincia(nombre=f"Prov {uuid.uuid4().hex[:6]}")
    db_session.add(provincia)
    db_session.flush()
    db_session.add(Ciudad(nombre="Ciudad 1", provincia_id=provincia.provincia_id))
    db_session.flush()
    cabeceras = auth_headers(reclutador, empresa)

    skills = client.get("/api/v1/recruiting/skills", headers=cabeceras).json()
    assert nombre_skill in {s["nombre"] for s in skills}
    assert all(s["activo"] for s in skills)
    provincias = client.get("/api/v1/recruiting/provincias", headers=cabeceras).json()
    assert {"provincia_id": provincia.provincia_id, "nombre": provincia.nombre, "cantidad_ciudades": 1} in provincias
    ciudades = client.get(
        "/api/v1/recruiting/ciudades", params={"provincia_id": provincia.provincia_id}, headers=cabeceras
    ).json()
    assert [(c["nombre"], c["provincia_nombre"]) for c in ciudades] == [("Ciudad 1", provincia.nombre)]
    assert client.get("/api/v1/recruiting/habilidades", headers=cabeceras).status_code == 200
    assert client.get("/api/v1/recruiting/niveles-seniority", headers=cabeceras).status_code == 200
    assert client.get(f"{URL}/perfiles-puesto", headers=cabeceras).json() == [] or isinstance(
        client.get(f"{URL}/perfiles-puesto", headers=cabeceras).json(), list
    )


# --- Contrato -------------------------------------------------------------------------------------------------------


def test_el_contrato_declara_operation_ids_y_respuestas_tipadas(client):
    rutas = client.get("/openapi.json").json()["paths"]
    esperadas = {
        ("/api/v1/recruiting/candidatos", "get"): "recruiting_candidatos_listar",
        ("/api/v1/recruiting/candidatos", "post"): "recruiting_candidatos_crear",
        ("/api/v1/recruiting/candidatos/{candidato_id}", "get"): "recruiting_candidatos_obtener",
        ("/api/v1/recruiting/candidatos/{candidato_id}", "put"): "recruiting_candidatos_actualizar",
        ("/api/v1/recruiting/candidatos/{candidato_id}", "delete"): "recruiting_candidatos_eliminar",
        ("/api/v1/recruiting/candidatos/cargar-cv", "post"): "recruiting_candidatos_cargar_cv",
        (
            "/api/v1/recruiting/candidatos/cargar-cv-masivo/iniciar",
            "post",
        ): "recruiting_candidatos_carga_masiva_iniciar",
    }
    for (ruta, metodo), operation_id in esperadas.items():
        assert rutas[ruta][metodo]["operationId"] == operation_id
    esquema = rutas["/api/v1/recruiting/candidatos"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert esquema == {"$ref": "#/components/schemas/CandidatoPagina"}
    parametros = {p["name"] for p in rutas["/api/v1/recruiting/candidatos/{candidato_id}"]["get"]["parameters"]}
    assert parametros == {"candidato_id"}
    tipo_id = rutas["/api/v1/recruiting/candidatos/{candidato_id}"]["get"]["parameters"][0]["schema"]
    assert tipo_id == {"type": "string", "format": "uuid", "title": "Candidato Id"}
