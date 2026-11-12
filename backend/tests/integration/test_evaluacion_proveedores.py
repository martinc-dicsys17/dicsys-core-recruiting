"""Evaluación de proveedores: configuración, campañas, tablero y respuestas."""

import uuid
from datetime import timedelta

import pytest

from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_comun import asegurar_item, hoy_argentina
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    ImportacionProveedores,
    ProveedoresAuditoria,
    RegistroProveedor,
)
from backend.modules.administracion.proveedores_services import ProveedorRegistroService
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/evaluaciones-proveedores"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(data_factory, db_session):
    empresa = data_factory.empresa()

    def usuario_con(claves, *, dni=None):
        usuario = data_factory.usuario(dni=dni)
        grupo = data_factory.grupo()
        data_factory.asignar_empresa(usuario, empresa)
        data_factory.asignar_grupo(usuario, grupo, empresa)
        data_factory.permisos(grupo, claves)
        return usuario, auth_headers(usuario, empresa)

    admin, h_admin = usuario_con(
        ["admin_contable", "admin_contable.evaluacion_proveedores", "admin_contable.evaluacion_config"]
    )
    vega = data_factory.empleado(
        empresa, nombre="Federico", apellido="Vega", dni=30111222, email_corporativo="fvega@dicsys.com"
    )
    gonzalez = data_factory.empleado(
        empresa, nombre="Natalia", apellido="Gonzalez", dni=30333444, email_corporativo="ngonzalez@dicsys.ai"
    )
    _, h_vega = usuario_con(["admin_contable", "admin_contable.evaluacion_proveedores"], dni=30111222)
    _, h_gonzalez = usuario_con(["admin_contable", "admin_contable.evaluacion_proveedores"], dni=30333444)

    def proveedor(nombre, tipo="sin_clasificar", referente=None, activo=True):
        p = RegistroProveedor(
            empresa_id=empresa.id,
            nombre=nombre,
            tipo=tipo,
            activo=activo,
            referente_empleado_id=referente.id if referente else None,
        )
        db_session.add(p)
        db_session.flush()
        return p

    def sumar(evaluacion, *proveedores):
        """Lo que hacen la importación del Sheet o «Agregar proveedor»: entran a la campaña."""
        campania = db_session.get(EvaluacionProveedores, uuid.UUID(evaluacion["id"]))
        for p in proveedores:
            asegurar_item(db_session, campania, p, Actor(usuario_id=None, email="sheet@dicsys.com"))
        db_session.commit()  # como la API: un rollback posterior no lo borra
        return evaluacion

    return {
        "empresa": empresa,
        "admin": admin,
        "h_admin": h_admin,
        "h_vega": h_vega,
        "h_gonzalez": h_gonzalez,
        "vega": vega,
        "gonzalez": gonzalez,
        "proveedor": proveedor,
        "sumar": sumar,
    }


def _crear_evaluacion(client, headers, periodo="2026", desde=-1, hasta=10):
    hoy = hoy_argentina()
    return client.post(
        f"{BASE}/evaluaciones",
        headers=headers,
        json={
            "periodo": periodo,
            "fecha_apertura": str(hoy + timedelta(days=desde)),
            "fecha_cierre": str(hoy + timedelta(days=hasta)),
        },
    )


# ─── Configuración ──────────────────────────────────────────────────────────────


def test_configuracion_arranca_apagada_y_se_guarda_con_auditoria(client, db_session, entorno):
    h = entorno["h_admin"]
    inicial = client.get(f"{BASE}/configuracion", headers=h).json()
    assert inicial["recordar_cada_dias"] is None and not inicial["aviso_apertura"] and not inicial["canal_email"]
    assert inicial["sheet_hoja"] == "Listado Proveedores" and inicial["hora_envio"] == "09:00:00"

    guardada = client.put(
        f"{BASE}/configuracion",
        headers=h,
        json={
            "sheet_url": "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
            "recordar_cada_dias": 2,
            "aviso_previo_cierre": True,
            "canal_email": True,
            "email_cc": "seguridad@dicsys.com; it@dicsys.com",
            "hora_envio": "10:30",
        },
    ).json()
    assert guardada["email_cc"] == ["seguridad@dicsys.com", "it@dicsys.com"]
    assert guardada["recordar_cada_dias"] == 2 and guardada["hora_envio"] == "10:30:00"
    assert db_session.query(ProveedoresAuditoria).filter_by(entidad="configuracion").count() == 1


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        ({"canal_webex_canal": True}, "Para avisar en un canal de Webex hay que indicar el ID del room"),
        ({"recordar_cada_dias": 3}, None),
        ({"email_cc": "no-es-mail"}, None),
    ],
)
def test_configuracion_invalida(client, entorno, datos, mensaje):
    respuesta = client.put(f"{BASE}/configuracion", headers=entorno["h_admin"], json=datos)
    assert respuesta.status_code == 422
    if mensaje:
        assert respuesta.json()["detail"] == mensaje


def test_configuracion_exige_el_permiso_de_admin(client, entorno):
    assert client.get(f"{BASE}/configuracion", headers=entorno["h_vega"]).status_code == 403


# ─── Campañas ───────────────────────────────────────────────────────────────────


def test_una_evaluacion_nueva_arranca_sin_proveedores(client, db_session, entorno):
    activo = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    entorno["proveedor"]("Dado de baja", activo=False)

    creada = _crear_evaluacion(client, entorno["h_admin"])

    assert creada.status_code == 201, creada.text
    datos = creada.json()
    assert datos["estado"] == "abierta" and datos["activa"] is True
    # No se evalúan todos: solo lo que entra por el Sheet o con «Agregar proveedor»
    assert datos["metricas"] == {"total": 0, "evaluados": 0, "pendientes": 0, "con_hallazgo": 0, "sin_evaluador": 0}
    assert db_session.query(EvaluacionItem).count() == 0

    agregado = client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(activo.id)]})
    assert agregado.status_code == 201, agregado.text
    item = db_session.query(EvaluacionItem).one()
    assert item.proveedor_id == activo.id and item.evaluador_empleado_id == entorno["vega"].id


def test_crear_la_siguiente_reemplaza_a_la_anterior_sin_tocar_sus_items(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    anterior = entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"], "2026").json(), odoo)
    assert _crear_evaluacion(client, entorno["h_admin"], "2026").status_code == 409

    siguiente = _crear_evaluacion(client, entorno["h_admin"], "2027", desde=0, hasta=30).json()
    assert db_session.query(EvaluacionItem).filter_by(evaluacion_id=uuid.UUID(siguiente["id"])).count() == 0

    lista = client.get(f"{BASE}/evaluaciones", headers=entorno["h_admin"]).json()
    estados = {e["periodo"]: e["estado"] for e in lista}
    assert estados == {"2026": "reemplazada", "2027": "abierta"}
    assert db_session.query(EvaluacionItem).filter_by(evaluacion_id=uuid.UUID(anterior["id"])).count() == 1
    respuesta = client.put(
        f"{BASE}/evaluaciones/{anterior['id']}",
        headers=entorno["h_admin"],
        json={"fecha_apertura": str(hoy_argentina()), "fecha_cierre": str(hoy_argentina() + timedelta(days=5))},
    )
    assert respuesta.status_code == 409


def test_fechas_invertidas_se_rechazan(client, entorno):
    respuesta = _crear_evaluacion(client, entorno["h_admin"], desde=5, hasta=1)
    assert respuesta.status_code == 422
    # El mensaje del validador llega tal cual (sin «Body: tiene un valor inválido»)
    assert respuesta.json()["detail"] == "La fecha de cierre no puede ser anterior a la de apertura"


def test_ampliar_el_cierre_reabre_la_evaluacion_cerrada(client, db_session, entorno):
    evaluacion = _crear_evaluacion(client, entorno["h_admin"], desde=-10, hasta=-1).json()
    assert evaluacion["estado"] == "cerrada"

    hoy = hoy_argentina()
    ampliada = client.put(
        f"{BASE}/evaluaciones/{evaluacion['id']}",
        headers=entorno["h_admin"],
        json={"fecha_apertura": evaluacion["fecha_apertura"], "fecha_cierre": str(hoy + timedelta(days=3))},
    ).json()

    assert ampliada["estado"] == "abierta"
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="ampliar_cierre").one()
    assert evento.despues == {"fecha_cierre": str(hoy + timedelta(days=3))}


# ─── Tablero ────────────────────────────────────────────────────────────────────


def test_tablero_admin_ve_todo_y_el_evaluador_solo_lo_suyo(client, entorno):
    proveedores = [
        entorno["proveedor"]("ODOO", "herramienta", entorno["vega"]),
        entorno["proveedor"]("Banco Galicia", "proveedor", entorno["gonzalez"]),
        entorno["proveedor"]("Sin dueño"),
    ]
    entorno["proveedor"]("No se evalúa", "proveedor", entorno["vega"])  # en el registro, no en la evaluación
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), *proveedores)

    admin = client.get(f"{BASE}/tablero", headers=entorno["h_admin"]).json()
    assert admin["es_admin"] is True
    assert [i["proveedor"]["nombre"] for i in admin["items"]] == ["Banco Galicia", "ODOO", "Sin dueño"]
    assert admin["metricas"]["sin_evaluador"] == 1
    assert [e["nombre"] for e in admin["evaluadores"]] == ["Gonzalez, Natalia", "Vega, Federico"]
    assert all(i["puede_editar"] for i in admin["items"])  # el admin edita todo (D-87)

    vega = client.get(f"{BASE}/tablero", headers=entorno["h_vega"]).json()
    assert vega["es_admin"] is False and vega["empleado_vinculado"] is True
    assert [i["proveedor"]["nombre"] for i in vega["items"]] == ["ODOO"]
    item = vega["items"][0]
    assert item["preguntas"] == ["incidentes", "mal_manejo"] and item["puede_editar"] is True
    assert vega["opciones"] == {"incidentes": ["Si", "No", "N/A"], "mal_manejo": ["Si", "No"]}  # sin checklist


def test_tablero_sin_empleado_vinculado_no_muestra_items(client, data_factory, entorno):
    odoo = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, entorno["empresa"])
    data_factory.asignar_grupo(usuario, grupo, entorno["empresa"])
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_proveedores"])

    tablero = client.get(f"{BASE}/tablero", headers=auth_headers(usuario, entorno["empresa"])).json()
    assert tablero["empleado_vinculado"] is False and tablero["items"] == []


def test_sin_evaluacion_el_tablero_viene_vacio(client, entorno):
    tablero = client.get(f"{BASE}/tablero", headers=entorno["h_vega"]).json()
    assert tablero["evaluacion"] is None and tablero["items"] == []


# ─── Respuestas ─────────────────────────────────────────────────────────────────


def _item_de(client, headers, nombre):
    return next(
        i for i in client.get(f"{BASE}/tablero", headers=headers).json()["items"] if i["proveedor"]["nombre"] == nombre
    )


def test_el_evaluador_responde_las_dos_preguntas_sea_cual_sea_el_tipo(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")

    incompleta = client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"incidentes": "No"})
    assert incompleta.status_code == 422 and "mal manejo" in incompleta.json()["detail"]

    respuesta = client.put(
        f"{BASE}/items/{item['id']}",
        headers=entorno["h_vega"],
        json={
            "incidentes": "No",
            "mal_manejo": "Si",
            "evidencia_mal_manejo": "  https://drive/incidente-odoo  ",
            "evidencia_incidentes": "no aplica con «No»",
            "checklist": "Aprobada",
        },
    )  # el checklist ya no existe
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["con_hallazgo"] is True

    guardado = db_session.get(EvaluacionItem, uuid.UUID(item["id"]))
    assert (guardado.incidentes, guardado.mal_manejo) == ("No", "Si")
    assert not hasattr(guardado, "checklist")
    # La evidencia acompaña al «Si» (recortada); con «No» se descarta
    assert guardado.evidencia_mal_manejo == "https://drive/incidente-odoo" and guardado.evidencia_incidentes is None
    assert guardado.evaluado_at is not None
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="evaluar").one()
    assert evento.despues["mal_manejo"] == "Si" and "checklist" not in evento.despues

    tablero = client.get(f"{BASE}/tablero", headers=entorno["h_vega"]).json()
    assert tablero["metricas"]["evaluados"] == 1 and tablero["metricas"]["con_hallazgo"] == 1
    assert tablero["items"][0]["evaluado"] is True and tablero["items"][0]["puede_editar"] is True
    assert tablero["items"][0]["con_evidencia"] is True and "checklist" not in tablero["items"][0]
    historial = ProveedorRegistroService.historial(db_session, guardado.proveedor)  # la ficha del proveedor
    assert historial[0]["evidencia_mal_manejo"] == "https://drive/incidente-odoo" and "checklist" not in historial[0]


@pytest.mark.parametrize(
    "respuestas, falta",
    [
        ({"incidentes": "Si", "mal_manejo": "No"}, "incidentes"),
        ({"incidentes": "No", "mal_manejo": "Si", "evidencia_mal_manejo": "   "}, "mal manejo de información"),
        ({"incidentes": "Si", "mal_manejo": "Si", "evidencia_incidentes": "x"}, "mal manejo de información"),
    ],
)
def test_con_si_la_evidencia_es_obligatoria(client, db_session, entorno, respuestas, falta):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")

    respuesta = client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json=respuestas)

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == f"Con «Si» la evidencia es obligatoria: falta la de {falta}"
    assert db_session.get(EvaluacionItem, uuid.UUID(item["id"])).evaluado_at is None


def test_con_no_o_na_la_evidencia_no_se_pide(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")

    respuesta = client.put(
        f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"incidentes": "N/A", "mal_manejo": "No"}
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["con_hallazgo"] is False


def test_editan_el_referente_y_el_admin_pero_no_otro_evaluador(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "proveedor", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_admin"], "ODOO")
    assert item["puede_editar"] is True  # el admin ve el botón Editar (D-87)

    respuestas = {"incidentes": "No", "mal_manejo": "No"}
    assert client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_gonzalez"], json=respuestas).status_code == 403
    assert (
        client.put(
            f"{BASE}/items/{item['id']}",
            headers=entorno["h_admin"],
            json={**respuestas, "mal_manejo": "Si", "evidencia_mal_manejo": "corregido por seguridad"},
        ).status_code
        == 200
    )
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="evaluar").one()
    assert evento.usuario_email == entorno["admin"].email


def test_detalle_de_la_evaluacion_con_historial(client, entorno):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")
    client.put(
        f"{BASE}/items/{item['id']}",
        headers=entorno["h_vega"],
        json={"incidentes": "Si", "mal_manejo": "No", "evidencia_incidentes": "https://drive/incidente"},
    )
    client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"incidentes": "No", "mal_manejo": "No"})

    detalle = client.get(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"]).json()

    assert detalle["proveedor"]["nombre"] == "ODOO" and detalle["evaluacion"]["periodo"] == "2026"
    assert detalle["evaluador"]["nombre"] == "Vega, Federico"
    assert (detalle["incidentes"], detalle["evidencia_incidentes"]) == ("No", None)
    assert "checklist" not in detalle and "checklist" not in detalle["opciones"]
    assert detalle["con_hallazgo"] is False and detalle["puede_editar"] is True and detalle["evaluado_por"]
    acciones = [h["accion"] for h in detalle["historial"]]
    assert acciones == ["evaluar", "evaluar", "crear"]  # del más nuevo al más viejo
    assert detalle["historial"][0]["antes"] == {"incidentes": "Si", "evidencia_incidentes": "https://drive/incidente"}
    assert detalle["historial"][0]["despues"] == {"incidentes": "No", "evidencia_incidentes": None}

    # El admin lo ve; otro evaluador no
    assert client.get(f"{BASE}/items/{item['id']}", headers=entorno["h_admin"]).status_code == 200
    assert client.get(f"{BASE}/items/{item['id']}", headers=entorno["h_gonzalez"]).status_code == 403
    assert client.get(f"{BASE}/items/{uuid.uuid4()}", headers=entorno["h_admin"]).status_code == 404


@pytest.mark.parametrize("desde, hasta, texto", [(-10, -1, "cerrada"), (2, 10, "abre el")])
def test_fuera_de_la_ventana_no_se_puede_evaluar(client, entorno, desde, hasta, texto):
    odoo = entorno["proveedor"]("ODOO", "proveedor", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"], desde=desde, hasta=hasta).json(), odoo)
    item = _item_de(client, entorno["h_admin"], "ODOO")

    respuesta = client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"mal_manejo": "No"})
    assert respuesta.status_code == 409 and texto in respuesta.json()["detail"]


def test_respuesta_con_opcion_inexistente(client, entorno):
    odoo = entorno["proveedor"]("ODOO", "proveedor", entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")
    assert (
        client.put(f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"mal_manejo": "Tal vez"}).status_code
        == 422
    )


def test_admin_puede_mirar_una_evaluacion_anterior(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    anterior = entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"], "2026").json(), odoo)
    _crear_evaluacion(client, entorno["h_admin"], "2027", desde=0, hasta=30)

    tablero = client.get(f"{BASE}/tablero?evaluacion_id={anterior['id']}", headers=entorno["h_admin"]).json()
    assert tablero["evaluacion"]["periodo"] == "2026" and tablero["evaluacion"]["estado"] == "reemplazada"
    assert tablero["puede_evaluar"] is False
    assert [e["nombre"] for e in tablero["evaluaciones"]] == ["2027", "2026"]
    # Un evaluador no elige: siempre ve la vigente
    vega = client.get(f"{BASE}/tablero?evaluacion_id={anterior['id']}", headers=entorno["h_vega"]).json()
    assert vega["evaluacion"]["periodo"] == "2027"


# ─── Agregar proveedores a la evaluación activa ─────────────────────────────────


def _candidatos(client, headers, buscar=""):
    respuesta = client.get(f"{BASE}/candidatos", headers=headers, params={"buscar": buscar})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def test_el_admin_ve_todo_el_registro_pero_un_inactivo_no_se_agrega(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    de_baja = entorno["proveedor"]("Webmail", "herramienta", entorno["gonzalez"], activo=False)
    db_session.commit()  # como la API: el rollback del 409 de abajo no lo borra

    # Busca en todo el registro: el que ya está en la evaluación aparece marcado y al final
    candidatos = _candidatos(client, entorno["h_admin"])
    assert candidatos["total"] == 2
    assert [(c["nombre"], c["activo"], c["referente"], c["en_evaluacion"]) for c in candidatos["items"]] == [
        ("Webmail", False, "Gonzalez, Natalia", False),
        ("ODOO", True, "Vega, Federico", True),
    ]
    [odoo] = _candidatos(client, entorno["h_admin"], "odoo")["items"]
    assert odoo["en_evaluacion"] is True

    # Inactivo: no se usa para evaluaciones nuevas (ni se reactiva solo al agregarlo)
    inactivo = client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(de_baja.id)]})
    assert inactivo.status_code == 409
    assert inactivo.json()["detail"] == "«Webmail» está inactivo: para evaluarlo, primero activalo en Proveedores"
    db_session.refresh(de_baja)
    assert de_baja.activo is False
    assert db_session.query(ProveedoresAuditoria).filter_by(entidad_id=de_baja.id).count() == 0

    # Activo en Proveedores, se agrega con su referente como evaluador
    de_baja.activo = True
    db_session.commit()
    respuesta = client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(de_baja.id)]})
    assert respuesta.status_code == 201, respuesta.text
    item = db_session.get(EvaluacionItem, uuid.UUID(respuesta.json()["agregados"][0]["id"]))
    assert item.evaluador_empleado_id == entorno["gonzalez"].id
    assert all(c["en_evaluacion"] for c in _candidatos(client, entorno["h_admin"])["items"])

    repetido = client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(de_baja.id)]})
    assert repetido.status_code == 409 and "ya está en la evaluación" in repetido.json()["detail"]


def test_agrega_varios_de_una_vez_y_es_todo_o_nada(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    galicia = entorno["proveedor"]("Banco Galicia", "proveedor", entorno["gonzalez"])
    mapfre = entorno["proveedor"]("Mapfre", "proveedor", entorno["vega"])
    _crear_evaluacion(client, entorno["h_admin"])

    # Un evaluador con uno ajeno en la lista: no entra ninguno, y el mensaje dice cuál
    mezcla = client.post(
        f"{BASE}/items", headers=entorno["h_vega"], json={"proveedor_ids": [str(odoo.id), str(galicia.id)]}
    )
    assert mezcla.status_code == 403 and "«Banco Galicia» no te está asignado" in mezcla.json()["detail"]
    assert db_session.query(EvaluacionItem).count() == 0

    # El admin suma varios (los repetidos cuentan una vez)
    varios = client.post(
        f"{BASE}/items",
        headers=entorno["h_admin"],
        json={"proveedor_ids": [str(odoo.id), str(galicia.id), str(odoo.id)]},
    )
    assert varios.status_code == 201, varios.text
    assert [a["proveedor_id"] for a in varios.json()["agregados"]] == [str(odoo.id), str(galicia.id)]
    assert {i.proveedor_id for i in db_session.query(EvaluacionItem)} == {odoo.id, galicia.id}

    # Uno que ya está frena la tanda entera
    otra = client.post(
        f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(mapfre.id), str(odoo.id)]}
    )
    assert otra.status_code == 409 and "«ODOO» ya está en la evaluación" in otra.json()["detail"]
    assert db_session.query(EvaluacionItem).count() == 2
    assert client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": []}).status_code == 422


def test_la_busqueda_ignora_acentos_y_mayusculas_y_encuentra_por_cuit(client, db_session, entorno):
    _crear_evaluacion(client, entorno["h_admin"])
    galicia = entorno["proveedor"]("Banco Galicía")
    galicia.razon_social, galicia.cuit = "Banco de Galicia y Buenos Aires S.A.U.", "30-50000173-5"
    entorno["proveedor"]("Mapfre Seguros")
    db_session.flush()

    def nombres(buscar):
        return [c["nombre"] for c in _candidatos(client, entorno["h_admin"], buscar)["items"]]

    assert nombres("GALICIA") == ["Banco Galicía"]  # sin el acento de la búsqueda
    assert nombres("galicía") == ["Banco Galicía"]
    assert nombres("buenos aires") == ["Banco Galicía"]  # razón social
    assert nombres("30500001735") == nombres("30-50000173-5") == ["Banco Galicía"]  # CUIT con o sin guiones
    assert nombres("no existe") == []


def test_ya_no_se_registra_un_proveedor_desde_la_evaluacion(client, entorno):
    """Los nuevos se dan de alta en el registro (Proveedores) y después se agregan."""
    _crear_evaluacion(client, entorno["h_admin"])
    assert client.post(
        f"{BASE}/items/registrar", headers=entorno["h_admin"], json={"nombre": "Nuevo SA"}
    ).status_code in (404, 405)


def test_el_evaluador_agrega_solo_los_que_tiene_asignados(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "herramienta", entorno["vega"])
    galicia = entorno["proveedor"]("Banco Galicia", "proveedor", entorno["gonzalez"])
    entorno["proveedor"]("Sin dueño")
    webmail = entorno["proveedor"]("Webmail", "herramienta", entorno["vega"], activo=False)
    _crear_evaluacion(client, entorno["h_admin"])

    # Solo ve los activos que tiene asignados como usuario referente
    assert [c["nombre"] for c in _candidatos(client, entorno["h_vega"])["items"]] == ["ODOO"]
    assert _candidatos(client, entorno["h_vega"], "galicia") == {"total": 0, "items": []}
    assert _candidatos(client, entorno["h_admin"])["total"] == 4  # el admin, todo el registro

    ajeno = client.post(f"{BASE}/items", headers=entorno["h_vega"], json={"proveedor_ids": [str(galicia.id)]})
    assert ajeno.status_code == 403 and "«Banco Galicia» no te está asignado" in ajeno.json()["detail"]
    de_baja = client.post(f"{BASE}/items", headers=entorno["h_vega"], json={"proveedor_ids": [str(webmail.id)]})
    assert de_baja.status_code == 409 and "activalo en Proveedores" in de_baja.json()["detail"]

    propio = client.post(f"{BASE}/items", headers=entorno["h_vega"], json={"proveedor_ids": [str(odoo.id)]})
    assert propio.status_code == 201, propio.text
    item = db_session.get(EvaluacionItem, uuid.UUID(propio.json()["agregados"][0]["id"]))
    assert item.evaluador_empleado_id == entorno["vega"].id
    assert [
        i["proveedor"]["nombre"] for i in client.get(f"{BASE}/tablero", headers=entorno["h_vega"]).json()["items"]
    ] == ["ODOO"]
    assert _candidatos(client, entorno["h_vega"])["items"][0]["en_evaluacion"] is True


def test_sin_empleado_vinculado_no_hay_proveedores_para_agregar(client, data_factory, entorno):
    _crear_evaluacion(client, entorno["h_admin"])
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, entorno["empresa"])
    data_factory.asignar_grupo(usuario, grupo, entorno["empresa"])
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_proveedores"])

    respuesta = client.get(f"{BASE}/candidatos", headers=auth_headers(usuario, entorno["empresa"]))
    assert respuesta.status_code == 403 and "no está vinculado" in respuesta.json()["detail"]


def test_sin_evaluacion_activa_no_se_agrega(client, entorno):
    _crear_evaluacion(client, entorno["h_admin"], desde=-10, hasta=-1)  # ya cerró
    p = entorno["proveedor"]("ODOO")
    assert client.get(f"{BASE}/candidatos", headers=entorno["h_admin"]).status_code == 409
    assert (
        client.post(f"{BASE}/items", headers=entorno["h_admin"], json={"proveedor_ids": [str(p.id)]}).status_code == 409
    )


def test_agregar_exige_el_permiso_de_evaluacion(client, data_factory, entorno):
    _crear_evaluacion(client, entorno["h_admin"])
    p = entorno["proveedor"]("ODOO", referente=entorno["vega"])
    usuario = data_factory.usuario(dni=30111222)  # el empleado de Vega, pero sin el submódulo
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, entorno["empresa"])
    data_factory.asignar_grupo(usuario, grupo, entorno["empresa"])
    data_factory.permisos(grupo, ["admin_contable"])
    headers = auth_headers(usuario, entorno["empresa"])
    assert client.get(f"{BASE}/candidatos", headers=headers).status_code == 403
    assert client.post(f"{BASE}/items", headers=headers, json={"proveedor_ids": [str(p.id)]}).status_code == 403


def test_eliminar_una_evaluacion_aunque_tenga_evaluados(client, db_session, entorno):
    odoo = entorno["proveedor"]("ODOO", "proveedor", entorno["vega"])
    evaluacion = entorno["sumar"](_crear_evaluacion(client, entorno["h_admin"]).json(), odoo)
    item = _item_de(client, entorno["h_vega"], "ODOO")
    assert (
        client.put(
            f"{BASE}/items/{item['id']}", headers=entorno["h_vega"], json={"incidentes": "No", "mal_manejo": "No"}
        ).status_code
        == 200
    )
    url = f"{BASE}/evaluaciones/{evaluacion['id']}"

    assert client.delete(url, headers=entorno["h_vega"]).status_code == 403  # sin el permiso de configuración
    respuesta = client.delete(url, headers=entorno["h_admin"])

    assert respuesta.status_code == 200, respuesta.text
    assert client.get(f"{BASE}/evaluaciones", headers=entorno["h_admin"]).json() == []
    tablero = client.get(f"{BASE}/tablero", headers=entorno["h_vega"]).json()
    assert tablero["evaluacion"] is None and tablero["items"] == []
    db_session.expire_all()
    assert db_session.get(EvaluacionItem, uuid.UUID(item["id"])).deleted_at is not None  # baja lógica
    evento = db_session.query(ProveedoresAuditoria).filter_by(entidad="evaluacion", accion="eliminar").one()
    assert evento.usuario_email == entorno["admin"].email
    assert (evento.antes["periodo"], evento.antes["proveedores"], evento.antes["evaluados"]) == ("2026", 1, 1)
    # Deja de verse en la ficha del proveedor y el período se puede volver a crear
    assert ProveedorRegistroService.historial(db_session, odoo) == []
    assert _crear_evaluacion(client, entorno["h_admin"]).status_code == 201
    assert client.delete(url, headers=entorno["h_admin"]).status_code == 404  # ya eliminada


def test_eliminar_descarta_la_vista_previa_pendiente_del_sheet(client, db_session, entorno):
    evaluacion = _crear_evaluacion(client, entorno["h_admin"]).json()
    vista_previa = ImportacionProveedores(empresa_id=entorno["empresa"].id, evaluacion_id=uuid.UUID(evaluacion["id"]))
    db_session.add(vista_previa)
    db_session.commit()

    assert client.delete(f"{BASE}/evaluaciones/{evaluacion['id']}", headers=entorno["h_admin"]).status_code == 200
    assert db_session.query(ImportacionProveedores).count() == 0
