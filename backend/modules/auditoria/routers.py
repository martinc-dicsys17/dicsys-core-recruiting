"""
Routers del módulo de Auditoría.

Dos routers:
- router (protegido): GET /auditoria → listar logs de la empresa activa.
- public_router (solo JWT + empresa): POST /auditoria → registrar navegación.

POST está disponible para cualquier usuario logueado con empresa activa, porque
cualquier pantalla del sistema dispara un log al ser visitada.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa
from backend.modules.auditoria.schemas import (
    AuditoriaLogCreate,
    AuditoriaLogList,
    AuditoriaLogResponse,
)
from backend.modules.auditoria.services import AuditoriaLogService
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auditoria", tags=["auditoria"])
public_router = APIRouter(prefix="/auditoria", tags=["auditoria"])


@public_router.post("", response_model=AuditoriaLogResponse, status_code=201)
async def crear_log(
    datos: AuditoriaLogCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
):
    """Registra una navegación.

    Cualquier usuario logueado con empresa activa puede crear logs sobre sí mismo.
    Anti-spoofing: el `email_usuario` se sobrescribe con el del JWT.
    """
    payload = datos.model_dump()
    payload["email_usuario"] = current_user.email

    try:
        log = AuditoriaLogService.crear(
            db=db,
            empresa_id=empresa_id,
            datos=payload,
            usuario=current_user.email,
        )
        return AuditoriaLogResponse.model_validate(log)
    except Exception as e:
        logger.error(f"Error al crear log de auditoría: {e}", exc_info=True)
        raise HTTPException(500, "Error al registrar la navegación")


@router.get("", response_model=AuditoriaLogList)
async def listar(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
    buscar_email: Optional[str] = None,
    buscar_modulo: Optional[str] = None,
    buscar_ruta: Optional[str] = None,
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
):
    """Lista logs paginados de la empresa activa, ordenados por fecha desc."""
    filtros = {
        "buscar_email": buscar_email,
        "buscar_modulo": buscar_modulo,
        "buscar_ruta": buscar_ruta,
        "desde": desde,
        "hasta": hasta,
    }
    resultado = AuditoriaLogService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return AuditoriaLogList(
        items=[AuditoriaLogResponse.model_validate(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )
