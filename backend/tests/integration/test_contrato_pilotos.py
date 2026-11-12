"""Contrato de los pilotos de v2, parametros y sincronizacion (F07-P08): response_model, errores con forma estable y
paginación uniforme; y el 422 de toda la API, que el OpenAPI declara como responde (PG-14)."""

import json
import re
import uuid

import pytest

from backend.modules.parametros.models import Parametro
from backend.modules.sincronizacion.models import LogSincronizacion, ProcesoSincronizacion
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

PILOTOS = ("/api/v1/parametros", "/api/v1/sincronizacion")


@pytest.fixture
def admin(data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["configuracion", "configuracion.parametros", "configuracion.actualizacion_datos"])
    return usuario, auth_headers(usuario, empresa)


@pytest.fixture
def parametros(db_session):
    sufijo = uuid.uuid4().hex[:8]
    filas = [
        Parametro(categoria=f"Piloto {sufijo}", nombre=f"P{i}", key=f"piloto_{sufijo}_{i}", valor=str(i))
        for i in range(3)
    ]
    db_session.add_all(filas)
    db_session.flush()
    return f"Piloto {sufijo}", filas


@pytest.fixture
def proceso(db_session):
    fila = ProcesoSincronizacion(codigo=f"piloto_{uuid.uuid4().hex[:8]}", nombre="Piloto", tipo_origen="test")
    db_session.add(fila)
    db_session.flush()
    return fila


def test_el_422_de_validacion_trae_detail_y_un_error_por_campo(client, admin):
    _, headers = admin

    r = client.post("/api/v1/parametros", json={"nombre": "x" * 201, "key": 7}, headers=headers)

    assert r.status_code == 422, r.text
    cuerpo = r.json()
    assert cuerpo["detail"].startswith("Categoría: es obligatorio")
    por_campo = {e["campo"]: e["mensaje"] for e in cuerpo["errores"]}
    assert por_campo == {
        "categoria": "es obligatorio",
        "nombre": "no puede tener más de 200 caracteres",
        "key": "debe ser texto",
    }


def test_el_openapi_declara_el_422_que_responde_el_handler(client):
    esquema = client.get("/openapi.json").json()
    componentes = esquema["components"]["schemas"]

    assert "HTTPValidationError" not in componentes and "ValidationError" not in componentes
    assert set(componentes["ErrorDeValidacion"]["properties"]) == {"detail", "errores"}
    assert "HTTPValidationError" not in json.dumps(esquema)
    login = esquema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"]
    assert login["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ErrorDeValidacion"


def test_los_pilotos_declaran_su_respuesta_y_sus_errores(client):
    paths = client.get("/openapi.json").json()["paths"]
    operaciones = [(p, m, op) for p, ops in paths.items() if p.startswith(PILOTOS) for m, op in ops.items()]

    assert len(operaciones) == 12
    for path, metodo, op in operaciones:
        respuestas = op["responses"]
        exito = respuestas.get("200") or respuestas.get("201")
        assert "$ref" in exito["content"]["application/json"]["schema"], f"{metodo} {path} sin response_model"
        for codigo in ("401", "403"):
            assert respuestas[codigo]["content"]["application/json"]["schema"]["$ref"].endswith("/Error")
        if "{id}" in path:
            assert "404" in respuestas, f"{metodo} {path}"
            assert next(p for p in op["parameters"] if p["name"] == "id")["schema"]["format"] == "uuid"


@pytest.mark.parametrize(
    ("metodo", "url", "cuerpo"),
    [
        ("get", "/api/v1/parametros/{id}", None),
        ("put", "/api/v1/parametros/{id}/valor", {"valor": "x"}),
        ("delete", "/api/v1/parametros/{id}", None),
        ("get", "/api/v1/sincronizacion/procesos/{id}", None),
        ("put", "/api/v1/sincronizacion/procesos/{id}", {"activo": False}),
        ("post", "/api/v1/sincronizacion/procesos/{id}/ejecutar", None),
        ("get", "/api/v1/sincronizacion/procesos/{id}/logs", None),
    ],
)
def test_un_id_mal_formado_da_422_y_uno_inexistente_404(client, admin, metodo, url, cuerpo):
    _, headers = admin

    def pedir(id_):
        return client.request(metodo.upper(), url.format(id=id_), json=cuerpo, headers=headers)

    mal = pedir("no-es-un-uuid")
    assert mal.status_code == 422, mal.text
    assert mal.json()["errores"] == [{"campo": "id", "mensaje": "no es un identificador válido"}]
    inexistente = pedir(uuid.uuid4())
    assert inexistente.status_code == 404, inexistente.text
    assert set(inexistente.json()) == {"detail"}


def test_el_listado_de_parametros_pagina_y_trae_las_categorias(client, admin, parametros):
    _, headers = admin
    categoria, _ = parametros

    primera = client.get("/api/v1/parametros", params={"categoria": categoria, "por_pagina": 2}, headers=headers)
    segunda = client.get(
        "/api/v1/parametros", params={"categoria": categoria, "por_pagina": 2, "pagina": 2}, headers=headers
    )

    assert primera.status_code == 200, primera.text
    assert {k: primera.json()[k] for k in ("total", "pagina", "por_pagina", "total_paginas")} == {
        "total": 3,
        "pagina": 1,
        "por_pagina": 2,
        "total_paginas": 2,
    }
    assert [p["nombre"] for p in primera.json()["items"] + segunda.json()["items"]] == ["P0", "P1", "P2"]
    assert categoria in primera.json()["categorias"]
    assert client.get("/api/v1/parametros", params={"por_pagina": 101}, headers=headers).status_code == 422


def test_borrar_un_parametro_responde_su_mensaje(client, admin, parametros):
    _, headers = admin
    _, filas = parametros

    r = client.delete(f"/api/v1/parametros/{filas[0].id}", headers=headers)

    assert r.status_code == 200 and r.json() == {"message": "Parámetro eliminado"}


def test_webex_rooms_sin_team_configurado_responde_la_forma_del_contrato(client, admin):
    _, headers = admin

    r = client.get("/api/v1/parametros/webex-rooms", headers=headers)

    assert r.status_code == 200
    assert r.json()["success"] is False and r.json()["rooms"] == [] and r.json()["error"]


def test_ejecutar_un_proceso_desactivado_da_409_y_uno_activo_registra_a_quien_llama(client, admin, proceso, db_session):
    usuario, headers = admin
    url = f"/api/v1/sincronizacion/procesos/{proceso.id}/ejecutar"
    proceso.activo = False
    db_session.flush()
    assert client.post(url, headers=headers).json() == {"detail": "El proceso está desactivado"}

    proceso.activo = True
    db_session.flush()
    r = client.post(url, params={"usuario": "otro@example.com"}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["exito"] is False and "no implementado" in r.json()["mensaje"]
    log = db_session.query(LogSincronizacion).filter_by(proceso_id=proceso.id).one()
    assert log.ejecutado_por == usuario.email, "el ejecutor sale del token, no de la query"


def test_los_logs_paginan_y_separan_errores_y_actualizaciones(client, admin, proceso, db_session):
    _, headers = admin
    for detalle in (
        json.dumps({"errores": [{"tipo": "dni", "dni": "1"}], "actualizaciones": ["a"]}),
        json.dumps(["viejo"]),
        "no es json",
    ):
        db_session.add(LogSincronizacion(proceso_id=proceso.id, detalle_errores=detalle, resultado="error"))
        db_session.flush()

    r = client.get(f"/api/v1/sincronizacion/procesos/{proceso.id}/logs", params={"por_pagina": 5}, headers=headers)

    assert r.status_code == 200, r.text
    assert r.json()["total"] == 3 and r.json()["total_paginas"] == 1
    detalles = sorted(
        (json.dumps(log["detalle_errores"]), json.dumps(log["actualizaciones"])) for log in r.json()["items"]
    )
    assert detalles == sorted(
        [('[{"tipo": "dni", "dni": "1"}]', '["a"]'), ('["viejo"]', "[]"), ('["no es json"]', "[]")]
    )
    procesos = client.get("/api/v1/sincronizacion/procesos", headers=headers).json()
    assert {"items", "total", "pagina", "por_pagina", "total_paginas"} <= set(procesos)


# operationId de lo que consume la SPA (F07-P09): el cliente TypeScript los usa como nombres de función, así que no
# cambian sin querer. Cambiar uno es cambiar el contrato: se actualiza acá y en la SPA a la vez.
OPERATION_IDS = {
    ("post", "/api/v1/auth/login"): "auth_login",
    ("post", "/api/v1/auth/verify-2fa"): "auth_verificar_2fa",
    ("post", "/api/v1/auth/seleccionar-empresa"): "auth_seleccionar_empresa",
    ("post", "/api/v1/auth/cambiar-empresa"): "auth_cambiar_empresa",
    ("post", "/api/v1/auth/refresh"): "auth_refrescar",
    ("post", "/api/v1/auth/logout"): "auth_logout",
    ("get", "/api/v1/auth/me"): "auth_sesion_actual",
    ("post", "/api/v1/auth/descargas"): "auth_firmar_descarga",
    ("get", "/api/v1/menus"): "menus_del_usuario",
    ("get", "/api/v1/sincronizacion/procesos"): "sincronizacion_listar_procesos",
    ("get", "/api/v1/sincronizacion/procesos/{id}"): "sincronizacion_obtener_proceso",
    ("put", "/api/v1/sincronizacion/procesos/{id}"): "sincronizacion_actualizar_proceso",
    ("post", "/api/v1/sincronizacion/procesos/{id}/ejecutar"): "sincronizacion_ejecutar_proceso",
    ("get", "/api/v1/sincronizacion/procesos/{id}/logs"): "sincronizacion_listar_logs",
    ("get", "/api/v1/parametros"): "parametros_listar",
    ("post", "/api/v1/parametros"): "parametros_crear",
    ("get", "/api/v1/parametros/{id}"): "parametros_obtener",
    ("put", "/api/v1/parametros/{id}"): "parametros_actualizar",
    ("put", "/api/v1/parametros/{id}/valor"): "parametros_actualizar_valor",
    ("delete", "/api/v1/parametros/{id}"): "parametros_eliminar",
    ("get", "/api/v1/parametros/webex-rooms"): "parametros_listar_webex_rooms",
}


def test_los_operation_id_de_la_spa_son_los_acordados(client):
    paths = client.get("/openapi.json").json()["paths"]

    actuales = {(metodo, path): paths[path][metodo]["operationId"] for metodo, path in OPERATION_IDS}

    assert actuales == OPERATION_IDS
    pilotos = {(m, p): op["operationId"] for p, ops in paths.items() if p.startswith(PILOTOS) for m, op in ops.items()}
    assert set(pilotos) <= set(OPERATION_IDS), "una operación nueva de un piloto necesita su operationId"
    assert all(re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+", o) for o in OPERATION_IDS.values())
