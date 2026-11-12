"""Asignacion por empleados o equipos: costo por persona y confirmacion atomica."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event, func
from sqlalchemy.exc import IntegrityError

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia
from backend.modules.nomina.models import Empleado
from backend.modules.operaciones.models import Equipo, equipo_integrantes
from backend.tests.helpers.auth import auth_headers

LICENCIAS = "/api/v1/innovacion/licencias"
LOTE = f"{LICENCIAS}/lote"
EQUIPOS = f"{LICENCIAS}/equipos"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


def _empleado(db_session, empresa_id, numero, **cambios):
    empleado = Empleado(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        codigo=f"LOTE-{numero}",
        cuil=20800000000 + numero,
        dni=80000000 + numero,
        apellido=f"Persona {numero:04}",
        nombre="Prueba",
        activo=True,
    )
    for campo, valor in cambios.items():
        setattr(empleado, campo, valor)
    db_session.add(empleado)
    db_session.flush()
    return empleado


def _equipo(db_session, empresa_id, nombre, empleado_ids=(), **cambios):
    equipo = Equipo(id=uuid.uuid4(), empresa_id=empresa_id, nombre=nombre, activo=True, **cambios)
    db_session.add(equipo)
    db_session.flush()
    if empleado_ids:
        db_session.execute(
            equipo_integrantes.insert(),
            [{"equipo_id": equipo.id, "empleado_id": empleado_id} for empleado_id in empleado_ids],
        )
    return equipo


@pytest.fixture
def asignacion(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    empleados = [_empleado(db_session, empresa.id, numero) for numero in range(1, 4)]
    herramienta = Herramienta(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        nombre="Editor Pro",
        nombre_normalizado="editor pro",
        moneda="USD",
        activo=True,
    )
    db_session.add(herramienta)
    equipos = [
        _equipo(db_session, empresa.id, "Alpha", [empleados[0].id, empleados[1].id]),
        _equipo(db_session, empresa.id, "Beta", [empleados[0].id, empleados[2].id]),
        _equipo(db_session, empresa.id, "Vacio"),
    ]
    db_session.commit()
    return {
        "headers": auth_headers(usuario, empresa),
        "email": usuario.email,
        "empresa_id": empresa.id,
        "empleado_ids": [empleado.id for empleado in empleados],
        "herramienta_id": herramienta.id,
        "equipo_ids": [equipo.id for equipo in equipos],
        "datos": {
            "herramienta_id": str(herramienta.id),
            "empleado_ids": [str(empleado.id) for empleado in empleados],
            "fecha_inicio": date.today().isoformat(),
            "fecha_fin": None,
            "costo_mensual": "20.15",
            "moneda": "USD",
            "nro_pedido_compra": "OC-LOTE",
        },
    }


def test_equipos_incluyen_integrantes_elegibles_y_equipos_vacios(
    client,
    asignacion,
    db_session,
    data_factory,
):
    empresa_id = asignacion["empresa_id"]
    ajena = data_factory.empresa()
    excluidos = [
        _empleado(db_session, empresa_id, 11, activo=False),
        _empleado(db_session, empresa_id, 12, deleted_at=utc_now()),
        _empleado(db_session, ajena.id, 13),
    ]
    db_session.execute(
        equipo_integrantes.insert(),
        [{"equipo_id": asignacion["equipo_ids"][0], "empleado_id": empleado.id} for empleado in excluidos],
    )
    equipo_inactivo = _equipo(db_session, empresa_id, "Inactivo")
    equipo_inactivo.activo = False
    _equipo(db_session, empresa_id, "Borrado", deleted_at=utc_now())
    _equipo(db_session, ajena.id, "Ajeno", [asignacion["empleado_ids"][0]])
    db_session.flush()

    respuesta = client.get(EQUIPOS, headers=asignacion["headers"])
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert [equipo["nombre"] for equipo in cuerpo] == ["Alpha", "Beta", "Vacio"]
    assert {equipo["id"] for equipo in cuerpo} == {str(id_) for id_ in asignacion["equipo_ids"]}
    assert all(set(equipo) == {"id", "nombre", "empleado_ids"} for equipo in cuerpo)
    primero, segundo, tercero = map(str, asignacion["empleado_ids"])
    assert cuerpo[0]["empleado_ids"] == [primero, segundo]
    assert cuerpo[1]["empleado_ids"] == [primero, tercero]
    assert cuerpo[2]["empleado_ids"] == []


def test_lote_unifica_personas_de_varios_equipos_y_aplica_costo_individual(
    client,
    asignacion,
    db_session,
):
    equipos = client.get(EQUIPOS, headers=asignacion["headers"]).json()
    ids = [id_ for equipo in equipos for id_ in equipo["empleado_ids"]]
    ids.append(str(asignacion["empleado_ids"][0]))
    confirmaciones = []

    def registrar(_session):
        confirmaciones.append(True)

    event.listen(db_session, "after_commit", registrar)
    try:
        respuesta = client.post(
            LOTE,
            headers=asignacion["headers"],
            json={
                **asignacion["datos"],
                "empleado_ids": ids,
            },
        )
    finally:
        event.remove(db_session, "after_commit", registrar)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {"creadas": 3}
    assert len(confirmaciones) == 1
    licencias = db_session.query(Licencia).filter(Licencia.empresa_id == asignacion["empresa_id"]).all()
    assert {lic.empleado_id for lic in licencias} == set(asignacion["empleado_ids"])
    assert len(licencias) == 3
    assert all(lic.activa and lic.costo_mensual == Decimal("20.15") for lic in licencias)
    assert all(lic.updated_by == asignacion["email"] and lic.nro_pedido_compra == "OC-LOTE" for lic in licencias)
    assert sum(lic.costo_mensual for lic in licencias) == Decimal("60.45")


def test_equipo_y_lote_soportan_mas_de_doscientos_integrantes(client, asignacion, db_session):
    empleados = [_empleado(db_session, asignacion["empresa_id"], numero) for numero in range(1000, 1205)]
    db_session.execute(
        equipo_integrantes.insert(),
        [{"equipo_id": asignacion["equipo_ids"][0], "empleado_id": empleado.id} for empleado in empleados],
    )
    db_session.commit()
    equipo = client.get(EQUIPOS, headers=asignacion["headers"]).json()[0]
    assert len(equipo["empleado_ids"]) == 207
    respuesta = client.post(
        LOTE,
        headers=asignacion["headers"],
        json={
            **asignacion["datos"],
            "empleado_ids": equipo["empleado_ids"],
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json() == {"creadas": 207}
    cantidad, total = (
        db_session.query(func.count(Licencia.id), func.sum(Licencia.costo_mensual))
        .filter(
            Licencia.empresa_id == asignacion["empresa_id"],
        )
        .one()
    )
    assert cantidad == 207
    assert total == Decimal("20.15") * 207


@pytest.mark.parametrize("caso", ["ajeno", "inactivo", "borrado", "inexistente"])
def test_un_empleado_no_elegible_rechaza_todo_antes_de_insertar(
    client,
    asignacion,
    db_session,
    data_factory,
    caso,
):
    if caso == "inexistente":
        invalido_id = uuid.uuid4()
    else:
        empresa_id = data_factory.empresa().id if caso == "ajeno" else asignacion["empresa_id"]
        invalido = _empleado(db_session, empresa_id, 21)
        if caso == "inactivo":
            invalido.activo = False
        elif caso == "borrado":
            invalido.deleted_at = utc_now()
        invalido_id = invalido.id
    db_session.commit()
    inserts = []
    conexion = db_session.connection()

    def registrar(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("INSERT") and "innovacion_licencias" in statement:
            inserts.append(statement)

    event.listen(conexion, "before_cursor_execute", registrar)
    try:
        respuesta = client.post(
            LOTE,
            headers=asignacion["headers"],
            json={
                **asignacion["datos"],
                "empleado_ids": [str(asignacion["empleado_ids"][0]), str(invalido_id)],
            },
        )
    finally:
        event.remove(conexion, "before_cursor_execute", registrar)
    assert respuesta.status_code == 404, respuesta.text
    assert inserts == []
    assert db_session.query(Licencia).filter(Licencia.empresa_id == asignacion["empresa_id"]).count() == 0


@pytest.mark.parametrize("caso", ["ajena", "borrada", "inexistente"])
def test_herramienta_no_disponible_no_crea_licencias(client, asignacion, db_session, data_factory, caso):
    if caso == "inexistente":
        herramienta_id = uuid.uuid4()
    elif caso == "borrada":
        herramienta_id = asignacion["herramienta_id"]
        db_session.get(Herramienta, herramienta_id).deleted_at = utc_now()
    else:
        herramienta = Herramienta(
            id=uuid.uuid4(),
            empresa_id=data_factory.empresa().id,
            nombre="Editor ajeno",
            nombre_normalizado="editor ajeno",
            moneda="USD",
            activo=True,
        )
        db_session.add(herramienta)
        herramienta_id = herramienta.id
    db_session.commit()
    respuesta = client.post(
        LOTE,
        headers=asignacion["headers"],
        json={
            **asignacion["datos"],
            "herramienta_id": str(herramienta_id),
        },
    )
    assert respuesta.status_code == 404, respuesta.text
    assert db_session.query(Licencia).filter(Licencia.empresa_id == asignacion["empresa_id"]).count() == 0


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("empleado_ids", []),
        ("empleado_ids", ["no-es-uuid"]),
        ("fecha_inicio", "fecha-invalida"),
        ("fecha_fin", (date.today() - timedelta(days=1)).isoformat()),
        ("costo_mensual", "-0.01"),
        ("costo_mensual", "100000000.00"),
        ("costo_mensual", "1.234"),
        ("moneda", "EUR"),
    ],
)
def test_lote_valida_seleccion_fechas_e_importe(client, asignacion, db_session, campo, valor):
    respuesta = client.post(
        LOTE,
        headers=asignacion["headers"],
        json={
            **asignacion["datos"],
            campo: valor,
        },
    )
    assert respuesta.status_code == 422, respuesta.text
    assert db_session.query(Licencia).filter(Licencia.empresa_id == asignacion["empresa_id"]).count() == 0


@pytest.mark.parametrize("integridad,status", [(False, 500), (True, 409)])
def test_fallo_despues_de_insertar_revierte_el_lote_y_preserva_licencias_previas(
    client,
    asignacion,
    db_session,
    monkeypatch,
    integridad,
    status,
):
    previa = client.post(
        LICENCIAS,
        headers=asignacion["headers"],
        json={
            **{k: v for k, v in asignacion["datos"].items() if k != "empleado_ids"},
            "empleado_id": str(asignacion["empleado_ids"][0]),
        },
    )
    assert previa.status_code == 201, previa.text
    previa_id = uuid.UUID(previa.json()["id"])
    insertadas = []

    def fallar_al_confirmar():
        db_session.flush()
        insertadas.append(
            db_session.query(Licencia)
            .filter(
                Licencia.empresa_id == asignacion["empresa_id"],
            )
            .count()
        )
        if integridad:
            raise IntegrityError("INSERT", {}, RuntimeError("Fallo simulado"))
        raise RuntimeError("Fallo simulado despues de flush")

    monkeypatch.setattr(db_session, "commit", fallar_al_confirmar)
    respuesta = client.post(LOTE, headers=asignacion["headers"], json=asignacion["datos"])
    assert respuesta.status_code == status, respuesta.text
    assert insertadas == [4]
    assert {
        lic.id
        for lic in db_session.query(Licencia)
        .filter(
            Licencia.empresa_id == asignacion["empresa_id"],
        )
        .all()
    } == {previa_id}


def test_alta_individual_sigue_admitiendo_costo_cero_y_fechas_iguales(client, asignacion):
    respuesta = client.post(
        LICENCIAS,
        headers=asignacion["headers"],
        json={
            **{k: v for k, v in asignacion["datos"].items() if k != "empleado_ids"},
            "empleado_id": str(asignacion["empleado_ids"][0]),
            "costo_mensual": "0",
            "fecha_fin": date.today().isoformat(),
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["costo_mensual"] == 0
    assert respuesta.json()["activa"] is True


def test_lote_exige_permiso_de_licencias(client, asignacion, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.resumen"])
    respuesta = client.post(LOTE, headers=auth_headers(usuario, empresa), json=asignacion["datos"])
    assert respuesta.status_code == 403
