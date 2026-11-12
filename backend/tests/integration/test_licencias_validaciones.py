"""Validaciones que preservan licencias y controles de permiso por empresa y grupos."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia
from backend.modules.nomina.models import Empleado
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/innovacion/licencias"
HERRAMIENTAS = "/api/v1/innovacion/herramientas"
pytestmark = [pytest.mark.integration]


@pytest.fixture
def auditoria_licencias(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    empleados = [
        Empleado(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            codigo=f"AUD-LIC-{indice}",
            cuil=20900000000 + indice,
            dni=90000000 + indice,
            apellido="Auditoria",
            nombre=f"Empleado {indice}",
            activo=activo,
        )
        for indice, activo in [(1, True), (2, False)]
    ]
    herramienta = Herramienta(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        nombre="Sin proveedor",
        nombre_normalizado="sin proveedor",
        moneda="USD",
        activo=True,
    )
    db_session.add_all([*empleados, herramienta])
    db_session.flush()
    licencia = Licencia(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        herramienta_id=herramienta.id,
        empleado_id=empleados[0].id,
        fecha_inicio=date.today().replace(day=1),
        costo_mensual=Decimal("10.00"),
        moneda="USD",
        activa=True,
    )
    db_session.add(licencia)
    db_session.commit()
    return {
        "headers": auth_headers(usuario, empresa),
        "licencia_id": str(licencia.id),
        "activo_id": str(empleados[0].id),
        "inactivo_id": str(empleados[1].id),
        "comunes": {
            "herramienta_id": str(herramienta.id),
            "fecha_inicio": date.today().isoformat(),
            "costo_mensual": "10.00",
            "moneda": "USD",
        },
    }


@pytest.mark.parametrize("vista", ["por-empleado", "por-equipo"])
def test_uuid_proveedor_invalido_no_devuelve_licencias(client, auditoria_licencias, vista):
    contexto = auditoria_licencias
    respuesta = client.get(
        f"{BASE}/{vista}",
        headers=contexto["headers"],
        params={
            "proveedor_id": "no-es-uuid",
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 0
    assert cuerpo["metricas"]["mes_actual"] == []
    assert cuerpo["items"] == []


@pytest.mark.parametrize("operacion", ["crear", "editar"])
def test_alta_y_edicion_individual_rechazan_empleado_inactivo(client, auditoria_licencias, operacion):
    contexto = auditoria_licencias
    opciones = client.get(f"{BASE}/empleados", headers=contexto["headers"]).json()
    assert {empleado["id"] for empleado in opciones} == {contexto["activo_id"]}
    lote = client.post(
        f"{BASE}/lote",
        headers=contexto["headers"],
        json={
            **contexto["comunes"],
            "empleado_ids": [contexto["inactivo_id"]],
        },
    )
    assert lote.status_code == 404, lote.text
    if operacion == "crear":
        respuesta = client.post(
            BASE,
            headers=contexto["headers"],
            json={
                **contexto["comunes"],
                "empleado_id": contexto["inactivo_id"],
            },
        )
    else:
        respuesta = client.put(
            f"{BASE}/{contexto['licencia_id']}",
            headers=contexto["headers"],
            json={
                "empleado_id": contexto["inactivo_id"],
            },
        )
    assert respuesta.status_code == 404, respuesta.text
    existente = client.get(f"{BASE}/{contexto['licencia_id']}", headers=contexto["headers"]).json()
    assert existente["empleado_id"] == contexto["activo_id"]


@pytest.mark.parametrize("cambio", ["ambas_fechas", "solo_fin", "solo_inicio"])
def test_edicion_rechaza_intervalo_invertido_incluso_con_una_sola_fecha(client, auditoria_licencias, cambio):
    contexto = auditoria_licencias
    primero = date.today().replace(day=1)
    fechas = {
        "fecha_inicio": (primero + timedelta(days=5)).isoformat(),
        "fecha_fin": (primero + timedelta(days=4)).isoformat(),
    }
    crear = client.post(
        BASE,
        headers=contexto["headers"],
        json={
            **contexto["comunes"],
            **fechas,
            "empleado_id": contexto["activo_id"],
        },
    )
    assert crear.status_code == 422, crear.text
    if cambio == "solo_fin":
        fechas = {"fecha_fin": (primero - timedelta(days=1)).isoformat()}
    elif cambio == "solo_inicio":
        preparar = client.put(
            f"{BASE}/{contexto['licencia_id']}",
            headers=contexto["headers"],
            json={
                "fecha_fin": fechas["fecha_fin"],
            },
        )
        assert preparar.status_code == 200, preparar.text
        fechas = {"fecha_inicio": fechas["fecha_inicio"]}
    antes = client.get(f"{BASE}/{contexto['licencia_id']}", headers=contexto["headers"]).json()
    editar = client.put(f"{BASE}/{contexto['licencia_id']}", headers=contexto["headers"], json=fechas)
    assert editar.status_code == 409, editar.text
    despues = client.get(f"{BASE}/{contexto['licencia_id']}", headers=contexto["headers"]).json()
    assert despues["fecha_inicio"] == antes["fecha_inicio"]
    assert despues["fecha_fin"] == antes["fecha_fin"]


@pytest.mark.parametrize("campo", ["empleado_id", "herramienta_id", "fecha_inicio", "moneda"])
def test_edicion_rechaza_null_en_campos_obligatorios(client, auditoria_licencias, campo):
    contexto = auditoria_licencias
    respuesta = client.put(
        f"{BASE}/{contexto['licencia_id']}",
        headers=contexto["headers"],
        json={
            campo: None,
        },
    )
    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.parametrize("costo", ["-0.01", "100000000.00", "1.234"])
def test_edicion_rechaza_costo_negativo_o_fuera_de_precision(client, auditoria_licencias, costo):
    contexto = auditoria_licencias
    respuesta = client.put(
        f"{BASE}/{contexto['licencia_id']}",
        headers=contexto["headers"],
        json={
            "costo_mensual": costo,
        },
    )
    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.parametrize("costo", ["0.00", "99999999.99"])
def test_edicion_acepta_limites_validos_del_costo(client, auditoria_licencias, costo):
    contexto = auditoria_licencias
    respuesta = client.put(
        f"{BASE}/{contexto['licencia_id']}",
        headers=contexto["headers"],
        json={
            "costo_mensual": costo,
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["costo_mensual"] == float(costo)
    assert respuesta.json()["empleado_id"] == contexto["activo_id"]


def test_edicion_permite_limpiar_campos_opcionales_sin_cambiar_los_demas(client, auditoria_licencias):
    contexto = auditoria_licencias
    respuesta = client.put(
        f"{BASE}/{contexto['licencia_id']}",
        headers=contexto["headers"],
        json={
            "costo_mensual": None,
            "fecha_fin": None,
            "nro_pedido_compra": None,
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["costo_mensual"] is None
    assert respuesta.json()["fecha_fin"] is None
    assert respuesta.json()["empleado_id"] == contexto["activo_id"]
    assert respuesta.json()["herramienta_id"] == contexto["comunes"]["herramienta_id"]


@pytest.mark.parametrize("operacion", ["crear", "editar"])
@pytest.mark.parametrize("costo", ["100000000.00", "1.234"])
def test_catalogo_rechaza_costo_referencia_fuera_de_precision(
    client,
    auditoria_licencias,
    operacion,
    costo,
):
    contexto = auditoria_licencias
    if operacion == "crear":
        respuesta = client.post(
            HERRAMIENTAS,
            headers=contexto["headers"],
            json={
                "nombre": "Herramienta costo",
                "costo_referencia": costo,
                "moneda": "USD",
            },
        )
    else:
        respuesta = client.put(
            f"{HERRAMIENTAS}/{contexto['comunes']['herramienta_id']}",
            headers=contexto["headers"],
            json={"costo_referencia": costo},
        )
    assert respuesta.status_code == 422, respuesta.text


@pytest.mark.parametrize("operacion", ["crear", "editar"])
@pytest.mark.parametrize("costo", [None, "0.00", "99999999.99"])
def test_catalogo_acepta_costo_referencia_nulo_y_limites_validos(
    client,
    auditoria_licencias,
    operacion,
    costo,
):
    contexto = auditoria_licencias
    if operacion == "crear":
        respuesta = client.post(
            HERRAMIENTAS,
            headers=contexto["headers"],
            json={
                "nombre": "Herramienta costo",
                "costo_referencia": costo,
                "moneda": "USD",
            },
        )
        esperado = 201
    else:
        url = f"{HERRAMIENTAS}/{contexto['comunes']['herramienta_id']}"
        preparar = client.put(url, headers=contexto["headers"], json={"costo_referencia": "20.00"})
        assert preparar.status_code == 200, preparar.text
        respuesta = client.put(url, headers=contexto["headers"], json={"costo_referencia": costo})
        esperado = 200
    assert respuesta.status_code == esperado, respuesta.text
    assert respuesta.json()["costo_referencia"] == (None if costo is None else float(costo))


@pytest.mark.parametrize("operacion", ["crear", "editar"])
def test_alta_y_edicion_individual_rechazan_herramienta_inactiva(
    client,
    db_session,
    auditoria_licencias,
    operacion,
):
    contexto = auditoria_licencias
    herramienta_actual = db_session.get(Herramienta, uuid.UUID(contexto["comunes"]["herramienta_id"]))
    inactiva = Herramienta(
        id=uuid.uuid4(),
        empresa_id=herramienta_actual.empresa_id,
        nombre="Herramienta inactiva",
        nombre_normalizado="herramienta inactiva",
        moneda="USD",
        activo=False,
    )
    db_session.add(inactiva)
    db_session.commit()
    if operacion == "crear":
        respuesta = client.post(
            BASE,
            headers=contexto["headers"],
            json={
                **contexto["comunes"],
                "empleado_id": contexto["activo_id"],
                "herramienta_id": str(inactiva.id),
            },
        )
    else:
        respuesta = client.put(
            f"{BASE}/{contexto['licencia_id']}",
            headers=contexto["headers"],
            json={
                "herramienta_id": str(inactiva.id),
            },
        )
    assert respuesta.status_code == 404, respuesta.text
    existente = client.get(f"{BASE}/{contexto['licencia_id']}", headers=contexto["headers"]).json()
    assert existente["herramienta_id"] == contexto["comunes"]["herramienta_id"]
    assert db_session.query(Licencia).filter(Licencia.empleado_id == uuid.UUID(contexto["activo_id"])).count() == 1


@pytest.mark.parametrize(
    "caso,status",
    [
        ("modulo_solo", 403),
        ("submodulo_solo", 403),
        ("ambos", 200),
        ("grupo_desactivado", 403),
        ("grupo_borrado", 403),
        ("permiso_borrado", 403),
        ("otra_empresa", 403),
        ("union_dos_grupos", 200),
        ("grant_prevalece_deny", 200),
    ],
)
def test_auditoria_control_permiso_licencias_por_empresa_y_grupos(
    client,
    db_session,
    data_factory,
    caso,
    status,
):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(usuario, empresa)
    empresa_permisos = empresa
    if caso == "otra_empresa":
        empresa_permisos = data_factory.empresa()
        data_factory.asignar_empresa(usuario, empresa_permisos)

    grupo = data_factory.grupo()
    data_factory.asignar_grupo(usuario, grupo, empresa_permisos)
    claves = ["innovacion", "innovacion.licencias"]
    if caso in ("modulo_solo", "union_dos_grupos"):
        claves = ["innovacion"]
    elif caso == "submodulo_solo":
        claves = ["innovacion.licencias"]
    permisos = data_factory.permisos(grupo, claves)

    if caso == "grupo_desactivado":
        grupo.activo = False
    elif caso == "grupo_borrado":
        grupo.deleted_at = utc_now()
    elif caso == "permiso_borrado":
        next(permiso for permiso in permisos if permiso.modulo == "innovacion.licencias").deleted_at = utc_now()
    elif caso in ("union_dos_grupos", "grant_prevalece_deny"):
        segundo = data_factory.grupo()
        data_factory.asignar_grupo(usuario, segundo, empresa)
        data_factory.permisos(
            segundo,
            ["innovacion.licencias"] if caso == "union_dos_grupos" else ["innovacion", "innovacion.licencias"],
            tiene_acceso=caso == "union_dos_grupos",
        )
    db_session.flush()

    respuesta = client.get(f"{BASE}/por-empleado", headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == status, respuesta.text
    if status == 200:
        assert respuesta.json()["items"] == []
