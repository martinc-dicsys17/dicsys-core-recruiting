"""
Routers para Sincronización de Datos.

Contrato auditado para el piloto de v2 (F07-P08): response_model en todo, errores con core/errores.Error, ids UUID
(uno mal formado da 422) y los listados con core/paginacion.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.core.errores import responde
from backend.core.paginacion import MAXIMO, POR_PAGINA, paginar
from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.sincronizacion.schemas import (
    EjecucionResponse,
    LogList,
    LogResponse,
    ProcesoList,
    ProcesoResponse,
    ProcesoUpdate,
)
from backend.modules.sincronizacion.services import SincronizacionService

router = APIRouter(prefix="/sincronizacion", tags=["Sincronización"], responses=responde(401, 403))

require_actualizacion_datos = Depends(require_submodulo("configuracion", "actualizacion_datos"))


def _proceso(db: Session, id: uuid.UUID):
    proceso = SincronizacionService.obtener(db, str(id))
    if not proceso:
        raise HTTPException(404, "Proceso no encontrado")
    return proceso


@router.get("/procesos", response_model=ProcesoList, operation_id="sincronizacion_listar_procesos")
async def listar_procesos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA, ge=1, le=MAXIMO),
    db: Session = Depends(get_db),
    current_user=require_actualizacion_datos,
):
    """Lista los procesos de sincronización."""
    items, datos = paginar(SincronizacionService.consulta(db), pagina, por_pagina)
    return ProcesoList(items=[ProcesoResponse.from_orm_custom(p) for p in items], **datos)


@router.get(
    "/procesos/{id}",
    response_model=ProcesoResponse,
    responses=responde(404),
    operation_id="sincronizacion_obtener_proceso",
)
async def obtener_proceso(id: uuid.UUID, db: Session = Depends(get_db), current_user=require_actualizacion_datos):
    """Obtiene un proceso por ID."""
    return ProcesoResponse.from_orm_custom(_proceso(db, id))


@router.put(
    "/procesos/{id}",
    response_model=ProcesoResponse,
    responses=responde(400, 404),
    operation_id="sincronizacion_actualizar_proceso",
)
async def actualizar_proceso(
    id: uuid.UUID, datos: ProcesoUpdate, db: Session = Depends(get_db), current_user=require_actualizacion_datos
):
    """Actualiza un proceso."""
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos para actualizar")

    proceso = SincronizacionService.actualizar(db, str(id), datos_dict)
    if not proceso:
        raise HTTPException(404, "Proceso no encontrado")
    return ProcesoResponse.from_orm_custom(proceso)


@router.post(
    "/procesos/{id}/ejecutar",
    response_model=EjecucionResponse,
    responses=responde(404, 409),
    operation_id="sincronizacion_ejecutar_proceso",
)
async def ejecutar_proceso(
    id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_actualizacion_datos,
):
    """Ejecuta un proceso de sincronización y devuelve el resultado; `exito` dice si la corrida anduvo. Un proceso que
    no existe da 404 y uno desactivado, 409. El log registra como ejecutor a quien llama."""
    if not _proceso(db, id).activo:
        raise HTTPException(409, "El proceso está desactivado")
    resultado = SincronizacionService.ejecutar_sincronizacion(db, str(id), current_user.email, empresa_id=empresa_id)
    return EjecucionResponse(**resultado)


@router.get(
    "/procesos/{id}/logs",
    response_model=LogList,
    responses=responde(404),
    operation_id="sincronizacion_listar_logs",
)
async def obtener_logs(
    id: uuid.UUID,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA, ge=1, le=MAXIMO),
    db: Session = Depends(get_db),
    current_user=require_actualizacion_datos,
):
    """Logs de ejecución de un proceso, del más nuevo al más viejo."""
    _proceso(db, id)
    items, datos = paginar(SincronizacionService.consulta_logs(db, str(id)), pagina, por_pagina)
    return LogList(items=[LogResponse.del_log(log) for log in items], **datos)
