"""Contratos HTTP ante fallos de servicios y recursos que ya no existen."""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from backend.modules.innovacion.licencias_models import Proveedor
from backend.modules.innovacion.licencias_services import (
    HerramientaService,
    LicenciaService,
    ProveedorService,
)
from backend.modules.nomina.models import Empleado
from backend.tests.helpers.auth import auth_headers

BASE = "/api/v1/innovacion"
ID = "00000000-0000-0000-0000-000000000001"
LICENCIA = {"herramienta_id": ID, "empleado_id": ID, "fecha_inicio": "2026-09-01"}
LOTE = {"herramienta_id": ID, "empleado_ids": [ID], "fecha_inicio": "2026-09-01"}
pytestmark = [pytest.mark.integration]

# El rollback explícito pertenece a los handlers de catálogo que abren o
# terminan su transacción. Los restantes delegan la transacción al servicio.
RUTAS = [
    (
        "post",
        "/proveedores",
        {"nombre": "Proveedor"},
        ProveedorService,
        "obtener_o_crear",
        "Error inesperado al crear el proveedor",
        True,
    ),
    (
        "put",
        f"/proveedores/{ID}",
        {"nombre": "Proveedor"},
        ProveedorService,
        "actualizar",
        "Error inesperado al actualizar el proveedor",
        True,
    ),
    (
        "delete",
        f"/proveedores/{ID}",
        None,
        ProveedorService,
        "eliminar",
        "Error inesperado al eliminar el proveedor",
        True,
    ),
    (
        "post",
        "/herramientas",
        {"nombre": "Herramienta"},
        HerramientaService,
        "crear",
        "Error inesperado al crear la herramienta",
        False,
    ),
    (
        "put",
        f"/herramientas/{ID}",
        {"nombre": "Herramienta"},
        HerramientaService,
        "actualizar",
        "Error inesperado al actualizar la herramienta",
        True,
    ),
    (
        "delete",
        f"/herramientas/{ID}",
        None,
        HerramientaService,
        "eliminar",
        "Error inesperado al eliminar la herramienta",
        True,
    ),
    ("post", "/licencias", LICENCIA, LicenciaService, "crear", "Error inesperado al crear la licencia", False),
    (
        "post",
        "/licencias/lote",
        LOTE,
        LicenciaService,
        "crear_lote",
        "No se pudo completar la asignacion de licencias",
        False,
    ),
    (
        "put",
        f"/licencias/{ID}",
        {"costo_mensual": "20.00"},
        LicenciaService,
        "actualizar",
        "Error inesperado al actualizar la licencia",
        False,
    ),
    (
        "put",
        f"/licencias/{ID}/activa/false",
        None,
        LicenciaService,
        "cambiar_activa",
        "Error inesperado al cambiar el estado",
        False,
    ),
]


@pytest.fixture
def acceso_errores(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])
    db_session.commit()
    return {"headers": auth_headers(usuario, empresa), "empresa_id": empresa.id, "email": usuario.email}


@pytest.mark.parametrize(
    "metodo,ruta,datos,servicio,funcion,detalle,rollback",
    RUTAS,
    ids=[f"{metodo}-{ruta}" for metodo, ruta, *_ in RUTAS],
)
def test_fallo_interno_responde_error_publico_y_revierte_transaccion_del_router(
    client,
    db_session,
    acceso_errores,
    monkeypatch,
    metodo,
    ruta,
    datos,
    servicio,
    funcion,
    detalle,
    rollback,
):
    marcador = uuid.uuid4()
    llamadas = []

    def fallar(db, empresa_id, *args, **kwargs):
        llamadas.append((empresa_id, kwargs["usuario"]))
        if rollback:
            db.add(
                Proveedor(
                    id=marcador,
                    empresa_id=empresa_id,
                    nombre="Cambio pendiente",
                    nombre_normalizado="cambio pendiente",
                    activo=True,
                )
            )
            db.flush()
        raise RuntimeError("Detalle interno de la base de datos")

    monkeypatch.setattr(servicio, funcion, fallar)
    respuesta = client.request(metodo, BASE + ruta, headers=acceso_errores["headers"], json=datos)

    assert respuesta.status_code == 500, respuesta.text
    assert respuesta.json() == {"detail": detalle}
    assert llamadas == [(acceso_errores["empresa_id"], acceso_errores["email"])]
    if rollback:
        assert db_session.get(Proveedor, marcador) is None


@pytest.mark.parametrize(
    "metodo,ruta,datos,servicio,funcion",
    [
        (metodo, ruta, datos, servicio, funcion)
        for metodo, ruta, datos, servicio, funcion, *_ in RUTAS
        if (servicio, funcion)
        in {
            (HerramientaService, "crear"),
            (HerramientaService, "actualizar"),
            (HerramientaService, "eliminar"),
            (ProveedorService, "eliminar"),
            (LicenciaService, "crear"),
        }
    ],
)
def test_conserva_status_y_detalle_de_un_error_http_del_servicio(
    client,
    acceso_errores,
    monkeypatch,
    metodo,
    ruta,
    datos,
    servicio,
    funcion,
):
    def limite_del_servicio(*args, **kwargs):
        raise HTTPException(status_code=503, detail="Servicio temporalmente no disponible")

    monkeypatch.setattr(servicio, funcion, limite_del_servicio)
    respuesta = client.request(metodo, BASE + ruta, headers=acceso_errores["headers"], json=datos)

    assert respuesta.status_code == 503, respuesta.text
    assert respuesta.json() == {"detail": "Servicio temporalmente no disponible"}


@pytest.mark.parametrize(
    "ruta,datos,funcion,status",
    [
        ("/licencias", LICENCIA, "crear", 409),
        ("/licencias/lote", LOTE, "crear_lote", 409),
        (f"/licencias/{ID}/activa/false", None, "cambiar_activa", 400),
    ],
)
def test_error_de_dominio_conserva_detalle_y_status(
    client,
    acceso_errores,
    monkeypatch,
    ruta,
    datos,
    funcion,
    status,
):
    def rechazar(*args, **kwargs):
        raise ValueError("La operación no se puede completar")

    monkeypatch.setattr(LicenciaService, funcion, rechazar)
    respuesta = client.request(
        "put" if funcion == "cambiar_activa" else "post",
        BASE + ruta,
        headers=acceso_errores["headers"],
        json=datos,
    )
    assert respuesta.status_code == status, respuesta.text
    assert respuesta.json() == {"detail": "La operación no se puede completar"}


@pytest.mark.parametrize(
    "metodo,sufijo,datos",
    [
        ("get", "", None),
        ("put", "", {"costo_mensual": "20.00"}),
        ("delete", "", None),
        ("put", "/activa/false", None),
    ],
)
def test_licencia_inexistente_responde_404(client, acceso_errores, metodo, sufijo, datos):
    respuesta = client.request(
        metodo,
        f"{BASE}/licencias/{ID}{sufijo}",
        headers=acceso_errores["headers"],
        json=datos,
    )
    assert respuesta.status_code == 404, respuesta.text
    assert respuesta.json() == {"detail": "Licencia no encontrada"}


def test_edicion_sin_datos_responde_400_antes_de_consultar_servicio(client, acceso_errores, monkeypatch):
    def no_debe_consultar(*args, **kwargs):
        pytest.fail("Un body vacío no debe llegar al servicio")

    monkeypatch.setattr(LicenciaService, "actualizar", no_debe_consultar)
    respuesta = client.put(f"{BASE}/licencias/{ID}", headers=acceso_errores["headers"], json={})
    assert respuesta.status_code == 400, respuesta.text
    assert respuesta.json() == {"detail": "No hay datos para actualizar"}


def test_proveedor_sin_nombre_util_responde_422_sin_crear_fila(client, db_session, acceso_errores):
    respuesta = client.post(f"{BASE}/proveedores", headers=acceso_errores["headers"], json={"nombre": "   "})
    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json() == {"detail": "El nombre es obligatorio"}
    assert db_session.query(Proveedor).filter(Proveedor.empresa_id == acceso_errores["empresa_id"]).count() == 0


def test_ruta_de_activacion_actualiza_licencia_y_metricas(client, db_session, acceso_errores):
    empleado = Empleado(
        id=uuid.uuid4(),
        empresa_id=acceso_errores["empresa_id"],
        codigo="ACT-001",
        apellido="Prueba",
        nombre="Activación",
        cuil=20900001001,
        dni=90000101,
        activo=True,
    )
    db_session.add(empleado)
    db_session.flush()
    headers = acceso_errores["headers"]
    herramienta = client.post(f"{BASE}/herramientas", headers=headers, json={"nombre": "Activación"})
    assert herramienta.status_code == 201, herramienta.text
    creada = client.post(
        f"{BASE}/licencias",
        headers=headers,
        json={
            "herramienta_id": herramienta.json()["id"],
            "empleado_id": str(empleado.id),
            "fecha_inicio": date.today().replace(day=1).isoformat(),
            "costo_mensual": "20.00",
            "moneda": "USD",
        },
    )
    assert creada.status_code == 201, creada.text
    licencia_id = creada.json()["id"]
    for activa, total in [(False, 0.0), (True, 20.0)]:
        respuesta = client.put(f"{BASE}/licencias/{licencia_id}/activa/{str(activa).lower()}", headers=headers)
        assert respuesta.status_code == 200, respuesta.text
        assert respuesta.json()["activa"] is activa
        assert respuesta.json()["id"] == licencia_id
        listado = client.get(f"{BASE}/licencias/por-empleado", headers=headers)
        assert listado.status_code == 200, listado.text
        esperado = [{"moneda": "USD", "total": total}] if activa else []
        assert listado.json()["metricas"]["mes_actual"] == esperado
