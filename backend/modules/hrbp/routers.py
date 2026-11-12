"""
Routers HRBP - Endpoints FastAPI
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.hrbp.schemas import (
    AjusteStockCreate,
    EmpleadoSimple,
    EntregaCreate,
    EntregaList,
    EntregaResponse,
    ItemTipoCreate,
    ItemTipoList,
    ItemTipoResponse,
    ItemTipoUpdate,
    UsuarioSimple,
)
from backend.modules.hrbp.services import EntregaService, ItemTipoService

router = APIRouter(prefix="/hrbp", tags=["hrbp"])

# Shortcuts de submódulo
require_items = Depends(require_submodulo("hrbp", "gestion_items"))
require_entregas = Depends(require_submodulo("hrbp", "entregas"))


# === ITEM TIPOS ===
@router.get("/items", response_model=ItemTipoList)
async def listar_items(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    stock_bajo: Optional[bool] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if stock_bajo:
        filtros["stock_bajo"] = stock_bajo

    resultado = ItemTipoService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return ItemTipoList(
        items=[ItemTipoResponse.model_validate(i) for i in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@router.get("/items/{id}", response_model=ItemTipoResponse)
async def obtener_item(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    item = ItemTipoService.obtener(db, empresa_id, id)
    if not item:
        raise HTTPException(404, "Item no encontrado")
    return ItemTipoResponse.model_validate(item)


@router.post("/items", response_model=ItemTipoResponse, status_code=201)
async def crear_item(
    datos: ItemTipoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    try:
        item = ItemTipoService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return ItemTipoResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/items/{id}", response_model=ItemTipoResponse)
async def actualizar_item(
    id: str,
    datos: ItemTipoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos para actualizar")
    item = ItemTipoService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
    if not item:
        raise HTTPException(404, "Item no encontrado")
    return ItemTipoResponse.model_validate(item)


@router.delete("/items/{id}")
async def eliminar_item(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    if not ItemTipoService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Item no encontrado")
    return {"message": "Item eliminado"}


@router.post("/items/{id}/ajustar-stock", response_model=ItemTipoResponse)
async def ajustar_stock(
    id: str,
    datos: AjusteStockCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_items,
):
    try:
        item = ItemTipoService.ajustar_stock(db, empresa_id, id, datos.cantidad, usuario=current_user.email)
        if not item:
            raise HTTPException(404, "Item no encontrado")
        return ItemTipoResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(400, str(e))


# === ENTREGAS ===
@router.get("/entregas", response_model=EntregaList)
async def listar_entregas(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    item_tipo_id: Optional[str] = None,
    empleado_id: Optional[str] = None,
    fecha_desde: Optional[datetime] = None,
    fecha_hasta: Optional[datetime] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_entregas,
):
    filtros = {}
    if item_tipo_id:
        filtros["item_tipo_id"] = item_tipo_id
    if empleado_id:
        filtros["empleado_id"] = empleado_id
    if fecha_desde:
        filtros["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filtros["fecha_hasta"] = fecha_hasta

    resultado = EntregaService.listar(db, empresa_id, pagina, por_pagina, filtros)

    items_response = []
    for entrega in resultado["items"]:
        entrega_dict = {
            "id": str(entrega.id),
            "item_tipo_id": str(entrega.item_tipo_id),
            "empleado_id": str(entrega.empleado_id),
            "hrbp_usuario_id": str(entrega.hrbp_usuario_id),
            "cantidad": entrega.cantidad,
            "observaciones": entrega.observaciones,
            "fecha_entrega": entrega.fecha_entrega,
            "created_at": entrega.created_at,
            "updated_at": entrega.updated_at,
        }
        if entrega.item_tipo:
            entrega_dict["item_tipo"] = ItemTipoResponse.model_validate(entrega.item_tipo)
        if entrega.empleado:
            entrega_dict["empleado"] = EmpleadoSimple.model_validate(entrega.empleado)
        if entrega.hrbp_usuario:
            entrega_dict["hrbp_usuario"] = UsuarioSimple.model_validate(entrega.hrbp_usuario)
        items_response.append(EntregaResponse(**entrega_dict))

    return EntregaList(
        items=items_response,
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@router.get("/entregas/{id}", response_model=EntregaResponse)
async def obtener_entrega(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_entregas,
):
    entrega = EntregaService.obtener(db, empresa_id, id)
    if not entrega:
        raise HTTPException(404, "Entrega no encontrada")

    entrega_dict = {
        "id": str(entrega.id),
        "item_tipo_id": str(entrega.item_tipo_id),
        "empleado_id": str(entrega.empleado_id),
        "hrbp_usuario_id": str(entrega.hrbp_usuario_id),
        "cantidad": entrega.cantidad,
        "observaciones": entrega.observaciones,
        "fecha_entrega": entrega.fecha_entrega,
        "created_at": entrega.created_at,
        "updated_at": entrega.updated_at,
    }
    if entrega.item_tipo:
        entrega_dict["item_tipo"] = ItemTipoResponse.model_validate(entrega.item_tipo)
    if entrega.empleado:
        entrega_dict["empleado"] = EmpleadoSimple.model_validate(entrega.empleado)
    if entrega.hrbp_usuario:
        entrega_dict["hrbp_usuario"] = UsuarioSimple.model_validate(entrega.hrbp_usuario)

    return EntregaResponse(**entrega_dict)


@router.post("/entregas", response_model=EntregaResponse, status_code=201)
async def crear_entrega(
    datos: EntregaCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_entregas,
):
    try:
        entrega = EntregaService.crear(db, empresa_id, datos.model_dump(), hrbp_usuario_id=str(current_user.id))
        # Recargar con relaciones
        entrega = EntregaService.obtener(db, empresa_id, str(entrega.id))

        entrega_dict = {
            "id": str(entrega.id),
            "item_tipo_id": str(entrega.item_tipo_id),
            "empleado_id": str(entrega.empleado_id),
            "hrbp_usuario_id": str(entrega.hrbp_usuario_id),
            "cantidad": entrega.cantidad,
            "observaciones": entrega.observaciones,
            "fecha_entrega": entrega.fecha_entrega,
            "created_at": entrega.created_at,
            "updated_at": entrega.updated_at,
        }
        if entrega.item_tipo:
            entrega_dict["item_tipo"] = ItemTipoResponse.model_validate(entrega.item_tipo)
        if entrega.empleado:
            entrega_dict["empleado"] = EmpleadoSimple.model_validate(entrega.empleado)
        if entrega.hrbp_usuario:
            entrega_dict["hrbp_usuario"] = UsuarioSimple.model_validate(entrega.hrbp_usuario)

        return EntregaResponse(**entrega_dict)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/entregas/{id}")
async def eliminar_entrega(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_entregas,
):
    if not EntregaService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Entrega no encontrada")
    return {"message": "Entrega eliminada y stock devuelto"}
