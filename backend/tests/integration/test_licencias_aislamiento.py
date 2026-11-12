"""Aislamiento multiempresa de licencias y del catalogo de herramientas."""

import uuid
from datetime import date

import pytest

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia, Proveedor
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado
from backend.tests.helpers.auth import auth_headers

HERRAMIENTAS = "/api/v1/innovacion/herramientas"
PROVEEDORES = "/api/v1/innovacion/proveedores"
LICENCIAS = "/api/v1/innovacion/licencias"
POR_EMPLEADO = "/api/v1/innovacion/licencias/por-empleado"


def _con_acceso(data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    return usuario, empresa, auth_headers(usuario, empresa)


def _empleado(db_session, empresa, sufijo):
    registro = Empleado(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        codigo=f"E{sufijo}",
        cuil=int(f"2030{sufijo}"),
        apellido="Prueba",
        nombre=f"Empleado {sufijo}",
        dni=int(f"3010{sufijo}"),
        activo=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(registro)
    db_session.flush()
    return registro


def _proveedor(db_session, empresa, nombre):
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
    return registro


def _herramienta(db_session, empresa, nombre, proveedor=None):
    registro = Herramienta(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        nombre=nombre,
        nombre_normalizado=normalizar_nombre(nombre),
        proveedor_id=_proveedor(db_session, empresa, proveedor).id if proveedor else None,
        moneda="USD",
        activo=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(registro)
    db_session.flush()
    return registro


@pytest.fixture
def dos_empresas(db_session, data_factory):
    propio_usuario, propia, propias_cabeceras = _con_acceso(data_factory)
    _, ajena, ajenas_cabeceras = _con_acceso(data_factory)

    return {
        "propia": propia,
        "ajena": ajena,
        "cabeceras": propias_cabeceras,
        "cabeceras_ajenas": ajenas_cabeceras,
        "empleado_propio": _empleado(db_session, propia, "001"),
        "empleado_ajeno": _empleado(db_session, ajena, "002"),
        "herramienta_ajena": _herramienta(db_session, ajena, "Secreto Ajeno SA", "Proveedor Ajeno"),
    }


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_crear_licencia_con_herramienta_de_otra_empresa(client, dos_empresas):
    """Sin esto, el nombre y proveedor del catalogo ajeno se filtran en el listado."""
    response = client.post(
        LICENCIAS,
        headers=dos_empresas["cabeceras"],
        json={
            "herramienta_id": str(dos_empresas["herramienta_ajena"].id),
            "empleado_id": str(dos_empresas["empleado_propio"].id),
            "fecha_inicio": "2026-09-01",
        },
    )

    assert response.status_code == 404, response.json()


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_crear_licencia_para_empleado_de_otra_empresa(client, db_session, dos_empresas):
    propia = _herramienta(db_session, dos_empresas["propia"], "Jira", "Atlassian")

    response = client.post(
        LICENCIAS,
        headers=dos_empresas["cabeceras"],
        json={
            "herramienta_id": str(propia.id),
            "empleado_id": str(dos_empresas["empleado_ajeno"].id),
            "fecha_inicio": "2026-09-01",
        },
    )

    assert response.status_code == 404, response.json()


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_reapuntar_una_licencia_a_herramienta_ajena(client, db_session, dos_empresas):
    propia = _herramienta(db_session, dos_empresas["propia"], "Confluence", "Atlassian")
    licencia = Licencia(
        id=uuid.uuid4(),
        empresa_id=dos_empresas["propia"].id,
        herramienta_id=propia.id,
        empleado_id=dos_empresas["empleado_propio"].id,
        fecha_inicio=date(2026, 9, 1),
        activa=True,
        moneda="USD",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(licencia)
    db_session.flush()

    response = client.put(
        f"{LICENCIAS}/{licencia.id}",
        headers=dos_empresas["cabeceras"],
        json={
            "herramienta_id": str(dos_empresas["herramienta_ajena"].id),
        },
    )

    assert response.status_code == 404, response.json()


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize("herramienta_id", ["no-es-un-uuid", "", "'; DROP TABLE innovacion_licencias; --"])
def test_un_id_malformado_es_referencia_invalida_no_error_interno(client, db_session, dos_empresas, herramienta_id):
    response = client.post(
        LICENCIAS,
        headers=dos_empresas["cabeceras"],
        json={
            "herramienta_id": herramienta_id,
            "empleado_id": str(dos_empresas["empleado_propio"].id),
            "fecha_inicio": "2026-09-01",
        },
    )

    assert response.status_code in (404, 422), response.json()
    assert response.status_code != 500


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize("basura", ["no-es-uuid", "1 OR 1=1", "../../etc/passwd"])
def test_ids_basura_en_la_url_no_dan_error_interno(client, dos_empresas, basura):
    """Un id malformado en el path o el query string es 404/422, nunca 500."""
    cabeceras = dos_empresas["cabeceras"]

    assert client.get(f"{LICENCIAS}/{basura}", headers=cabeceras).status_code == 404
    assert client.put(f"{LICENCIAS}/{basura}/activa/false", headers=cabeceras).status_code == 404
    assert client.get(POR_EMPLEADO, headers=cabeceras, params={"empleado_id": basura}).status_code == 200
    assert client.get(POR_EMPLEADO, headers=cabeceras, params={"equipo_id": basura}).json()["total"] == 0


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_catalogo_ajeno_no_aparece_ni_por_id(client, dos_empresas):
    assert client.get(HERRAMIENTAS, headers=dos_empresas["cabeceras"]).json() == []
    # El proveedor de la otra empresa tampoco se lista.
    assert client.get(PROVEEDORES, headers=dos_empresas["cabeceras"]).json() == []


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_crear_herramienta_con_proveedor_de_otra_empresa(client, db_session, dos_empresas):
    ajeno = _proveedor(db_session, dos_empresas["ajena"], "Proveedor Ajeno SA")

    response = client.post(
        HERRAMIENTAS,
        headers=dos_empresas["cabeceras"],
        json={
            "nombre": "Herramienta propia",
            "proveedor_id": str(ajeno.id),
        },
    )

    assert response.status_code == 404, response.json()


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_listado_por_empleado_no_cruza_empresas(client, db_session, dos_empresas):
    propia = _herramienta(db_session, dos_empresas["propia"], "Slack", "Salesforce")
    db_session.add(
        Licencia(
            id=uuid.uuid4(),
            empresa_id=dos_empresas["ajena"].id,
            herramienta_id=dos_empresas["herramienta_ajena"].id,
            empleado_id=dos_empresas["empleado_ajeno"].id,
            fecha_inicio=date(2026, 9, 1),
            activa=True,
            costo_mensual=999,
            moneda="USD",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.add(
        Licencia(
            id=uuid.uuid4(),
            empresa_id=dos_empresas["propia"].id,
            herramienta_id=propia.id,
            empleado_id=dos_empresas["empleado_propio"].id,
            fecha_inicio=date(2026, 9, 1),
            activa=True,
            costo_mensual=10,
            moneda="USD",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    db_session.flush()

    cuerpo = client.get(POR_EMPLEADO, headers=dos_empresas["cabeceras"]).json()

    assert cuerpo["total"] == 1
    herramientas = {lic["herramienta"] for fila in cuerpo["items"] for lic in fila["licencias"]}
    assert herramientas == {"Slack"}
    # El gasto ajeno no se cuela en las metricas.
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 10.0}]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_activar_una_licencia_ajena(client, db_session, dos_empresas):
    ajena = Licencia(
        id=uuid.uuid4(),
        empresa_id=dos_empresas["ajena"].id,
        herramienta_id=dos_empresas["herramienta_ajena"].id,
        empleado_id=dos_empresas["empleado_ajeno"].id,
        fecha_inicio=date(2026, 9, 1),
        activa=True,
        moneda="USD",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(ajena)
    db_session.flush()

    response = client.put(f"{LICENCIAS}/{ajena.id}/activa/false", headers=dos_empresas["cabeceras"])

    assert response.status_code == 404
