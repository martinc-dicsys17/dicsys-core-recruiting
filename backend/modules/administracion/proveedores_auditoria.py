"""
Auditoría del módulo Proveedores (D-67).

Cada alta, edición, baja, evaluación, cambio de campaña, importación confirmada
y envío de aviso deja una fila en proveedores_auditoria con quién, desde dónde,
cuándo y los valores antes/después. La tabla es append-only: este módulo solo
inserta.

La API la llama el frontend Flask, no el navegador: la IP y el navegador del
usuario llegan en X-Cliente-IP y X-Cliente-User-Agent (frontend/app.py). Si
faltan, se usa lo que ve el backend.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from backend.modules.administracion.proveedores_models import ProveedoresAuditoria


@dataclass(frozen=True)
class Actor:
    """Quién hace la acción y desde dónde."""

    usuario_id: Optional[uuid.UUID]
    email: Optional[str]
    ip: Optional[str] = None
    user_agent: Optional[str] = None

    @classmethod
    def desde_request(cls, request: Request, usuario) -> "Actor":
        ip = request.headers.get("x-cliente-ip") or (request.client.host if request.client else None)
        user_agent = request.headers.get("x-cliente-user-agent") or request.headers.get("user-agent")
        return cls(
            usuario_id=usuario.id,
            email=usuario.email,
            ip=(ip or None) and ip[:45],
            user_agent=(user_agent or None) and user_agent[:500],
        )


# Procesos automáticos (job de avisos): sin usuario ni IP
SISTEMA = Actor(usuario_id=None, email="cron@sistema")


def _serializable(valor: Any) -> Any:
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, (datetime, date, time)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return float(valor)
    return valor


def foto(objeto: Any, campos: Iterable[str]) -> Dict[str, Any]:
    """Valores actuales de `campos` del objeto, listos para JSONB."""
    return {campo: _serializable(getattr(objeto, campo)) for campo in campos}


def diferencias(antes: Dict[str, Any], despues: Dict[str, Any]) -> tuple:
    """Solo los campos que cambiaron, para no llenar la auditoría de ruido."""
    claves = [c for c in despues if antes.get(c) != despues.get(c)]
    return {c: antes.get(c) for c in claves}, {c: despues.get(c) for c in claves}


def registrar(
    db: Session,
    empresa_id: uuid.UUID,
    actor: Actor,
    entidad: str,
    entidad_id: uuid.UUID,
    accion: str,
    *,
    antes: Optional[Dict[str, Any]] = None,
    despues: Optional[Dict[str, Any]] = None,
    evaluacion_id: Optional[uuid.UUID] = None,
) -> ProveedoresAuditoria:
    """Agrega el evento a la sesión; se confirma junto con el cambio que audita."""
    evento = ProveedoresAuditoria(
        empresa_id=empresa_id,
        usuario_id=actor.usuario_id,
        usuario_email=actor.email,
        ip=actor.ip,
        user_agent=actor.user_agent,
        entidad=entidad,
        entidad_id=entidad_id,
        evaluacion_id=evaluacion_id,
        accion=accion,
        antes={k: _serializable(v) for k, v in antes.items()} if antes is not None else None,
        despues={k: _serializable(v) for k, v in despues.items()} if despues is not None else None,
    )
    db.add(evento)
    return evento
