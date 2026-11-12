"""
Piezas compartidas por el registro de proveedores y su evaluación: la fecha en
hora Argentina, cuál es la evaluación activa y cómo entra un proveedor en ella.

Viven acá para que registro, evaluación, importación y avisos no se importen
entre sí.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.modules.administracion.proveedores_auditoria import Actor, registrar
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    RegistroProveedor,
)

# Argentina no tiene horario de verano: UTC-3 fijo, sin depender de tzdata.
ZONA_ARGENTINA = timezone(timedelta(hours=-3), "ART")


def ahora_argentina() -> datetime:
    return datetime.now(ZONA_ARGENTINA)


def hoy_argentina() -> date:
    return ahora_argentina().date()


class ReferenciaInvalida(Exception):
    """Una referencia apunta a algo que no existe o es de otra empresa (404, sin decir cuál)."""


def uuid_o_none(valor) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(valor))
    except ValueError, AttributeError, TypeError:
        return None


# ─── Datos obligatorios del registro ───────────────────────────────────────────


def datos_faltantes(*, referente, servicio_provisto, tipo_informacion, acuerdo_servicio, politica_nda) -> List[str]:
    """
    Lo que le falta a un proveedor para guardarse: lo usan el form, la API y la
    importación del Sheet. El adjunto del acuerdo firmado se controla aparte,
    porque depende del storage y no de los datos.
    """
    faltan = [
        etiqueta
        for valor, etiqueta in (
            (referente, "usuario referente"),
            (servicio_provisto, "servicio / bien provisto"),
            (tipo_informacion, "tipo de información que manejan"),
            (acuerdo_servicio, "¿hay acuerdo de servicio firmado? (Sí o No)"),
        )
        if not valor
    ]
    if acuerdo_servicio == "No" and not politica_nda:
        faltan.append("política de seguridad / NDA (sin acuerdo firmado es obligatoria)")
    return faltan


# ─── Evaluación activa (D-65, D-71, D-74) ──────────────────────────────────────


def evaluacion_vigente(db: Session, empresa_id: uuid.UUID) -> Optional[EvaluacionProveedores]:
    """La última evaluación, mientras no la reemplace otra (puede estar cerrada)."""
    return (
        db.query(EvaluacionProveedores)
        .filter(
            EvaluacionProveedores.empresa_id == empresa_id,
            EvaluacionProveedores.reemplazada_at.is_(None),
            EvaluacionProveedores.deleted_at.is_(None),
        )
        .first()
    )


def estado_evaluacion(evaluacion: EvaluacionProveedores, hoy: Optional[date] = None) -> str:
    """programada · abierta · cerrada · reemplazada."""
    hoy = hoy or hoy_argentina()
    if evaluacion.reemplazada_at is not None:
        return "reemplazada"
    if hoy > evaluacion.fecha_cierre:
        return "cerrada"
    if hoy < evaluacion.fecha_apertura:
        return "programada"
    return "abierta"


def es_activa(evaluacion: Optional[EvaluacionProveedores], hoy: Optional[date] = None) -> bool:
    """Activa = la vigente sin pasar el cierre (también antes de abrir, para cargarla)."""
    return evaluacion is not None and estado_evaluacion(evaluacion, hoy) in ("programada", "abierta")


def evaluacion_activa(db: Session, empresa_id: uuid.UUID) -> Optional[EvaluacionProveedores]:
    evaluacion = evaluacion_vigente(db, empresa_id)
    return evaluacion if es_activa(evaluacion) else None


def item_de(db: Session, evaluacion_id: uuid.UUID, proveedor_id: uuid.UUID) -> Optional[EvaluacionItem]:
    return (
        db.query(EvaluacionItem)
        .filter(
            EvaluacionItem.evaluacion_id == evaluacion_id,
            EvaluacionItem.proveedor_id == proveedor_id,
            EvaluacionItem.deleted_at.is_(None),
        )
        .first()
    )


def asegurar_item(
    db: Session, evaluacion: EvaluacionProveedores, proveedor: RegistroProveedor, actor: Actor
) -> EvaluacionItem:
    """El proveedor entra en la evaluación con su referente como evaluador (D-72, D-75)."""
    item = item_de(db, evaluacion.id, proveedor.id)
    if item is not None:
        return item
    item = EvaluacionItem(
        id=uuid.uuid4(),
        empresa_id=evaluacion.empresa_id,
        evaluacion_id=evaluacion.id,
        proveedor_id=proveedor.id,
        evaluador_empleado_id=proveedor.referente_empleado_id,
        created_by=actor.email,
        updated_by=actor.email,
    )
    db.add(item)
    registrar(
        db,
        evaluacion.empresa_id,
        actor,
        "item",
        item.id,
        "crear",
        evaluacion_id=evaluacion.id,
        despues={"proveedor_id": proveedor.id, "evaluador_empleado_id": proveedor.referente_empleado_id},
    )
    return item
