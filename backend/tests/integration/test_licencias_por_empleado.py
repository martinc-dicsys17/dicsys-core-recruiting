"""El listado agrupa por empleado: una fila por persona, no por licencia."""

import uuid
from datetime import date, timedelta

import pytest

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia, Proveedor
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado
from backend.modules.operaciones.models import Equipo, equipo_integrantes
from backend.tests.helpers.auth import auth_headers

POR_EMPLEADO = "/api/v1/innovacion/licencias/por-empleado"


@pytest.fixture
def escenario(db_session, data_factory):
    """Dos empleados: uno con dos licencias, otro con una. Mas una tercera herramienta."""
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])

    def empleado(codigo, apellido, nombre):
        registro = Empleado(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            codigo=codigo,
            cuil=int(f"2030{codigo[-4:]}"),
            apellido=apellido,
            nombre=nombre,
            dni=int(f"30{codigo[-6:]}"),
            activo=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db_session.add(registro)
        return registro

    proveedores = {}

    def proveedor(nombre):
        """Un proveedor por nombre, reusado entre herramientas."""
        if nombre not in proveedores:
            registro = Proveedor(
                id=uuid.uuid4(),
                empresa_id=empresa.id,
                nombre=nombre,
                nombre_normalizado=normalizar_nombre(nombre),
                activo=True,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db_session.add(registro)
            db_session.flush()
            proveedores[nombre] = registro
        return proveedores[nombre]

    def herramienta(nombre, nombre_proveedor, costo):
        registro = Herramienta(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            nombre=nombre,
            nombre_normalizado=normalizar_nombre(nombre),
            proveedor_id=proveedor(nombre_proveedor).id,
            costo_referencia=costo,
            moneda="USD",
            activo=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db_session.add(registro)
        return registro

    def licencia(emp, herr, costo, activa, moneda="USD"):
        registro = Licencia(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            herramienta_id=herr.id,
            empleado_id=emp.id,
            fecha_inicio=(date.today().replace(day=1) - timedelta(days=1)).replace(day=1),
            activa=activa,
            costo_mensual=costo,
            moneda=moneda,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        db_session.add(registro)
        return registro

    lescano = empleado("DEV-000001", "Lescano", "Tomas")
    gimenez = empleado("DEV-000002", "Gimenez", "Paula")
    db_session.flush()

    claude = herramienta("Claude Code", "Anthropic", 200)
    chatgpt = herramienta("ChatGPT Pro", "OpenAI", 100)
    office = herramienta("Microsoft 365", "Microsoft", 35.5)
    db_session.flush()

    licencia(lescano, claude, 200, True)
    licencia(lescano, chatgpt, 100, False)
    licencia(gimenez, office, 35.5, False)
    db_session.flush()

    return {
        "headers": auth_headers(usuario, empresa),
        "empresa_id": empresa.id,
        "lescano_id": lescano.id,
        "proveedores": {n: str(p.id) for n, p in proveedores.items()},
    }


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_una_fila_por_empleado_con_sus_licencias(client, escenario):
    response = client.get(POR_EMPLEADO, headers=escenario["headers"])

    assert response.status_code == 200
    cuerpo = response.json()
    # Dos empleados, tres licencias: la fila es la persona.
    assert cuerpo["total"] == 2

    por_nombre = {fila["empleado_nombre"]: fila for fila in cuerpo["items"]}
    assert list(por_nombre) == ["Gimenez, Paula", "Lescano, Tomas"]

    lescano = por_nombre["Lescano, Tomas"]
    assert lescano["cantidad"] == 2
    assert lescano["cantidad_activas"] == 1
    assert {lic["herramienta"] for lic in lescano["licencias"]} == {"Claude Code", "ChatGPT Pro"}


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_incluye_licencias_activas_y_no_activas(client, escenario):
    """La fila muestra las inactivas tambien, no solo las activas."""
    cuerpo = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()
    activas = {lic["herramienta"]: lic["activa"] for fila in cuerpo["items"] for lic in fila["licencias"]}

    assert activas == {
        "Claude Code": True,
        "ChatGPT Pro": False,
        "Microsoft 365": False,
    }


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_total_del_empleado_solo_cuenta_las_activas(client, escenario):
    """La fila no puede decir un gasto mayor al de las metricas."""
    cuerpo = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()
    por_nombre = {fila["empleado_nombre"]: fila for fila in cuerpo["items"]}

    # Lescano tiene Claude activa (200) y ChatGPT inactiva (100): paga 200.
    assert por_nombre["Lescano, Tomas"]["totales"] == [{"moneda": "USD", "total": 200.0}]
    # Gimenez tiene su unica licencia inactiva: no paga nada.
    assert por_nombre["Gimenez, Paula"]["totales"] == []
    # Y coincide con el gasto que informan las metricas.
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 200.0}]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_suma_monedas_distintas(client, escenario, db_session):
    """ARS y USD se informan por separado; sumarlos daria un numero falso."""
    licencia = db_session.query(Licencia).join(Herramienta).filter(Herramienta.nombre == "Microsoft 365").one()
    licencia.moneda = "ARS"
    licencia.costo_mensual = 50000
    licencia.activa = True
    db_session.flush()

    metricas = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()["metricas"]

    assert metricas["mes_actual"] == [
        {"moneda": "ARS", "total": 50000.0},
        {"moneda": "USD", "total": 200.0},
    ]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_filtro_por_proveedor_deja_solo_los_empleados_que_matchean(client, escenario):
    response = client.get(
        POR_EMPLEADO, headers=escenario["headers"], params={"proveedor_id": escenario["proveedores"]["OpenAI"]}
    )

    cuerpo = response.json()
    assert cuerpo["total"] == 1
    fila = cuerpo["items"][0]
    assert fila["empleado_nombre"] == "Lescano, Tomas"
    # En el detalle solo la licencia que matchea, no todas las del empleado.
    assert [lic["herramienta"] for lic in fila["licencias"]] == ["ChatGPT Pro"]
    # La de ChatGPT esta inactiva, asi que no suma gasto.
    assert fila["totales"] == []


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_filtra_por_equipo_del_empleado(client, escenario, db_session):
    """Un empleado puede estar en varios equipos: alcanza con pertenecer."""
    equipo = Equipo(
        id=uuid.uuid4(),
        empresa_id=escenario["empresa_id"],
        nombre="Plataforma",
        activo=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(equipo)
    db_session.flush()
    db_session.execute(
        equipo_integrantes.insert().values(
            equipo_id=equipo.id,
            empleado_id=escenario["lescano_id"],
            created_at=utc_now(),
        )
    )
    db_session.flush()

    cuerpo = client.get(POR_EMPLEADO, headers=escenario["headers"], params={"equipo_id": str(equipo.id)}).json()

    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["empleado_nombre"] == "Lescano, Tomas"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_busca_por_nombre_de_empleado(client, escenario):
    response = client.get(POR_EMPLEADO, headers=escenario["headers"], params={"buscar": "Gimenez"})

    cuerpo = response.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["empleado_nombre"] == "Gimenez, Paula"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_metricas_solo_cuentan_las_activas(client, escenario):
    """Una licencia inactiva no es gasto: no se paga."""
    cuerpo = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()

    # De las tres licencias solo Claude Code (200) esta activa.
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 200.0}]
    assert cuerpo["metricas"]["mes_anterior"] == [{"moneda": "USD", "total": 200.0}]
    # La moneda se informa igual, con variacion cero.
    assert cuerpo["metricas"]["delta"] == [{"moneda": "USD", "total": 0.0}]
    assert cuerpo["metricas"]["tendencia"] == "estable"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_al_activar_una_licencia_sube_el_gasto(client, escenario, db_session):
    """Es el feedback que se busca al tocar el checkbox."""
    antes = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()
    assert antes["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 200.0}]

    inactiva = db_session.query(Licencia).join(Herramienta).filter(Herramienta.nombre == "ChatGPT Pro").one()
    inactiva.activa = True
    db_session.flush()

    despues = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()

    assert despues["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 300.0}]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_lo_que_arranca_este_mes_no_cuenta_el_anterior(client, escenario, db_session):
    """La variacion entre meses es justo lo que se vence o arranca."""
    claude = db_session.query(Licencia).join(Herramienta).filter(Herramienta.nombre == "Claude Code").one()
    hoy = date.today()
    claude.fecha_inicio = hoy.replace(day=1)
    db_session.flush()

    metricas = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()["metricas"]

    assert metricas["mes_actual"] == [{"moneda": "USD", "total": 200.0}]
    # La moneda sigue presente en cero, no se omite.
    assert metricas["mes_anterior"] == [{"moneda": "USD", "total": 0.0}]
    assert metricas["delta"] == [{"moneda": "USD", "total": 200.0}]
    assert metricas["tendencia"] == "sube"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_lo_que_vencio_el_mes_anterior_no_cuenta_hoy(client, escenario, db_session):
    claude = db_session.query(Licencia).join(Herramienta).filter(Herramienta.nombre == "Claude Code").one()
    hoy = date.today()
    claude.fecha_fin = hoy.replace(day=1) - timedelta(days=1)
    db_session.flush()

    metricas = client.get(POR_EMPLEADO, headers=escenario["headers"]).json()["metricas"]

    assert metricas["mes_actual"] == [{"moneda": "USD", "total": 0.0}]
    assert metricas["mes_anterior"] == [{"moneda": "USD", "total": 200.0}]
    assert metricas["delta"] == [{"moneda": "USD", "total": -200.0}]
    assert metricas["tendencia"] == "baja"


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_pagina_empleados_no_licencias(client, escenario):
    """Con 1 por pagina hay 2 paginas: se pagina la persona, no la licencia."""
    primera = client.get(POR_EMPLEADO, headers=escenario["headers"], params={"por_pagina": 1, "pagina": 1}).json()

    assert primera["total"] == 2
    assert primera["total_paginas"] == 2
    assert len(primera["items"]) == 1
    assert primera["items"][0]["empleado_nombre"] == "Gimenez, Paula"

    segunda = client.get(POR_EMPLEADO, headers=escenario["headers"], params={"por_pagina": 1, "pagina": 2}).json()
    assert segunda["items"][0]["empleado_nombre"] == "Lescano, Tomas"
    # Las metricas son del set filtrado completo, no de la pagina: en la
    # pagina 2 solo esta Lescano, pero el gasto informado es el de todos.
    assert segunda["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 200.0}]
