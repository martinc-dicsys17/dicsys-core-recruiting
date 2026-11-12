"""Auto-generación anual de la evaluación de proveedores: configuración, tarea y reglas de una vez por año."""

from datetime import date, datetime

import pytest

from backend.modules.administracion.evaluacion_proveedores_services import AutogeneracionService, EvaluacionService
from backend.modules.administracion.evaluacion_proveedores_tareas import autogeneracion_anual
from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    ProveedoresAuditoria,
    ProveedoresConfiguracion,
    RegistroProveedor,
)
from backend.modules.tareas.registro import TAREAS
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/evaluaciones-proveedores"
ADMIN = Actor(usuario_id=None, email="admin@dicsys.com")
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(data_factory, db_session):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_config"])
    vega = data_factory.empleado(empresa, nombre="Federico", apellido="Vega")

    def proveedor(nombre, activo=True, referente=vega, eliminado=False):
        p = RegistroProveedor(
            empresa_id=empresa.id,
            nombre=nombre,
            activo=activo,
            referente_empleado_id=referente.id if referente else None,
        )
        if eliminado:
            p.deleted_at = datetime(2026, 1, 1)
        db_session.add(p)
        db_session.flush()
        return p

    def configurar(inicio=(1, 3), fin=(30, 4), activa=True):
        configuracion = db_session.query(ProveedoresConfiguracion).filter_by(empresa_id=empresa.id).first()
        if configuracion is None:
            configuracion = ProveedoresConfiguracion(empresa_id=empresa.id)
            db_session.add(configuracion)
        configuracion.auto_generar = activa
        configuracion.auto_inicio_dia, configuracion.auto_inicio_mes = inicio
        configuracion.auto_fin_dia, configuracion.auto_fin_mes = fin
        db_session.flush()
        return configuracion

    return {
        "empresa": empresa,
        "headers": auth_headers(usuario, empresa),
        "vega": vega,
        "proveedor": proveedor,
        "configurar": configurar,
    }


def _evaluaciones(db_session, entorno):
    return db_session.query(EvaluacionProveedores).filter_by(empresa_id=entorno["empresa"].id, deleted_at=None).all()


# ─── Configuración por API ──────────────────────────────────────────────────────


def test_arranca_apagada_y_se_configura_por_la_api(client, db_session, entorno):
    url = f"{BASE}/autogeneracion"
    assert client.get(url, headers=entorno["headers"]).json() == {
        "activa": False,
        "inicio_dia": None,
        "inicio_mes": None,
        "fin_dia": None,
        "fin_mes": None,
        "ultimo_periodo": None,
        "proxima": None,
    }

    respuesta = client.put(
        url,
        headers=entorno["headers"],
        json={"activa": True, "inicio_dia": 1, "inicio_mes": 3, "fin_dia": 30, "fin_mes": 4},
    )

    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert (datos["activa"], datos["inicio_dia"], datos["inicio_mes"], datos["fin_dia"], datos["fin_mes"]) == (
        True,
        1,
        3,
        30,
        4,
    )
    assert datos["proxima"]["fecha_apertura"][5:] == "03-01" and datos["proxima"]["fecha_cierre"][5:] == "04-30"
    evento = db_session.query(ProveedoresAuditoria).filter_by(accion="configurar_autogeneracion").one()
    assert evento.despues["activa"] is True and evento.despues["inicio_mes"] == 3


@pytest.mark.parametrize(
    "cuerpo, mensaje",
    [
        ({"activa": True}, "Para activar la auto-generación hay que indicar la fecha de inicio y la de fin"),
        ({"inicio_dia": 31, "inicio_mes": 4}, "La fecha de inicio no existe: 31/04"),
        ({"fin_dia": 30, "fin_mes": 2}, "La fecha de fin no existe: 30/02"),
        ({"inicio_dia": 1}, "La fecha de inicio necesita el día y el mes"),
    ],
)
def test_fechas_invalidas_se_rechazan(client, entorno, cuerpo, mensaje):
    respuesta = client.put(f"{BASE}/autogeneracion", headers=entorno["headers"], json=cuerpo)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == mensaje


def test_sin_el_permiso_de_configuracion_no_se_ve(client, data_factory, entorno):
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, entorno["empresa"])
    data_factory.asignar_grupo(usuario, grupo, entorno["empresa"])
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.evaluacion_proveedores"])
    assert client.get(f"{BASE}/autogeneracion", headers=auth_headers(usuario, entorno["empresa"])).status_code == 403


# ─── La tarea ───────────────────────────────────────────────────────────────────


def test_al_llegar_la_fecha_de_inicio_crea_la_evaluacion_con_los_activos(db_session, entorno):
    odoo = entorno["proveedor"]("ODOO")
    sin_referente = entorno["proveedor"]("Sin dueño", referente=None)
    entorno["proveedor"]("De baja", activo=False)
    entorno["proveedor"]("Eliminado", eliminado=True)
    configuracion = entorno["configurar"]()
    anterior = EvaluacionService.crear(
        db_session,
        entorno["empresa"].id,
        {"periodo": "2025", "fecha_apertura": date(2025, 3, 1), "fecha_cierre": date(2025, 4, 30)},
        ADMIN,
    )

    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 2, 28)) is None
    assert configuracion.auto_ultimo_periodo is None  # todavía no llegó: no marca el año

    evaluacion = AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 3, 1))

    assert (evaluacion.periodo, evaluacion.fecha_apertura, evaluacion.fecha_cierre) == (
        "2026",
        date(2026, 3, 1),
        date(2026, 4, 30),
    )
    items = {i.proveedor_id: i for i in db_session.query(EvaluacionItem).filter_by(evaluacion_id=evaluacion.id)}
    assert set(items) == {odoo.id, sin_referente.id}  # todos los activos; ni los de baja ni los eliminados
    assert items[odoo.id].evaluador_empleado_id == entorno["vega"].id
    db_session.refresh(anterior)
    assert anterior.reemplazada_at is not None  # reemplaza a la vigente, como la creación manual
    assert configuracion.auto_ultimo_periodo == "2026"
    evento = db_session.query(ProveedoresAuditoria).filter_by(entidad_id=evaluacion.id, accion="crear").one()
    assert evento.usuario_email == "cron@sistema" and evento.despues["via"] == "autogeneracion"

    # Una sola vez por año: ni al día siguiente ni después de eliminarla
    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 3, 2)) is None
    EvaluacionService.eliminar(db_session, entorno["empresa"].id, evaluacion.id, ADMIN)
    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 3, 3)) is None
    assert [e.periodo for e in _evaluaciones(db_session, entorno)] == ["2025"]
    # El año siguiente vuelve a crear
    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2027, 3, 1)).periodo == "2027"


def test_si_la_evaluacion_del_anio_ya_existe_no_crea_otra(db_session, entorno):
    configuracion = entorno["configurar"]()
    EvaluacionService.crear(
        db_session,
        entorno["empresa"].id,
        {"periodo": "2026", "fecha_apertura": date(2026, 2, 1), "fecha_cierre": date(2026, 2, 28)},
        ADMIN,
    )

    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 3, 1)) is None
    assert configuracion.auto_ultimo_periodo == "2026"
    assert [e.periodo for e in _evaluaciones(db_session, entorno)] == ["2026"]


def test_activada_con_la_ventana_ya_pasada_espera_al_anio_siguiente(db_session, entorno):
    configuracion = entorno["configurar"]()
    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 10, 7)) is None
    assert configuracion.auto_ultimo_periodo == "2026" and _evaluaciones(db_session, entorno) == []
    proxima = AutogeneracionService.como_dict(db_session, entorno["empresa"].id, configuracion, date(2026, 10, 7))[
        "proxima"
    ]
    assert proxima == {
        "periodo": "2027",
        "fecha_apertura": date(2027, 3, 1),
        "fecha_cierre": date(2027, 4, 30),
        "ya_existe": False,
    }


def test_apagada_no_hace_nada(db_session, entorno):
    configuracion = entorno["configurar"](activa=False)
    assert AutogeneracionService.generar_si_corresponde(db_session, configuracion, date(2026, 3, 1)) is None
    assert configuracion.auto_ultimo_periodo is None and _evaluaciones(db_session, entorno) == []


def test_fin_antes_del_inicio_cierra_al_anio_siguiente_y_el_29_de_febrero_cae_el_28(db_session, entorno):
    cruza = entorno["configurar"](inicio=(1, 12), fin=(31, 1))
    assert AutogeneracionService.ventana(cruza, 2026) == (date(2026, 12, 1), date(2027, 1, 31))
    bisiesto = entorno["configurar"](inicio=(29, 2), fin=(29, 2))
    assert AutogeneracionService.ventana(bisiesto, 2026) == (date(2026, 2, 28), date(2026, 2, 28))
    assert AutogeneracionService.ventana(bisiesto, 2028) == (date(2028, 2, 29), date(2028, 2, 29))


def test_la_tarea_es_continua_y_resume_lo_que_creo(db_session, entorno, monkeypatch):
    assert TAREAS["autogeneracion_evaluacion_proveedores"].continua is True
    entorno["proveedor"]("ODOO")
    entorno["configurar"]()
    procesar = AutogeneracionService.procesar
    monkeypatch.setattr(AutogeneracionService, "procesar", lambda db: procesar(db, date(2026, 3, 1)))

    assert autogeneracion_anual(db_session) == "Evaluación creada automáticamente: 2026 con 1 proveedor(es)"
    assert autogeneracion_anual(db_session) is None  # ya resuelto: no deja corrida
