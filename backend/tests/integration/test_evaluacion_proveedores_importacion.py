"""Importación del Sheet «Listado Proveedores» a la evaluación activa (vista previa y confirmación)."""

import uuid
from datetime import timedelta

import pytest

from backend.core import google_sheets
from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_comun import asegurar_item, hoy_argentina
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    ImportacionFila,
    ImportacionProveedores,
    ProveedoresAuditoria,
    ProveedoresConfiguracion,
    RegistroProveedor,
)
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/evaluaciones-proveedores"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

ENCABEZADO = [
    "",
    "Razón Social (Nombre de fantasía) - Herramienta",
    "Referente Interno",
    "Servicio/Bien Provisto",
    "Tipo de información que manejan",
    "Hay un acuerdo de servicio firmado? (Proveedores)",
    "Tiene Politica de seguridad o firma nuestro Acuerdo de confidencialidad",
    "Herramientas: Si hubo incidentes",
]
TITULO = ["", "RC 02-02 (3)\nRevisión 00", "", "", "", "", "", "Evaluación de proveedores"]


@pytest.fixture
def entorno(data_factory, db_session, monkeypatch):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_config"])
    headers = auth_headers(usuario, empresa)
    db_session.add(
        ProveedoresConfiguracion(
            empresa_id=empresa.id,
            sheet_hoja="Listado Proveedores",
            sheet_url="https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit",
        )
    )
    db_session.flush()
    vega = data_factory.empleado(empresa, nombre="Federico Martín", apellido="Vega")
    gonzalez = data_factory.empleado(empresa, nombre="Natalia", apellido="Gonzalez")
    data_factory.empleado(empresa, nombre="Diego", apellido="Galvan")
    data_factory.empleado(empresa, nombre="Diego", apellido="Galvan")  # homónimo: ambiguo

    hoja = {"filas": []}
    pedidos = []

    def leer(url, nombre_hoja, **_):
        pedidos.append((url, nombre_hoja))
        return hoja["filas"]

    monkeypatch.setattr(google_sheets, "leer_hoja", leer)
    hoy = hoy_argentina()
    return {
        "empresa": empresa,
        "headers": headers,
        "hoja": hoja,
        "pedidos": pedidos,
        "vega": vega,
        "gonzalez": gonzalez,
        "hoy": hoy,
    }


def _evaluacion(client, entorno, periodo="2026"):
    hoy = entorno["hoy"]
    respuesta = client.post(
        f"{BASE}/evaluaciones",
        headers=entorno["headers"],
        json={"periodo": periodo, "fecha_apertura": str(hoy), "fecha_cierre": str(hoy + timedelta(days=15))},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _fila(nombre, referente, servicio="", tipo_info="", acuerdo="", nda=""):
    return ["", nombre, referente, servicio, tipo_info, acuerdo, nda]


def test_vista_previa_clasifica_altas_cambios_y_rechazadas(client, db_session, entorno):
    existente_igual = RegistroProveedor(
        empresa_id=entorno["empresa"].id, nombre="ODOO", referente_empleado_id=entorno["vega"].id
    )
    existente_cambia = RegistroProveedor(
        empresa_id=entorno["empresa"].id, nombre="Google Suite", referente_empleado_id=entorno["vega"].id
    )
    db_session.add_all([existente_igual, existente_cambia])
    db_session.flush()
    _evaluacion(client, entorno)
    entorno["hoja"]["filas"] = [
        TITULO,
        ENCABEZADO,
        _fila("odoo", "Vega Federico"),
        _fila("Google Suite", "Gonzalez Natalia"),
        _fila("Survey Monkey", "Pollora Agostinas", tipo_info="Satisfacción de cliente", acuerdo="si"),
        _fila("HikVision", "Galvan Diego", nda="https://www.hikvision.com/privacy"),
        _fila("Zoom", "Gonzalez Natalia", servicio="Videollamadas", tipo_info="Reuniones", acuerdo="Sí"),
        _fila("Slack", "Vega Federico", servicio="Chat", tipo_info="Mensajes", acuerdo="N/A"),
        _fila("Jira", "Vega Federico", servicio="Tickets", tipo_info="Proyectos", acuerdo="No"),
        _fila("", ""),
        _fila("ODOO", "Vega Federico"),  # repetida en el Sheet
    ]

    vista = client.post(f"{BASE}/importaciones", headers=entorno["headers"])

    assert vista.status_code == 201, vista.text
    datos = vista.json()
    assert entorno["pedidos"] == [
        ("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit", "Listado Proveedores")
    ]
    assert (datos["filas_leidas"], datos["altas"], datos["sin_cambios"], datos["cambios_referente"]) == (7, 1, 1, 1)
    assert (datos["rechazadas"], datos["sin_definir"], datos["faltan_adjunto"]) == (4, 0, 1)
    por_nombre = {f["nombre"]: f for f in datos["filas"]}
    assert por_nombre["odoo"]["accion"] == "sin_cambios"
    assert (datos["se_agregan"], datos["ya_estan"], datos["de_baja"]) == (3, 0, 0)  # la evaluación arranca vacía
    cambio = por_nombre["Google Suite"]
    assert cambio["accion"] == "cambio_referente"
    assert (cambio["referente_anterior"], cambio["referente_nuevo"]) == ("Vega, Federico Martín", "Gonzalez, Natalia")
    # Las altas tienen que traer los datos obligatorios del form; si no, se rechazan con el motivo
    assert {
        n: (f["accion"], f["evaluacion"], f["motivo"]) for n, f in por_nombre.items() if f["accion"] == "rechazada"
    } == {
        "Survey Monkey": (
            "rechazada",
            "no_entra",
            "Falta: usuario referente («Pollora Agostinas» no está en la nómina), servicio / bien provisto",
        ),
        "HikVision": (
            "rechazada",
            "no_entra",
            "Falta: usuario referente («Galvan Diego» no está en la nómina), "
            "servicio / bien provisto, tipo de información que manejan, "
            "¿hay acuerdo de servicio firmado? (Sí o No)",
        ),
        "Slack": ("rechazada", "no_entra", "Falta: ¿hay acuerdo de servicio firmado? (Sí o No)"),
        "Jira": ("rechazada", "no_entra", "Falta: política de seguridad / NDA (sin acuerdo firmado es obligatoria)"),
    }
    assert por_nombre["Survey Monkey"]["fila_sheet"] == 5
    # Con acuerdo firmado entra, pero el archivo se pide después desde el form
    zoom = por_nombre["Zoom"]
    assert (zoom["accion"], zoom["evaluacion"], zoom["falta_adjunto"], zoom["motivo"]) == (
        "alta",
        "se_agrega",
        True,
        None,
    )
    assert db_session.query(RegistroProveedor).count() == 2  # la vista previa no escribe el registro


def test_confirmar_aplica_altas_cambios_marcados_y_asigna_a_la_activa(client, db_session, entorno):
    google = RegistroProveedor(
        empresa_id=entorno["empresa"].id, nombre="Google Suite", referente_empleado_id=entorno["vega"].id
    )
    webex = RegistroProveedor(
        empresa_id=entorno["empresa"].id, nombre="Webex", referente_empleado_id=entorno["vega"].id
    )
    db_session.add_all([google, webex])
    db_session.flush()
    evaluacion = _evaluacion(client, entorno)  # arranca vacía: los proveedores entran por el Sheet
    entorno["hoja"]["filas"] = [
        TITULO,
        ENCABEZADO,
        _fila("Google Suite", "Gonzalez Natalia"),
        _fila("Webex", "Gonzalez Natalia"),
        _fila(
            "Survey Monkey",
            "Vega Federico",
            servicio="Encuestas",
            tipo_info="Opiniones",
            acuerdo="No",
            nda="https://www.surveymonkey.com/privacy",
        ),
    ]
    vista = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()
    marcado = next(f["id"] for f in vista["filas"] if f["nombre"] == "Google Suite")

    resultado = client.post(
        f"{BASE}/importaciones/{vista['id']}/confirmar",
        headers=entorno["headers"],
        json={"cambios_confirmados": [marcado]},
    )

    assert resultado.status_code == 200, resultado.text
    assert resultado.json() == {"altas": 1, "cambios_referente": 1, "asignados": 3, "ya_estaban": 0, "rechazadas": 0}
    db_session.expire_all()
    assert db_session.get(RegistroProveedor, google.id).referente_empleado_id == entorno["gonzalez"].id
    assert db_session.get(RegistroProveedor, webex.id).referente_empleado_id == entorno["vega"].id  # sin marcar
    nuevo = db_session.query(RegistroProveedor).filter_by(nombre="Survey Monkey").one()
    assert (nuevo.referente_empleado_id, nuevo.servicio_provisto, nuevo.acuerdo_servicio, nuevo.tipo) == (
        entorno["vega"].id,
        "Encuestas",
        "No",
        "sin_clasificar",
    )
    items = {
        i.proveedor_id: i for i in db_session.query(EvaluacionItem).filter_by(evaluacion_id=uuid.UUID(evaluacion["id"]))
    }
    assert set(items) == {google.id, webex.id, nuevo.id}
    assert items[google.id].evaluador_empleado_id == entorno["gonzalez"].id
    # La vista previa temporal se borró y la importación quedó auditada
    assert db_session.query(ImportacionProveedores).count() == 0
    assert db_session.query(ImportacionFila).count() == 0
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="confirmar_importacion").one()
    assert evento.despues == {
        "altas": 1,
        "cambios_referente": 1,
        "asignados": 3,
        "ya_estaban": 0,
        "rechazadas": 0,
        "filas_leidas": 3,
    }


def test_las_altas_rechazadas_no_entran_ni_al_registro_ni_a_la_evaluacion(client, db_session, entorno):
    evaluacion = _evaluacion(client, entorno)
    entorno["hoja"]["filas"] = [
        TITULO,
        ENCABEZADO,
        _fila("Survey Monkey", "Vega Federico", servicio="Encuestas"),  # le faltan datos
        _fila("Zoom", "Gonzalez Natalia", servicio="Videollamadas", tipo_info="Reuniones", acuerdo="Si"),
        _fila(
            "Slack",
            "Vega Federico",
            servicio="Chat",
            tipo_info="Mensajes",
            acuerdo="No",
            nda="https://slack.com/privacy",
        ),
    ]
    vista = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()
    assert (vista["altas"], vista["rechazadas"]) == (2, 1)
    # Natalia deja la nómina entre la vista previa y la confirmación: Zoom ya no tiene referente
    entorno["gonzalez"].activo = False
    db_session.commit()

    resultado = client.post(f"{BASE}/importaciones/{vista['id']}/confirmar", headers=entorno["headers"], json={})

    assert resultado.json() == {"altas": 1, "cambios_referente": 0, "asignados": 1, "ya_estaban": 0, "rechazadas": 2}
    db_session.expire_all()
    slack = db_session.query(RegistroProveedor).one()
    assert (slack.nombre, slack.referente_empleado_id, slack.acuerdo_servicio) == ("Slack", entorno["vega"].id, "No")
    assert [
        i.proveedor_id for i in db_session.query(EvaluacionItem).filter_by(evaluacion_id=uuid.UUID(evaluacion["id"]))
    ] == [slack.id]


def test_con_los_proveedores_ya_registrados_igual_los_suma_a_la_evaluacion(client, db_session, entorno):
    """El caso de una evaluación nueva: 0 altas en el registro, pero todos entran a la evaluación."""

    def registrado(nombre, activo=True):
        p = RegistroProveedor(
            empresa_id=entorno["empresa"].id, nombre=nombre, activo=activo, referente_empleado_id=entorno["vega"].id
        )
        db_session.add(p)
        return p

    odoo, google, _webmail = registrado("ODOO"), registrado("Google Suite"), registrado("Webmail", activo=False)
    db_session.flush()
    evaluacion = _evaluacion(client, entorno)
    campania = db_session.get(EvaluacionProveedores, uuid.UUID(evaluacion["id"]))
    asegurar_item(db_session, campania, google, Actor(usuario_id=None, email="admin@dicsys.com"))  # agregado a mano
    db_session.commit()
    entorno["hoja"]["filas"] = [
        TITULO,
        ENCABEZADO,
        _fila("ODOO", "Vega Federico"),
        _fila("Google Suite", "Vega Federico"),
        _fila("Webmail", "Vega Federico"),
    ]

    vista = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()

    # En el registro no cambia nada; en la evaluación, uno se agrega, uno ya está y el de baja no entra
    assert (vista["altas"], vista["sin_cambios"], vista["cambios_referente"]) == (0, 3, 0)
    assert (vista["se_agregan"], vista["ya_estan"], vista["de_baja"]) == (1, 1, 1)
    assert {f["nombre"]: f["evaluacion"] for f in vista["filas"]} == {
        "ODOO": "se_agrega",
        "Google Suite": "ya_esta",
        "Webmail": "de_baja",
    }

    resultado = client.post(f"{BASE}/importaciones/{vista['id']}/confirmar", headers=entorno["headers"], json={})
    assert resultado.json() == {"altas": 0, "cambios_referente": 0, "asignados": 1, "ya_estaban": 1, "rechazadas": 0}
    db_session.expire_all()
    en_la_evaluacion = {
        i.proveedor_id for i in db_session.query(EvaluacionItem).filter_by(evaluacion_id=campania.id, deleted_at=None)
    }
    assert en_la_evaluacion == {odoo.id, google.id}


def test_no_toca_evaluaciones_anteriores(client, db_session, entorno):
    anterior = _evaluacion(client, entorno, "2025")
    _evaluacion(client, entorno, "2026")
    entorno["hoja"]["filas"] = [ENCABEZADO, _fila("ODOO", "Vega Federico")]
    vista = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()
    client.post(f"{BASE}/importaciones/{vista['id']}/confirmar", headers=entorno["headers"], json={})

    assert db_session.query(EvaluacionItem).filter_by(evaluacion_id=uuid.UUID(anterior["id"])).count() == 0


def test_cancelar_borra_la_vista_previa_y_una_nueva_reemplaza_a_la_abandonada(client, db_session, entorno):
    _evaluacion(client, entorno)
    entorno["hoja"]["filas"] = [ENCABEZADO, _fila("ODOO", "Vega Federico")]
    primera = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()
    segunda = client.post(f"{BASE}/importaciones", headers=entorno["headers"]).json()
    assert db_session.query(ImportacionProveedores).count() == 1
    assert client.get(f"{BASE}/importaciones/{primera['id']}", headers=entorno["headers"]).status_code == 404

    assert client.delete(f"{BASE}/importaciones/{segunda['id']}", headers=entorno["headers"]).status_code == 200
    assert db_session.query(ImportacionProveedores).count() == 0
    assert db_session.query(RegistroProveedor).count() == 0


def test_sin_evaluacion_activa_no_se_importa(client, entorno):
    entorno["hoja"]["filas"] = [ENCABEZADO, _fila("ODOO", "Vega Federico")]
    respuesta = client.post(f"{BASE}/importaciones", headers=entorno["headers"])
    assert respuesta.status_code == 422 and "evaluación activa" in respuesta.json()["detail"]
    assert entorno["pedidos"] == []


def test_encabezado_incompleto_no_escribe_nada(client, db_session, entorno):
    _evaluacion(client, entorno)
    entorno["hoja"]["filas"] = [["", "Razón Social", "Servicio"], ["", "ODOO", "ERP"]]
    respuesta = client.post(f"{BASE}/importaciones", headers=entorno["headers"])
    assert respuesta.status_code == 422 and "Referente Interno" in respuesta.json()["detail"]
    assert db_session.query(ImportacionProveedores).count() == 0


def test_error_de_google_llega_como_mensaje(client, entorno, monkeypatch):
    _evaluacion(client, entorno)

    def falla(*_, **__):
        raise google_sheets.ErrorSheets("La cuenta de servicio no tiene acceso al Sheet")

    monkeypatch.setattr(google_sheets, "leer_hoja", falla)
    respuesta = client.post(f"{BASE}/importaciones", headers=entorno["headers"])
    assert respuesta.status_code == 422 and "no tiene acceso" in respuesta.json()["detail"]
