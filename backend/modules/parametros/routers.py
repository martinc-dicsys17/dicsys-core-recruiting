"""
Routers para el módulo Parámetros.
Protegido a nivel de main.py con require_submodulo('configuracion', 'parametros').

Contrato auditado para el piloto de v2 (F07-P08): response_model en todo, errores con core/errores.Error, ids UUID
(uno mal formado da 422) y el listado con core/paginacion.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.errores import responde
from backend.core.paginacion import MAXIMO, POR_PAGINA, paginar
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.modules.parametros.schemas import (
    Mensaje,
    ParametroCreate,
    ParametroList,
    ParametroResponse,
    ParametroUpdate,
    ParametroValorUpdate,
    WebexRooms,
)
from backend.modules.parametros.services import ParametroService, ValorInvalido
from backend.modules.usuarios.models import Usuario

router = APIRouter(tags=["parametros"], responses=responde(401, 403))
logger = logging.getLogger(__name__)


@router.get("/parametros", response_model=ParametroList, operation_id="parametros_listar")
async def listar_parametros(
    buscar: Optional[str] = Query(None, description="Búsqueda libre por nombre, key o descripción"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA, ge=1, le=MAXIMO),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Listado de parámetros del sistema."""
    items, datos = paginar(ParametroService.consulta(db, buscar=buscar, categoria=categoria), pagina, por_pagina)
    return ParametroList(
        items=[ParametroResponse.model_validate(p) for p in items],
        **datos,
        categorias=ParametroService.listar_categorias(db),
    )


@router.get("/parametros/webex-rooms", response_model=WebexRooms, operation_id="parametros_listar_webex_rooms")
async def listar_webex_rooms(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Lista los espacios del team de Webex (GET /v1/rooms?teamId=) para el
    selector multi-opción del parámetro webex_sync_espacios. Llamada con timeout;
    si falla, devuelve success=False y la UI cae al fallback (selección actual).
    """
    from backend.core import config
    from backend.core.webex import webex_service

    team_id = config.get_parameter("webex_team_dicsys_id", "", db=db)
    if not team_id:
        return {"success": False, "error": "Falta configurar el Team ID de Webex (webex_team_dicsys_id)", "rooms": []}
    if not webex_service.is_configured:
        return {"success": False, "error": "Webex no está configurado (WEBEX_BOT_TOKEN)", "rooms": []}

    res = webex_service.list_rooms_by_team(team_id, timeout=15.0)
    if not res.get("success"):
        return {"success": False, "error": res.get("error") or "No se pudieron listar los espacios", "rooms": []}
    return {"success": True, "rooms": res.get("rooms", [])}


@router.get(
    "/parametros/{id}", response_model=ParametroResponse, responses=responde(404), operation_id="parametros_obtener"
)
async def obtener_parametro(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Obtiene un parámetro por ID."""
    parametro = ParametroService.obtener(db, id)
    if not parametro:
        raise HTTPException(404, "Parámetro no encontrado")
    return ParametroResponse.model_validate(parametro)


@router.post(
    "/parametros",
    response_model=ParametroResponse,
    status_code=201,
    responses=responde(409),
    operation_id="parametros_crear",
)
async def crear_parametro(
    datos: ParametroCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea un nuevo parámetro."""
    try:
        parametro = ParametroService.crear(db, datos.model_dump(), usuario=current_user.email)
        return ParametroResponse.model_validate(parametro)
    except ValorInvalido as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al crear parámetro: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el parámetro")


@router.put(
    "/parametros/{id}",
    response_model=ParametroResponse,
    responses=responde(404, 409),
    operation_id="parametros_actualizar",
)
async def actualizar_parametro(
    id: uuid.UUID,
    datos: ParametroUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza la definición de un parámetro."""
    try:
        parametro = ParametroService.actualizar(db, id, datos.model_dump(), usuario=current_user.email)
    except ValorInvalido as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))
    if not parametro:
        raise HTTPException(404, "Parámetro no encontrado")
    return ParametroResponse.model_validate(parametro)


@router.put(
    "/parametros/{id}/valor",
    response_model=ParametroResponse,
    responses=responde(404),
    operation_id="parametros_actualizar_valor",
)
async def actualizar_valor_parametro(
    id: uuid.UUID,
    datos: ParametroValorUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza solo el valor de un parámetro (edición inline en la UI principal)."""
    try:
        parametro = ParametroService.actualizar_valor(db, id, datos.valor, usuario=current_user.email)
    except ValorInvalido as e:
        raise HTTPException(422, str(e))
    if not parametro:
        raise HTTPException(404, "Parámetro no encontrado")
    return ParametroResponse.model_validate(parametro)


@router.delete("/parametros/{id}", response_model=Mensaje, responses=responde(404), operation_id="parametros_eliminar")
async def eliminar_parametro(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina (soft delete) un parámetro."""
    if not ParametroService.eliminar(db, id, usuario=current_user.email):
        raise HTTPException(404, "Parámetro no encontrado")
    return Mensaje(message="Parámetro eliminado")
