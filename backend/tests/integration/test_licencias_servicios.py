"""Contratos de dominio y reversión de escrituras de Gestión de Licencias."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from backend.modules.innovacion.licencias_models import Herramienta, Licencia, Proveedor
from backend.modules.innovacion.licencias_schemas import (
    HerramientaCreate,
    HerramientaUpdate,
    LicenciaCreate,
    LicenciaUpdate,
)
from backend.modules.innovacion.licencias_services import (
    HerramientaService,
    LicenciaService,
    ProveedorService,
    ReferenciaInvalida,
)
from backend.tests.integration.test_licencias_validaciones import auditoria_licencias  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def vigente(db_session, auditoria_licencias):  # noqa: F811
    return db_session.get(Licencia, uuid.UUID(auditoria_licencias["licencia_id"]))


@pytest.mark.parametrize("dias", [None, -3, 0, 7])
def test_vencimiento(dias):
    licencia = Licencia(fecha_fin=date.today() + timedelta(days=dias) if dias is not None else None)
    assert licencia.esta_vencida == (dias is not None and dias < 0)


@pytest.mark.parametrize(
    "schema,datos",
    [
        (HerramientaCreate, {"nombre": "Editor"}),
        (HerramientaUpdate, {}),
        (LicenciaCreate, {"herramienta_id": "h", "empleado_id": "e", "fecha_inicio": "2026-09-01"}),
        (LicenciaUpdate, {}),
    ],
)
def test_moneda_desconocida_se_rechaza_en_altas_y_ediciones(schema, datos):
    with pytest.raises(ValidationError, match="Moneda debe ser"):
        schema(**datos, moneda="EUR")


def test_campos_opcionales_del_catalogo_no_fuerzan_moneda():
    assert HerramientaUpdate(moneda=None).model_dump(exclude_unset=True) == {"moneda": None}


def test_catalogo_equipos_vacio_no_inventa_pertenencias(db_session, vigente):
    assert LicenciaService.listar_equipos(db_session, vigente.empresa_id) == []


@pytest.mark.parametrize(
    "operacion", ["proveedor_nuevo", "proveedor_editar", "herramienta_nueva", "herramienta_editar"]
)
def test_nombres_en_blanco_no_crean_ni_destruyen_catalogos(db_session, vigente, operacion):
    empresa_id = vigente.empresa_id
    if operacion == "proveedor_nuevo":
        assert ProveedorService.obtener_o_crear(db_session, empresa_id, "   ") is None
    elif operacion == "proveedor_editar":
        proveedor = ProveedorService.obtener_o_crear(db_session, empresa_id, "Proveedor")
        db_session.commit()
        with pytest.raises(ValueError, match="obligatorio"):
            ProveedorService.actualizar(db_session, empresa_id, str(proveedor.id), "   ")
        assert proveedor.nombre == "Proveedor"
    elif operacion == "herramienta_nueva":
        with pytest.raises(ValueError, match="obligatorio"):
            HerramientaService.crear(db_session, empresa_id, {"nombre": "   "})
    else:
        with pytest.raises(ValueError, match="obligatorio"):
            HerramientaService.actualizar(db_session, empresa_id, str(vigente.herramienta_id), {"nombre": "   "})
        assert db_session.get(Herramienta, vigente.herramienta_id).nombre == "Sin proveedor"
    assert db_session.query(Herramienta).filter_by(empresa_id=empresa_id).count() == 1


@pytest.mark.parametrize("operacion", ["proveedor", "herramienta", "licencia"])
def test_conflicto_al_confirmar_revierte_la_escritura(db_session, vigente, monkeypatch, operacion):
    empresa_id = vigente.empresa_id
    proveedor = ProveedorService.obtener_o_crear(db_session, empresa_id, "Original")
    db_session.commit()
    proveedor_id = proveedor.id
    datos = {
        "herramienta_id": str(vigente.herramienta_id),
        "empleado_id": str(vigente.empleado_id),
        "fecha_inicio": date.today(),
        "moneda": "USD",
    }

    def conflicto():
        db_session.flush()
        raise IntegrityError("COMMIT", {}, RuntimeError("Conflicto concurrente simulado"))

    monkeypatch.setattr(db_session, "commit", conflicto)
    with pytest.raises(ValueError):
        if operacion == "proveedor":
            ProveedorService.actualizar(db_session, empresa_id, str(proveedor_id), "Nuevo nombre")
        elif operacion == "herramienta":
            HerramientaService.crear(db_session, empresa_id, {"nombre": "Nueva herramienta"})
        else:
            LicenciaService.crear(db_session, empresa_id, datos)
    assert db_session.get(Proveedor, proveedor_id).nombre == "Original"
    assert db_session.query(Herramienta).filter_by(empresa_id=empresa_id).count() == 1
    assert db_session.query(Licencia).filter_by(empresa_id=empresa_id).count() == 1


def test_servicio_preserva_identidad_empresa_y_auditoria_al_editar(db_session, vigente):
    licencia_id, empresa_id = vigente.id, vigente.empresa_id
    vigente.updated_by = "autor-original"
    db_session.commit()
    editada = LicenciaService.actualizar(
        db_session,
        empresa_id,
        str(licencia_id),
        {
            "id": uuid.uuid4(),
            "empresa_id": uuid.uuid4(),
            "campo_desconocido": "ignorado",
            "costo_mensual": Decimal("12.50"),
        },
    )
    assert (editada.id, editada.empresa_id, editada.updated_by) == (licencia_id, empresa_id, "autor-original")
    assert editada.costo_mensual == Decimal("12.50")
    desactivada = LicenciaService.cambiar_activa(db_session, empresa_id, str(licencia_id), False)
    assert desactivada.activa is False
    assert desactivada.updated_by == "autor-original"


def test_alta_directa_admite_autor_opcional_y_catalogo_sin_proveedor(db_session, vigente):
    herramienta = HerramientaService.crear(
        db_session,
        vigente.empresa_id,
        {
            "nombre": "Otra herramienta",
            "proveedor_nombre": "   ",
        },
    )
    assert herramienta.proveedor_id is None
    herramienta = HerramientaService.actualizar(
        db_session,
        vigente.empresa_id,
        str(herramienta.id),
        {
            "proveedor_nombre": "   ",
        },
    )
    assert herramienta.proveedor_id is None
    licencia = LicenciaService.crear(
        db_session,
        vigente.empresa_id,
        {
            "herramienta_id": str(herramienta.id),
            "empleado_id": str(vigente.empleado_id),
            "fecha_inicio": date.today(),
            "moneda": "ARS",
        },
    )
    assert licencia.updated_by is None
    assert licencia.activa is True


@pytest.mark.parametrize("seleccion", [[], ["invalido"]])
def test_servicio_lote_rechaza_seleccion_vacia_o_invalida(db_session, vigente, seleccion):
    with pytest.raises(ReferenciaInvalida):
        LicenciaService.crear_lote(
            db_session,
            vigente.empresa_id,
            {
                "herramienta_id": str(vigente.herramienta_id),
                "empleado_ids": seleccion,
                "fecha_inicio": date.today(),
                "moneda": "ARS",
            },
        )
    assert db_session.query(Licencia).filter_by(empresa_id=vigente.empresa_id).count() == 1


def test_tendencia_mixta_preserva_importes_por_moneda(db_session, vigente):
    vigente.fecha_inicio, vigente.fecha_fin = date(2026, 12, 1), date(2026, 12, 31)
    vigente.costo_mensual = Decimal("10.00")
    vigente.moneda = "USD"
    db_session.add(
        Licencia(
            empresa_id=vigente.empresa_id,
            empleado_id=vigente.empleado_id,
            herramienta_id=vigente.herramienta_id,
            fecha_inicio=date(2027, 1, 1),
            moneda="ARS",
            costo_mensual=Decimal("20.00"),
            activa=True,
        )
    )
    db_session.commit()
    metricas = LicenciaService.metricas_gasto(db_session, vigente.empresa_id, hoy=date(2027, 1, 15))
    assert metricas["tendencia"] == "mixta"
    assert metricas["mes_anterior"] == [{"moneda": "ARS", "total": 0.0}, {"moneda": "USD", "total": 10.0}]
    assert metricas["mes_actual"] == [{"moneda": "ARS", "total": 20.0}, {"moneda": "USD", "total": 0.0}]
    assert metricas["delta"] == [{"moneda": "ARS", "total": 20.0}, {"moneda": "USD", "total": -10.0}]
