"""Endpoints autenticados para la bandeja personal de notificaciones."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, get_empresa_activa, require_admin
from backend.modules.notificaciones_internas.schemas import (
    NotificacionInternaAuditoria,
    NotificacionInternaAuditoriaItem,
    NotificacionInternaConteo,
    NotificacionInternaHistorial,
    NotificacionInternaList,
    NotificacionInternaResponse,
)
from backend.modules.notificaciones_internas.services import NotificacionInternaService
from backend.modules.usuarios.models import Usuario

router = APIRouter(tags=["notificaciones-internas"])


@router.get("/notificaciones-internas", response_model=NotificacionInternaList)
async def listar_notificaciones(
    limite: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    items = NotificacionInternaService.listar_para_usuario(db, empresa_id, current_user.id, limite)
    return NotificacionInternaList(
        items=[NotificacionInternaResponse.model_validate(item) for item in items],
        total_no_leidas=NotificacionInternaService.contar_no_leidas(db, empresa_id, current_user.id),
    )


@router.get("/notificaciones-internas/no-leidas", response_model=NotificacionInternaConteo)
async def contar_no_leidas(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    return NotificacionInternaConteo(
        total_no_leidas=NotificacionInternaService.contar_no_leidas(db, empresa_id, current_user.id)
    )


@router.get("/notificaciones-internas/historial", response_model=NotificacionInternaHistorial)
async def historial_notificaciones(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=10, le=100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    items, total = NotificacionInternaService.historial_para_usuario(
        db, empresa_id, current_user.id, pagina, por_pagina
    )
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return NotificacionInternaHistorial(
        items=[NotificacionInternaResponse.model_validate(item) for item in items],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=total_paginas,
    )


@router.get("/notificaciones-internas/auditoria", response_model=NotificacionInternaAuditoria)
async def auditoria_notificaciones(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=10, le=100),
    buscar: str | None = Query(None),
    origen: str | None = Query(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    _: Usuario = Depends(require_admin),
):
    items, total = NotificacionInternaService.historial_auditoria(db, empresa_id, pagina, por_pagina, buscar, origen)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    return NotificacionInternaAuditoria(
        items=[
            NotificacionInternaAuditoriaItem(
                **NotificacionInternaResponse.model_validate(notificacion).model_dump(),
                usuario_email=usuario.email,
                usuario_nombre=" ".join(filter(None, [usuario.nombre, usuario.apellido])),
            )
            for notificacion, usuario in items
        ],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=total_paginas,
    )


@router.put("/notificaciones-internas/leer-todas", response_model=NotificacionInternaConteo)
async def marcar_todas_leidas(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    NotificacionInternaService.marcar_todas_leidas(db, empresa_id, current_user.id)
    return NotificacionInternaConteo(total_no_leidas=0)


@router.put("/notificaciones-internas/{notificacion_id}/leer", response_model=NotificacionInternaResponse)
async def marcar_leida(
    notificacion_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        item = NotificacionInternaService.marcar_leida(db, empresa_id, current_user.id, notificacion_id)
        return NotificacionInternaResponse.model_validate(item)
    except ValueError, AttributeError:
        raise HTTPException(404, "Notificacion no encontrada")


@router.delete("/notificaciones-internas/{notificacion_id}")
async def eliminar_notificacion(
    notificacion_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = Depends(get_current_user),
):
    try:
        NotificacionInternaService.eliminar(db, empresa_id, current_user.id, notificacion_id)
    except ValueError, AttributeError:
        raise HTTPException(404, "Notificacion no encontrada")
    return {"ok": True}
