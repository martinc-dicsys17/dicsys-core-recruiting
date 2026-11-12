"""Seguimiento y avisos de la evaluación de proveedores: envío manual y job diario."""

from datetime import datetime, time, timedelta

import pytest

from backend.modules.administracion import evaluacion_proveedores_avisos as avisos
from backend.modules.administracion.proveedores_comun import ZONA_ARGENTINA, hoy_argentina
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    ProveedoresAuditoria,
    ProveedoresAviso,
    ProveedoresConfiguracion,
    RegistroProveedor,
)
from backend.modules.tareas import cola
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/evaluaciones-proveedores"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(data_factory, db_session):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_config"])
    vega = data_factory.empleado(empresa, nombre="Federico", apellido="Vega", email_corporativo="fvega@dicsys.com")
    externo = data_factory.empleado(empresa, nombre="Ana", apellido="Paz", email_corporativo="ana@gmail.com")
    al_dia = data_factory.empleado(empresa, nombre="Luis", apellido="Sosa", email_corporativo="lsosa@dicsys.ai")
    hoy = hoy_argentina()
    evaluacion = EvaluacionProveedores(
        empresa_id=empresa.id,
        periodo="2026",
        fecha_apertura=hoy - timedelta(days=4),
        fecha_cierre=hoy + timedelta(days=10),
    )
    db_session.add(evaluacion)
    db_session.flush()
    for nombre, empleado, evaluado in (
        ("ODOO", vega, False),
        ("Webex", vega, False),
        ("Claude", externo, False),
        ("Banco", al_dia, True),
        ("Sin dueño", None, False),
    ):
        proveedor = RegistroProveedor(
            empresa_id=empresa.id, nombre=nombre, referente_empleado_id=empleado.id if empleado else None
        )
        db_session.add(proveedor)
        db_session.flush()
        db_session.add(
            EvaluacionItem(
                empresa_id=empresa.id,
                evaluacion_id=evaluacion.id,
                proveedor_id=proveedor.id,
                evaluador_empleado_id=empleado.id if empleado else None,
                mal_manejo="No" if evaluado else None,
                evaluado_at=datetime(2026, 1, 1) if evaluado else None,
            )
        )
    configuracion = ProveedoresConfiguracion(
        empresa_id=empresa.id,
        sheet_hoja="Listado Proveedores",
        canal_email=True,
        email_cc="seguridad@dicsys.com",
        canal_webex_personal=True,
        canal_webex_canal=True,
        webex_room_id="room-seguridad",
        hora_envio=time(9, 0),
    )
    db_session.add(configuracion)
    db_session.flush()
    return {
        "empresa": empresa,
        "headers": auth_headers(usuario, empresa),
        "evaluacion": evaluacion,
        "configuracion": configuracion,
        "vega": vega,
        "externo": externo,
        "al_dia": al_dia,
        "hoy": hoy,
    }


def test_seguimiento_por_evaluador_con_vista_previa(client, entorno):
    datos = client.get(f"{BASE}/seguimiento", headers=entorno["headers"]).json()

    assert datos["canales"] == ["email", "webex_personal", "webex_canal"]
    assert datos["sin_evaluador"] == ["Sin dueño"]
    filas = {f["evaluador"]["nombre"]: f for f in datos["evaluadores"]}
    assert filas["Vega, Federico"]["pendientes"] == ["ODOO", "Webex"]
    assert filas["Sosa, Luis"]["mensaje"] is None and filas["Sosa, Luis"]["evaluados"] == 1
    mensaje = filas["Vega, Federico"]["mensaje"]
    assert mensaje["asunto"] == "Evaluación de proveedores 2026: 2 pendientes"
    assert "Hola Federico" in mensaje["cuerpo"] and "  - ODOO" in mensaje["cuerpo"]


def _filas_del_room(tarjeta):
    """(evaluador, pendientes) de la tabla de la tarjeta del room, sin el encabezado."""
    tabla = next(b for b in tarjeta["body"] if b["type"] == "Container" and b.get("style") != "warning")
    filas = [[c["items"][0]["text"] for c in fila["columns"]] for fila in tabla["items"]]
    assert filas[0] == ["Evaluador", "Pendientes"]
    return [tuple(f) for f in filas[1:]]


def test_envio_manual_por_cada_canal_con_cc_y_solo_a_mails_corporativos(
    client, db_session, entorno, fake_email, fake_webex
):
    elegidos = [str(entorno["vega"].id), str(entorno["externo"].id), str(entorno["al_dia"].id)]

    resultados = client.post(
        f"{BASE}/seguimiento/avisar", headers=entorno["headers"], json={"evaluadores": elegidos}
    ).json()

    por_clave = {(r["evaluador"], r["canal"]): r for r in resultados}
    assert por_clave[("Vega, Federico", "email")]["enviado"] is True
    assert por_clave[("Vega, Federico", "webex_personal")]["enviado"] is True
    assert por_clave[("Paz, Ana", "email")]["enviado"] is False
    assert "corporativo" in por_clave[("Paz, Ana", "email")]["detalle"]
    assert por_clave[("Sosa, Luis", "-")]["detalle"] == "No tiene pendientes"
    assert por_clave[("Canal de Webex", "webex_canal")]["enviado"] is True

    assert fake_email.messages[0]["to"] == ["fvega@dicsys.com", "seguridad@dicsys.com"]
    assert "ODOO" in fake_email.messages[0]["html"]
    # Por Webex, solo tarjetas (D-95)
    assert {m["kind"] for m in fake_webex.messages} == {"card"}
    personales = [m for m in fake_webex.messages if m.get("person_email")]
    assert [m["person_email"] for m in personales] == ["fvega@dicsys.com"]
    assert personales[0]["text"] == "Evaluación de proveedores 2026: 2 pendientes"
    assert [i["text"] for i in personales[0]["card"]["body"][3]["items"]] == ["• ODOO", "• Webex"]
    canal = next(m for m in fake_webex.messages if m.get("room_id"))
    assert canal["room_id"] == "room-seguridad"
    assert ("Vega, Federico", "2") in _filas_del_room(canal["card"])
    assert db_session.query(ProveedoresAviso).filter_by(enviado=True).count() == 3
    assert db_session.query(ProveedoresAviso).filter_by(enviado=False).count() == 2  # Paz: email y Webex


def test_sin_canales_activos_no_se_envia(client, db_session, entorno, fake_email):
    configuracion = entorno["configuracion"]
    configuracion.canal_email = configuracion.canal_webex_personal = configuracion.canal_webex_canal = False
    db_session.flush()
    respuesta = client.post(
        f"{BASE}/seguimiento/avisar", headers=entorno["headers"], json={"evaluadores": [str(entorno["vega"].id)]}
    )
    assert respuesta.status_code == 422 and fake_email.messages == []


# ─── Prueba de canales ──────────────────────────────────────────────────────────


def _probar(client, entorno, empleado, **canales):
    return client.post(
        f"{BASE}/seguimiento/probar", headers=entorno["headers"], json={"evaluador_id": str(empleado.id), **canales}
    )


def test_la_prueba_le_llega_al_evaluador_marcada_y_por_los_canales_de_pantalla(
    client, db_session, entorno, fake_email, fake_webex
):
    # Lo guardado tiene todo prendido; en pantalla, solo el email (con otro CC) y el room
    respuesta = _probar(
        client,
        entorno,
        entorno["vega"],
        canal_email=True,
        email_cc="it@dicsys.com",
        canal_webex_canal=True,
        webex_room_id="room-prueba",
    )

    assert respuesta.status_code == 200, respuesta.text
    por_canal = {r["canal"]: r for r in respuesta.json()}
    assert set(por_canal) == {"email", "webex_canal"} and all(r["enviado"] for r in por_canal.values())
    correo = fake_email.messages[0]
    assert correo["to"] == ["fvega@dicsys.com", "it@dicsys.com"]
    assert correo["subject"] == "[Prueba] Evaluación de proveedores 2026: 2 pendientes"
    assert "[Prueba] Mensaje de prueba" in correo["html"] and "ODOO" in correo["html"]
    # Al room va la tarjeta, marcada
    [tarjeta] = fake_webex.messages
    assert tarjeta["room_id"] == "room-prueba"
    assert tarjeta["kind"] == "card" and tarjeta["text"] == "[Prueba] Evaluación de proveedores 2026"
    cuerpo = tarjeta["card"]["body"]
    assert (
        cuerpo[0]["text"] == "Evaluación de proveedores 2026"
        and "Quedan 3 evaluaciones pendientes" in cuerpo[1]["text"]
    )
    assert cuerpo[2]["style"] == "warning" and "[Prueba]" in cuerpo[2]["items"][0]["text"]
    assert _filas_del_room(tarjeta["card"]) == [("Paz, Ana", "1"), ("Vega, Federico", "2")]
    # La tabla ocupa todo el ancho: el nombre se estira y el número va a la derecha
    fila = cuerpo[3]["items"][1]
    assert fila["columns"][0]["width"] == "stretch" and fila["columns"][1]["width"] == "auto"
    assert fila["columns"][1]["items"][0]["horizontalAlignment"] == "Right"
    assert tarjeta["card"]["actions"][0]["url"].endswith("/administracion/evaluaciones-proveedores")
    assert [r["canal"] for r in respuesta.json()] == ["email", "webex_canal"]
    # No cuenta como aviso (no frena los del job); queda en la auditoría
    assert db_session.query(ProveedoresAviso).count() == 0
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="probar_canales").one()
    assert evento.despues == {
        "evaluador": "Vega, Federico",
        "canales": ["email", "webex_canal"],
        "enviados": 2,
        "fallidos": 0,
    }


def test_la_prueba_avisa_si_no_tiene_pendientes_y_respeta_el_mail_corporativo(client, entorno, fake_email, fake_webex):
    al_dia = _probar(client, entorno, entorno["al_dia"], canal_webex_personal=True).json()
    assert [r["enviado"] for r in al_dia] == [True]
    [tarjeta] = fake_webex.messages
    assert tarjeta["kind"] == "card" and tarjeta["person_email"] == "lsosa@dicsys.ai"
    assert tarjeta["text"] == "[Prueba] Evaluación de proveedores 2026: 0 pendientes"
    assert "Hoy no tiene pendientes" in tarjeta["card"]["body"][2]["items"][0]["text"]
    assert tarjeta["card"]["body"][1]["text"].startswith("Tenés 0 pendientes")

    externo = _probar(client, entorno, entorno["externo"], canal_email=True).json()
    assert externo[0]["enviado"] is False and "corporativo" in externo[0]["detalle"]
    assert fake_email.messages == []


def test_tarjeta_del_evaluador_con_sus_pendientes_y_el_boton_al_tablero(entorno):
    tarjeta = avisos.tarjeta_evaluador(entorno["evaluacion"], entorno["vega"], ["ODOO", "Webex"])

    assert tarjeta["type"] == "AdaptiveCard" and tarjeta["version"] == "1.3"
    titulo, subtitulo, saludo, lista = tarjeta["body"]  # sin nota de prueba
    assert titulo["text"] == "Evaluación de proveedores 2026"
    assert subtitulo["text"].startswith("Tenés 2 pendientes · cierra el ")
    assert saludo["text"].startswith("Hola Federico")
    assert [i["text"] for i in lista["items"]] == ["• ODOO", "• Webex"]
    assert tarjeta["actions"][0] == {
        "type": "Action.OpenUrl",
        "title": "Ir a Evaluación de Proveedores",
        "url": tarjeta["actions"][0]["url"],
    }


def test_mail_del_evaluador_con_la_marca_y_los_datos_escapados(entorno):
    entorno["vega"].nombre = "Federico <b>"
    cuerpo = avisos.html_evaluador(entorno["evaluacion"], entorno["vega"], ["ODOO", "A&B Seguros"])

    assert "Dicsys Core" in cuerpo or avisos.settings.app_name in cuerpo  # la marca en el encabezado
    assert "Evaluación de proveedores 2026" in cuerpo and "Tenés 2 pendientes" in cuerpo
    assert "Federico &lt;b&gt;" in cuerpo and "A&amp;B Seguros" in cuerpo  # todo lo que viene de datos, escapado
    assert "/administracion/evaluaciones-proveedores" in cuerpo and "Ir a Evaluación de Proveedores" in cuerpo
    assert "[Prueba]" not in cuerpo
    assert "#0967D2" in cuerpo and "#4F46E5" not in cuerpo and "#7C3AED" not in cuerpo  # azul Dicsys, sin violeta
    con_nota = avisos.html_evaluador(entorno["evaluacion"], entorno["vega"], [], "[Prueba] Mensaje de prueba")
    assert "[Prueba] Mensaje de prueba" in con_nota and "Sin pendientes" in con_nota


@pytest.mark.parametrize(
    "canales, mensaje",
    [
        ({}, "al menos un canal"),
        ({"canal_webex_canal": True}, "ID del room"),
    ],
)
def test_la_prueba_pide_canales_validos(client, entorno, fake_email, canales, mensaje):
    respuesta = _probar(client, entorno, entorno["vega"], **canales)
    assert respuesta.status_code == 422 and mensaje in respuesta.text and fake_email.messages == []


def test_la_prueba_solo_con_evaluadores_de_la_evaluacion_vigente(client, data_factory, entorno, fake_email):
    ajeno = data_factory.empleado(entorno["empresa"], nombre="Sin", apellido="Asignar")
    respuesta = _probar(client, entorno, ajeno, canal_email=True)
    assert respuesta.status_code == 422 and "no evalúa" in respuesta.json()["detail"]


ERROR_TEAM = (
    '{"message":"Unable to post message to room: \\"User 0000 must join the team conversation before '
    'posting activities\\"","errors":[],"trackingId":"ROUTERGW_x"}'
)


def test_la_prueba_muestra_el_error_de_webex_legible(client, entorno, monkeypatch, fake_webex):
    def falla_en_el_room(tarjeta, fallback_text="", **destino):
        if destino.get("room_id"):
            return {"success": False, "status_code": 403, "error": ERROR_TEAM}
        return {"success": True}

    monkeypatch.setattr(fake_webex, "send_card", falla_en_el_room)  # el adaptador, no el proxy

    resultados = _probar(
        client, entorno, entorno["vega"], canal_webex_personal=True, canal_webex_canal=True, webex_room_id="room-team"
    ).json()

    por_canal = {r["canal"]: r for r in resultados}
    assert por_canal["webex_personal"]["enviado"] is True
    assert por_canal["webex_canal"]["detalle"] == (
        "El bot de Webex no es miembro del equipo (team) de ese room: hay que invitarlo al equipo"
    )


# ─── Job diario ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "config, dias_desde_apertura, dias_hasta_cierre, esperado",
    [
        ({"aviso_apertura": True}, 0, 10, "apertura"),
        ({"aviso_previo_cierre": True}, 5, 1, "previo_cierre"),
        ({"recordar_cada_dias": 2}, 4, 6, "recordatorio"),
        ({"recordar_cada_dias": 2}, 3, 6, None),
        ({"recordar_cada_dias": 1}, 0, 6, None),  # el día de apertura es del aviso de apertura
        ({"aviso_apertura": True, "recordar_cada_dias": 1}, 0, 6, "apertura"),
        ({}, 4, 6, None),  # todo apagado: no manda nada
        ({"aviso_previo_cierre": True}, 5, -1, None),  # ya cerró
    ],
)
def test_motivo_del_dia(config, dias_desde_apertura, dias_hasta_cierre, esperado):
    hoy = hoy_argentina()
    configuracion = ProveedoresConfiguracion(
        **{"aviso_apertura": False, "aviso_previo_cierre": False, "recordar_cada_dias": None, **config}
    )
    evaluacion = EvaluacionProveedores(
        periodo="x",
        fecha_apertura=hoy - timedelta(days=dias_desde_apertura),
        fecha_cierre=hoy + timedelta(days=dias_hasta_cierre),
    )
    assert avisos.motivo_del_dia(configuracion, evaluacion, hoy) == esperado


def test_job_manda_una_vez_por_dia_y_respeta_la_hora(db_session, entorno, fake_email, fake_webex):
    entorno["configuracion"].recordar_cada_dias = 2
    db_session.flush()
    hoy = entorno["hoy"]
    temprano = datetime.combine(hoy, time(8, 59), tzinfo=ZONA_ARGENTINA)
    a_horario = datetime.combine(hoy, time(9, 1), tzinfo=ZONA_ARGENTINA)

    assert avisos.procesar_avisos_del_dia(db_session, temprano)["encolados"] == 0
    primero = avisos.procesar_avisos_del_dia(db_session, a_horario)
    segundo = avisos.procesar_avisos_del_dia(db_session, a_horario + timedelta(minutes=1))

    # Vega por email y Webex, y el resumen al room; Paz no tiene mail corporativo y no se encola
    assert primero == {"empresas": 1, "encolados": 3, "errores": []}
    assert segundo == {"empresas": 0, "encolados": 0, "errores": []}
    assert fake_email.messages == []  # lo despacha la cola del motor de tareas
    registros = db_session.query(ProveedoresAviso).filter_by(evaluacion_id=entorno["evaluacion"].id).all()
    assert {a.motivo for a in registros} == {"recordatorio"}
    assert sum(1 for a in registros if a.error == avisos.EN_COLA) == 3

    assert cola.despachar(db_session, pausar=False) == {"enviados": 3, "reintentos": 0, "fallidos": 0}
    assert len(fake_email.messages) == 1 and fake_email.messages[0]["to"] == [
        "fvega@dicsys.com",
        "seguridad@dicsys.com",
    ]
    assert {m["kind"] for m in fake_webex.messages} == {"card"} and len(fake_webex.messages) == 2
    for registro in registros:
        db_session.refresh(registro)
    assert sum(1 for a in registros if a.enviado) == 3  # la cola le avisó al módulo
    assert cola.despachar(db_session, pausar=False)["enviados"] == 0  # sin duplicados


def test_job_con_los_checks_apagados_no_manda_nada(db_session, entorno, fake_email, fake_webex):
    hoy = entorno["hoy"]
    resultado = avisos.procesar_avisos_del_dia(db_session, datetime.combine(hoy, time(12, 0), tzinfo=ZONA_ARGENTINA))
    assert resultado == {"empresas": 0, "encolados": 0, "errores": []}
    assert fake_email.messages == [] and fake_webex.messages == []
