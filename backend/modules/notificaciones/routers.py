"""
Routers para el módulo Notificaciones.
Protegido a nivel de main.py con require_modulo('notificaciones').
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core import webex_oauth
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.modules.notificaciones.schemas import (
    CumpleaneroResponse,
    CumpleanerosHoy,
    NotificacionLogList,
    NotificacionLogResponse,
    ProcesoResponse,
    WebexReaderCode,
    WebexReaderEstado,
)
from backend.modules.notificaciones.services import NotificacionService
from backend.modules.usuarios.models import Usuario

router = APIRouter(tags=["notificaciones"])
logger = logging.getLogger(__name__)


@router.get("/notificaciones/logs", response_model=NotificacionLogList)
async def listar_logs(
    estado: Optional[str] = Query(None, description="Filtrar por estado (pendiente, procesando, enviado, error)"),
    fecha: Optional[date] = Query(None, description="Filtrar por fecha del evento (AAAA-MM-DD)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Log de notificaciones, más recientes primero."""
    items = NotificacionService.listar_logs(db, estado=estado, fecha=fecha, limit=limit)
    return NotificacionLogList(
        items=[NotificacionLogResponse.model_validate(log) for log in items],
        total=len(items),
    )


@router.get("/notificaciones/cumpleanos/hoy", response_model=CumpleanerosHoy)
async def cumpleaneros_hoy(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Empleados que cumplen años hoy y estado del proceso de envío."""
    items = NotificacionService.buscar_cumpleaneros(db)
    return CumpleanerosHoy(
        items=[CumpleaneroResponse.model_validate(e) for e in items],
        total=len(items),
        en_ejecucion=NotificacionService.proceso_en_ejecucion(),
    )


@router.post("/notificaciones/cumpleanos/procesar", response_model=ProcesoResponse)
async def procesar_cumpleanos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Dispara el proceso de envío de saludos de cumpleaños en background.
    Procesa una persona a la vez con una espera aleatoria entre envíos.
    """
    if NotificacionService.proceso_en_ejecucion():
        raise HTTPException(409, "Ya hay un proceso de envío en ejecución")

    cumpleaneros = NotificacionService.buscar_cumpleaneros(db)
    if not cumpleaneros:
        return ProcesoResponse(message="No hay cumpleañeros hoy", en_ejecucion=False)

    if not NotificacionService.iniciar_proceso_cumpleanos(usuario=current_user.email):
        raise HTTPException(409, "Ya hay un proceso de envío en ejecución")

    logger.info(f"🎂 Proceso de cumpleaños iniciado por {current_user.email} ({len(cumpleaneros)} cumpleañeros)")
    return ProcesoResponse(
        message=f"Proceso iniciado: {len(cumpleaneros)} cumpleañero(s) hoy",
        en_ejecucion=True,
    )


@router.get("/notificaciones/webex-reader", response_model=WebexReaderEstado)
async def webex_reader_estado(
    redirect_uri: Optional[str] = Query(None, description="Callback del frontend (derivado de su host)"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Estado de la cuenta lectora de Webex (integración OAuth)."""
    return WebexReaderEstado(**webex_oauth.estado(db, redirect_uri=redirect_uri))


@router.post("/notificaciones/webex-reader/code", response_model=WebexReaderEstado)
async def webex_reader_code(
    datos: WebexReaderCode,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Canjea el authorization code del callback OAuth y guarda los tokens."""
    if not webex_oauth.validar_state(datos.state):
        raise HTTPException(400, "State inválido: reintentá la autorización desde la página de Notificaciones")
    try:
        webex_oauth.exchange_code(db, datos.code, usuario=current_user.email, redirect_uri=datos.redirect_uri)
    except webex_oauth.WebexOAuthError as e:
        logger.error(f"Error al canjear el code de Webex: {e}")
        raise HTTPException(502, f"No se pudo conectar la cuenta lectora: {e}")
    return WebexReaderEstado(**webex_oauth.estado(db))
