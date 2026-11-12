"""
Routers para el módulo de Clientes.
"""

import hashlib
import logging
import uuid
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.administracion.clientes_schemas import (
    CategoriaClienteCreate,
    CategoriaClienteResponse,
    CategoriaClienteUpdate,
    ClienteCreate,
    ClienteDomicilioCreate,
    ClienteDomicilioResponse,
    ClienteList,
    ClienteResponse,
    ClienteUpdate,
)
from backend.modules.administracion.clientes_services import CategoriaClienteService, ClienteService

router = APIRouter(tags=["clientes"])
logger = logging.getLogger(__name__)

# Shortcut de submódulo
require_clientes = Depends(require_submodulo("admin_contable", "clientes"))

# Configuración de logos de clientes
LOGOS_DIR = Path("/data/files/clientes-logo")
LOGOS_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
LOGOS_MAX_SIZE = 2 * 1024 * 1024  # 2MB


# ─── Categorías ───────────────────────────────────────────────────────────────


@router.get("/clientes/categorias", response_model=list[CategoriaClienteResponse])
async def listar_categorias(
    solo_activas: bool = False,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    return [
        CategoriaClienteResponse.model_validate(c) for c in CategoriaClienteService.listar(db, empresa_id, solo_activas)
    ]


@router.post("/clientes/categorias", response_model=CategoriaClienteResponse, status_code=201)
async def crear_categoria(
    datos: CategoriaClienteCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    try:
        return CategoriaClienteResponse.model_validate(
            CategoriaClienteService.crear(db, empresa_id, datos.model_dump())
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al crear categoría: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear la categoría")


@router.put("/clientes/categorias/{id}", response_model=CategoriaClienteResponse)
async def actualizar_categoria(
    id: str,
    datos: CategoriaClienteUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    d = datos.model_dump(exclude_unset=True)
    if not d:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        cat = CategoriaClienteService.actualizar(db, empresa_id, id, d)
        if not cat:
            raise HTTPException(404, "Categoría no encontrada")
        return CategoriaClienteResponse.model_validate(cat)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al actualizar categoría: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar la categoría")


@router.delete("/clientes/categorias/{id}")
async def eliminar_categoria(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    if not CategoriaClienteService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Categoría no encontrada")
    return {"message": "Categoría eliminada"}


# ─── Clientes ─────────────────────────────────────────────────────────────────


@router.get("/clientes", response_model=ClienteList)
async def listar_clientes(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    tipo: Optional[str] = None,
    activo: Optional[bool] = None,
    categoria_id: Optional[str] = None,
    ordenar_por: Optional[str] = None,
    ordenar_dir: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if tipo:
        filtros["tipo"] = tipo
    if activo is not None:
        filtros["activo"] = activo
    if categoria_id:
        filtros["categoria_id"] = categoria_id
    if ordenar_por:
        filtros["ordenar_por"] = ordenar_por
    if ordenar_dir:
        filtros["ordenar_dir"] = ordenar_dir

    resultado = ClienteService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return ClienteList(
        items=[ClienteResponse.model_validate(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/clientes/{id}", response_model=ClienteResponse)
async def obtener_cliente(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    cliente = ClienteService.obtener(db, empresa_id, id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    return ClienteResponse.model_validate(cliente)


@router.post("/clientes", response_model=ClienteResponse, status_code=201)
async def crear_cliente(
    datos: ClienteCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    try:
        return ClienteResponse.model_validate(ClienteService.crear(db, empresa_id, datos.model_dump()))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al crear cliente: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el cliente")


@router.put("/clientes/{id}", response_model=ClienteResponse)
async def actualizar_cliente(
    id: str,
    datos: ClienteUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    d = datos.model_dump(exclude_unset=True)
    if not d:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        cliente = ClienteService.actualizar(db, empresa_id, id, d)
        if not cliente:
            raise HTTPException(404, "Cliente no encontrado")
        return ClienteResponse.model_validate(cliente)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al actualizar cliente: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar el cliente")


@router.delete("/clientes/{id}")
async def eliminar_cliente(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    if not ClienteService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Cliente no encontrado")
    return {"message": "Cliente eliminado"}


# ─── Domicilios ───────────────────────────────────────────────────────────────


@router.post("/clientes/{cliente_id}/domicilios", response_model=ClienteDomicilioResponse, status_code=201)
async def agregar_domicilio(
    cliente_id: str,
    datos: ClienteDomicilioCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    try:
        dom = ClienteService.agregar_domicilio(db, empresa_id, cliente_id, datos.model_dump())
        return ClienteDomicilioResponse.model_validate(dom)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"Error al agregar domicilio: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al agregar el domicilio")


@router.delete("/clientes/{cliente_id}/domicilios/{domicilio_id}")
async def eliminar_domicilio(
    cliente_id: str,
    domicilio_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    if not ClienteService.eliminar_domicilio(db, empresa_id, domicilio_id):
        raise HTTPException(404, "Domicilio no encontrado")
    return {"message": "Domicilio eliminado"}


# ─── Logo ─────────────────────────────────────────────────────────────────────


@router.post("/clientes/{id}/logo", response_model=ClienteResponse)
async def subir_logo_cliente(
    id: str,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    """Sube o reemplaza el logo de un cliente."""
    cliente = ClienteService.obtener(db, empresa_id, id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    ext = Path(logo.filename).suffix.lower()
    if ext not in LOGOS_ALLOWED_EXT:
        raise HTTPException(400, f"Formato no permitido. Use: {', '.join(LOGOS_ALLOWED_EXT)}")

    content = await logo.read()
    if len(content) > LOGOS_MAX_SIZE:
        raise HTTPException(400, "El archivo excede el tamaño máximo de 2MB")

    file_hash = hashlib.sha256(content).hexdigest()[:16]
    unique_id = uuid_lib.uuid4().hex[:8]
    filename = f"{file_hash}_{unique_id}{ext}"

    LOGOS_DIR.mkdir(parents=True, exist_ok=True)

    # Eliminar logo anterior si existe
    if cliente.logo:
        old_filename = cliente.logo.split("/")[-1]
        old_path = LOGOS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    file_path = LOGOS_DIR / filename
    with open(file_path, "wb") as f:
        f.write(content)

    logo_url = f"/files/clientes-logo/{filename}"
    actualizado = ClienteService.actualizar(db, empresa_id, id, {"logo": logo_url})
    return ClienteResponse.model_validate(actualizado)


@router.delete("/clientes/{id}/logo", response_model=ClienteResponse)
async def eliminar_logo_cliente(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_clientes,
):
    """Elimina el logo de un cliente."""
    cliente = ClienteService.obtener(db, empresa_id, id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    if cliente.logo:
        old_filename = cliente.logo.split("/")[-1]
        old_path = LOGOS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    actualizado = ClienteService.actualizar(db, empresa_id, id, {"logo": None})
    return ClienteResponse.model_validate(actualizado)
