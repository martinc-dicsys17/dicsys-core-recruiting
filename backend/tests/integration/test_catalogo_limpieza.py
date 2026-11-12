"""Bajas lógicas del catálogo y recuperación de nombres eliminados."""

import uuid
from datetime import date

import pytest

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia, Proveedor
from backend.modules.nomina.models import Empleado
from backend.tests.helpers.auth import auth_headers

HERRAMIENTAS = "/api/v1/innovacion/herramientas"
PROVEEDORES = "/api/v1/innovacion/proveedores"
LICENCIAS = "/api/v1/innovacion/licencias"
POR_EMPLEADO = "/api/v1/innovacion/licencias/por-empleado"


@pytest.fixture
def acceso(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])

    empleado = Empleado(
        id=uuid.uuid4(),
        empresa_id=empresa.id,
        codigo="DEV-900",
        cuil=20309000001,
        apellido="Prueba",
        nombre="Empleado",
        dni=30900001,
        activo=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(empleado)
    db_session.flush()

    return {
        "headers": auth_headers(usuario, empresa),
        "empresa_id": empresa.id,
        "empleado_id": str(empleado.id),
    }


def _nombres(client, url, headers):
    return [x["nombre"] for x in client.get(url, headers=headers).json()]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_el_proveedor_mal_escrito_se_limpia_reapuntando_y_borrando(client, acceso):
    """El flujo completo del typo, que es para lo que existe esto."""
    cabeceras = acceso["headers"]
    client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "ChatGPT Pro", "proveedor_nombre": "OpenAI"})
    sucia = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Sora", "proveedor_nombre": "OenAI"}).json()

    assert _nombres(client, PROVEEDORES, cabeceras) == ["OenAI", "OpenAI"]

    # Reapuntar conserva la herramienta al eliminar el proveedor incorrecto.
    bueno = next(p for p in client.get(PROVEEDORES, headers=cabeceras).json() if p["nombre"] == "OpenAI")
    corregida = client.put(f"{HERRAMIENTAS}/{sucia['id']}", headers=cabeceras, json={"proveedor_id": bueno["id"]})
    assert corregida.status_code == 200
    assert corregida.json()["proveedor"] == "OpenAI"

    assert client.delete(f"{PROVEEDORES}/{sucia['proveedor_id']}", headers=cabeceras).status_code == 204
    assert _nombres(client, PROVEEDORES, cabeceras) == ["OpenAI"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_desasignar_el_proveedor_conserva_la_herramienta(client, acceso):
    """Alcanza con dejar la herramienta sin proveedor."""
    cabeceras = acceso["headers"]
    herramienta = client.post(
        HERRAMIENTAS, headers=cabeceras, json={"nombre": "Sora", "proveedor_nombre": "OenAI"}
    ).json()

    client.put(f"{HERRAMIENTAS}/{herramienta['id']}", headers=cabeceras, json={"proveedor_id": ""})

    assert client.delete(f"{PROVEEDORES}/{herramienta['proveedor_id']}", headers=cabeceras).status_code == 204
    assert client.get(HERRAMIENTAS, headers=cabeceras).json()[0]["proveedor"] is None


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_borrar_herramienta_quita_sus_licencias(client, acceso):
    cabeceras = acceso["headers"]
    herramienta = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jira"}).json()
    client.post(
        LICENCIAS,
        headers=cabeceras,
        json={
            "herramienta_id": herramienta["id"],
            "empleado_id": acceso["empleado_id"],
            "fecha_inicio": "2026-09-01",
        },
    )

    response = client.delete(f"{HERRAMIENTAS}/{herramienta['id']}", headers=cabeceras)

    assert response.status_code == 204
    assert client.get(POR_EMPLEADO, headers=cabeceras).json()["items"] == []


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_borrar_la_licencia_libera_la_herramienta(client, acceso):
    cabeceras = acceso["headers"]
    herramienta = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jira"}).json()
    licencia = client.post(
        LICENCIAS,
        headers=cabeceras,
        json={
            "herramienta_id": herramienta["id"],
            "empleado_id": acceso["empleado_id"],
            "fecha_inicio": "2026-09-01",
            "costo_mensual": 50,
            "moneda": "USD",
        },
    ).json()

    assert client.delete(f"{LICENCIAS}/{licencia['id']}", headers=cabeceras).status_code == 204
    assert client.delete(f"{HERRAMIENTAS}/{herramienta['id']}", headers=cabeceras).status_code == 204


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_la_licencia_borrada_sale_del_listado_y_del_gasto(client, acceso):
    cabeceras = acceso["headers"]
    herramienta = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jira"}).json()
    licencia = client.post(
        LICENCIAS,
        headers=cabeceras,
        json={
            "herramienta_id": herramienta["id"],
            "empleado_id": acceso["empleado_id"],
            "fecha_inicio": "2026-09-01",
            "costo_mensual": 50,
            "moneda": "USD",
        },
    ).json()

    antes = client.get(POR_EMPLEADO, headers=cabeceras).json()
    assert antes["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 50.0}]

    client.delete(f"{LICENCIAS}/{licencia['id']}", headers=cabeceras)

    despues = client.get(POR_EMPLEADO, headers=cabeceras).json()
    # Era su unica licencia, asi que el empleado ya no aparece.
    assert despues["total"] == 0
    assert despues["metricas"]["mes_actual"] == []


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_renombrar_una_herramienta_rechaza_el_duplicado(client, acceso):
    """Corregir un nombre no puede colisionar con otro ya existente."""
    cabeceras = acceso["headers"]
    client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jira"})
    otra = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jiraa"}).json()

    response = client.put(f"{HERRAMIENTAS}/{otra['id']}", headers=cabeceras, json={"nombre": "  JIRA "})

    assert response.status_code == 409
    assert "Ya existe" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_renombrar_corrige_el_typo(client, acceso):
    cabeceras = acceso["headers"]
    herramienta = client.post(HERRAMIENTAS, headers=cabeceras, json={"nombre": "Jiraa"}).json()

    response = client.put(f"{HERRAMIENTAS}/{herramienta['id']}", headers=cabeceras, json={"nombre": "Jira"})

    assert response.status_code == 200
    assert _nombres(client, HERRAMIENTAS, cabeceras) == ["Jira"]


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_no_se_puede_borrar_nada_de_otra_empresa(client, db_session, acceso, data_factory):
    """El borrado tambien respeta el aislamiento."""
    ajeno_usuario = data_factory.usuario()
    ajena = data_factory.empresa()
    ajeno_grupo = data_factory.grupo()
    data_factory.asignar_empresa(ajeno_usuario, ajena)
    data_factory.asignar_grupo(ajeno_usuario, ajeno_grupo, ajena)
    data_factory.permisos(ajeno_grupo, ["innovacion", "innovacion.licencias"])
    ajenas_cabeceras = auth_headers(ajeno_usuario, ajena)

    propia = client.post(
        HERRAMIENTAS, headers=acceso["headers"], json={"nombre": "Jira", "proveedor_nombre": "Atlassian"}
    ).json()

    assert client.delete(f"{HERRAMIENTAS}/{propia['id']}", headers=ajenas_cabeceras).status_code == 404
    assert client.delete(f"{PROVEEDORES}/{propia['proveedor_id']}", headers=ajenas_cabeceras).status_code == 404
    assert (
        client.put(f"{HERRAMIENTAS}/{propia['id']}", headers=ajenas_cabeceras, json={"nombre": "Robada"}).status_code
        == 404
    )


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize("origen", ["proveedor", "herramienta_nueva", "herramienta_editada"])
def test_recrear_proveedor_recupera_la_misma_fila(client, db_session, acceso, origen):
    headers = acceso["headers"]
    original = client.post(PROVEEDORES, headers=headers, json={"nombre": "OenAI"}).json()
    fila = db_session.get(Proveedor, uuid.UUID(original["id"]))
    creado = fila.created_at
    assert client.delete(f"{PROVEEDORES}/{original['id']}", headers=headers).status_code == 204

    if origen == "proveedor":
        response = client.post(PROVEEDORES, headers=headers, json={"nombre": "  OENAI  "})
        assert response.status_code == 201
        assert response.json()["id"] == original["id"]
    elif origen == "herramienta_nueva":
        response = client.post(HERRAMIENTAS, headers=headers, json={"nombre": "Sora", "proveedor_nombre": "  OENAI  "})
        assert response.status_code == 201
        assert response.json()["proveedor_id"] == original["id"]
    else:
        herramienta = client.post(HERRAMIENTAS, headers=headers, json={"nombre": "Sora"}).json()
        response = client.put(
            f"{HERRAMIENTAS}/{herramienta['id']}", headers=headers, json={"proveedor_nombre": "  OENAI  "}
        )
        assert response.status_code == 200
        assert response.json()["proveedor_id"] == original["id"]

    db_session.refresh(fila)
    assert fila.deleted_at is None
    assert fila.activo is True
    assert fila.created_at == creado
    assert fila.nombre == "OENAI"
    assert db_session.query(Proveedor).filter_by(empresa_id=acceso["empresa_id"]).count() == 1


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_recrear_herramienta_recupera_id_y_aplica_datos_nuevos(client, db_session, acceso):
    headers = acceso["headers"]
    original = client.post(
        HERRAMIENTAS,
        headers=headers,
        json={
            "nombre": "Jira",
            "proveedor_nombre": "Atlassian",
            "costo_referencia": 50,
            "moneda": "USD",
        },
    ).json()
    fila = db_session.get(Herramienta, uuid.UUID(original["id"]))
    creado = fila.created_at
    assert client.delete(f"{HERRAMIENTAS}/{original['id']}", headers=headers).status_code == 204
    assert client.delete(f"{PROVEEDORES}/{original['proveedor_id']}", headers=headers).status_code == 204

    response = client.post(HERRAMIENTAS, headers=headers, json={"nombre": "  JIRA  "})

    assert response.status_code == 201
    assert response.json()["id"] == original["id"]
    assert response.json()["proveedor_id"] is None
    assert response.json()["costo_referencia"] is None
    assert response.json()["moneda"] == "ARS"
    db_session.refresh(fila)
    assert fila.deleted_at is None
    assert fila.activo is True
    assert fila.created_at == creado
    assert fila.nombre == "JIRA"
    assert db_session.query(Herramienta).filter_by(empresa_id=acceso["empresa_id"]).count() == 1
    assert client.post(HERRAMIENTAS, headers=headers, json={"nombre": "Jira"}).status_code == 409


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_recrear_no_recupera_catalogos_borrados_de_otra_empresa(client, db_session, acceso, data_factory):
    ajena = data_factory.empresa()
    proveedor = Proveedor(empresa_id=ajena.id, nombre="Atlassian", nombre_normalizado="atlassian", deleted_at=utc_now())
    herramienta = Herramienta(empresa_id=ajena.id, nombre="Jira", nombre_normalizado="jira", deleted_at=utc_now())
    db_session.add_all([proveedor, herramienta])
    db_session.flush()

    response = client.post(
        HERRAMIENTAS,
        headers=acceso["headers"],
        json={
            "nombre": "Jira",
            "proveedor_nombre": "Atlassian",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] != str(herramienta.id)
    assert response.json()["proveedor_id"] != str(proveedor.id)
    db_session.refresh(proveedor)
    db_session.refresh(herramienta)
    assert proveedor.deleted_at is not None
    assert herramienta.deleted_at is not None


@pytest.fixture
def catalogo_cascada(db_session, data_factory, acceso):
    empresa_id = acceso["empresa_id"]
    ajena = data_factory.empresa()
    empleado = db_session.get(Empleado, uuid.UUID(acceso["empleado_id"]))
    segundo = Empleado(
        empresa_id=empresa_id,
        codigo="DEV-901",
        cuil=20309000002,
        apellido="Otra",
        nombre="Persona",
        dni=30900002,
        activo=True,
    )
    externo = Empleado(
        empresa_id=ajena.id,
        codigo="EXT-1",
        cuil=20309000003,
        apellido="Externa",
        nombre="Persona",
        dni=30900003,
        activo=True,
    )
    proveedor = Proveedor(empresa_id=empresa_id, nombre="Proveedor", nombre_normalizado="proveedor")
    proveedor_ajeno = Proveedor(empresa_id=ajena.id, nombre="Proveedor", nombre_normalizado="proveedor")
    db_session.add_all([segundo, externo, proveedor, proveedor_ajeno])
    db_session.flush()
    herramientas = [
        Herramienta(empresa_id=empresa_id, nombre=nombre, nombre_normalizado=nombre.lower(), proveedor_id=proveedor.id)
        for nombre in ["Editor", "Chat"]
    ]
    # Incluso ante referencias históricas cruzadas, nunca se modifica otra empresa.
    herramienta_ajena = Herramienta(
        empresa_id=ajena.id, nombre="Editor", nombre_normalizado="editor", proveedor_id=proveedor.id
    )
    db_session.add_all([*herramientas, herramienta_ajena])
    db_session.flush()
    licencias = [
        Licencia(
            empresa_id=empresa_id,
            empleado_id=persona.id,
            herramienta_id=herramientas[indice].id,
            fecha_inicio=date.today(),
            activa=activa,
        )
        for persona, indice, activa in [(empleado, 0, True), (segundo, 0, False), (segundo, 1, True)]
    ]
    anteriores = Licencia(
        empresa_id=empresa_id,
        empleado_id=empleado.id,
        herramienta_id=herramientas[0].id,
        fecha_inicio=date.today(),
        deleted_at=utc_now(),
        updated_by="baja anterior",
    )
    ajenas = [
        Licencia(empresa_id=ajena.id, empleado_id=externo.id, herramienta_id=h.id, fecha_inicio=date.today())
        for h in [herramientas[0], herramienta_ajena]
    ]
    db_session.add_all([*licencias, anteriores, *ajenas])
    db_session.commit()
    return proveedor, herramientas, licencias, anteriores, [proveedor_ajeno, herramienta_ajena, *ajenas]


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize("tipo", ["herramienta", "proveedor"])
def test_cascada_es_logica_auditada_y_aislada_por_empresa(client, db_session, acceso, catalogo_cascada, tipo):
    proveedor, herramientas, licencias, anterior, ajenos = catalogo_cascada
    fecha_anterior = anterior.deleted_at
    url, raiz = (HERRAMIENTAS, herramientas[0]) if tipo == "herramienta" else (PROVEEDORES, proveedor)
    afectados = [herramientas[0], *licencias[:2]] if tipo == "herramienta" else [proveedor, *herramientas, *licencias]
    intactos = [proveedor, herramientas[1], licencias[2], *ajenos] if tipo == "herramienta" else ajenos

    respuesta = client.delete(f"{url}/{raiz.id}", headers=acceso["headers"])

    assert respuesta.status_code == 204, respuesta.text
    db_session.expire_all()
    assert raiz.deleted_at is not None
    for fila in afectados:
        assert fila.deleted_at == raiz.deleted_at
        assert fila.updated_at == raiz.deleted_at
        assert fila.updated_by
        assert db_session.get(type(fila), fila.id) is not None
    for fila in intactos:
        assert fila.deleted_at is None
    assert anterior.deleted_at == fecha_anterior
    assert anterior.updated_by == "baja anterior"
    assert client.delete(f"{url}/{raiz.id}", headers=acceso["headers"]).status_code == 404


@pytest.mark.integration
@pytest.mark.deploy_gate
@pytest.mark.parametrize("tipo", ["herramienta", "proveedor"])
def test_cascada_se_revierte_completa_si_falla_commit(client, db_session, acceso, catalogo_cascada, monkeypatch, tipo):
    proveedor, herramientas, licencias, _, ajenos = catalogo_cascada
    url, raiz = (HERRAMIENTAS, herramientas[0]) if tipo == "herramienta" else (PROVEEDORES, proveedor)

    def fallar_commit():
        raise RuntimeError("Fallo al confirmar la transacción")

    monkeypatch.setattr(db_session, "commit", fallar_commit)
    respuesta = client.delete(f"{url}/{raiz.id}", headers=acceso["headers"])

    assert respuesta.status_code == 500
    db_session.expire_all()
    for fila in [proveedor, *herramientas, *licencias, *ajenos]:
        assert fila.deleted_at is None


@pytest.mark.integration
@pytest.mark.deploy_gate
def test_baja_individual_no_quita_licencias_de_otros_empleados(client, db_session, acceso, catalogo_cascada):
    proveedor, herramientas, licencias, _, _ = catalogo_cascada
    respuesta = client.delete(f"{LICENCIAS}/{licencias[0].id}", headers=acceso["headers"])
    assert respuesta.status_code == 204
    db_session.expire_all()
    assert licencias[0].deleted_at is not None
    assert all(fila.deleted_at is None for fila in [proveedor, *herramientas, *licencias[1:]])
