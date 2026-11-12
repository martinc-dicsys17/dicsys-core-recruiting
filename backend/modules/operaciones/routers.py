"""
Routers FastAPI para el módulo de Operaciones - Equipos.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.operaciones.schemas import (
    EquipoCreate,
    EquipoList,
    EquipoResponse,
    EquipoUpdate,
    IntegranteResponse,
    LiderResponse,
)
from backend.modules.operaciones.services import EquipoService

router = APIRouter(prefix="/operaciones", tags=["operaciones"])

# Shortcut de submódulo
require_equipos = Depends(require_submodulo("operaciones", "equipos"))


def _equipo_to_response(equipo) -> EquipoResponse:
    """Convierte un equipo a su schema de respuesta."""
    lider = None
    if equipo.lider_rel:
        lider = LiderResponse(
            id=str(equipo.lider_rel.id),
            codigo=equipo.lider_rel.codigo,
            apellido=equipo.lider_rel.apellido,
            nombre=equipo.lider_rel.nombre,
        )

    integrantes = [
        IntegranteResponse(id=str(emp.id), codigo=emp.codigo, apellido=emp.apellido, nombre=emp.nombre)
        for emp in equipo.integrantes
    ]

    return EquipoResponse(
        id=str(equipo.id),
        nombre=equipo.nombre,
        cliente_id=str(equipo.cliente_id) if equipo.cliente_id else None,
        lider_id=str(equipo.lider_id) if equipo.lider_id else None,
        lider=lider,
        activo=equipo.activo,
        integrantes=integrantes,
        created_at=equipo.created_at,
        updated_at=equipo.updated_at,
    )


@router.get("/equipos", response_model=EquipoList)
async def listar_equipos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_equipos,
):
    """Lista equipos con paginación y filtros."""
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if activo is not None:
        filtros["activo"] = activo

    resultado = EquipoService.listar(db, empresa_id, pagina, por_pagina, filtros)

    return EquipoList(
        items=[_equipo_to_response(e) for e in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@router.get("/equipos/{id}", response_model=EquipoResponse)
async def obtener_equipo(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_equipos,
):
    """Obtiene un equipo por ID."""
    equipo = EquipoService.obtener(db, empresa_id, id)
    if not equipo:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return _equipo_to_response(equipo)


@router.post("/equipos", response_model=EquipoResponse, status_code=201)
async def crear_equipo(
    datos: EquipoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_equipos,
):
    """Crea un nuevo equipo."""
    try:
        equipo = EquipoService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return _equipo_to_response(equipo)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/equipos/{id}", response_model=EquipoResponse)
async def actualizar_equipo(
    id: str,
    datos: EquipoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_equipos,
):
    """Actualiza un equipo existente."""
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    equipo = EquipoService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
    if not equipo:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    return _equipo_to_response(equipo)
