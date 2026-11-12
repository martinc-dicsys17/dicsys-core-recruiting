"""
Routers para el módulo de Empresa.

Endpoints CRUD de empresa, domicilios y asociación usuario-empresa.
Protegidos con require_admin.
"""

import hashlib
import logging
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_admin
from backend.modules.empresa.schemas import (
    EmpresaCreate,
    EmpresaDomicilioCreate,
    EmpresaDomicilioResponse,
    EmpresaList,
    EmpresaResponse,
    EmpresaUpdate,
    UsuarioEmpresaResponse,
)
from backend.modules.empresa.services import EmpresaService
from backend.modules.usuarios.models import Usuario

router = APIRouter(tags=["empresas"])
logger = logging.getLogger(__name__)

# Configuración de logos de empresa
LOGOS_DIR = Path("/data/files/empresas-logo")
LOGOS_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".svg"}
LOGOS_MAX_SIZE = 2 * 1024 * 1024  # 2MB
logger = logging.getLogger(__name__)


# ─── Empresas CRUD ────────────────────────────────────────────────────────────


@router.get("/empresas", response_model=EmpresaList)
async def listar_empresas(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    activo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if activo is not None:
        filtros["activo"] = activo

    resultado = EmpresaService.listar(db, pagina, por_pagina, filtros)
    return EmpresaList(
        items=[EmpresaResponse.model_validate(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/empresas/{id}", response_model=EmpresaResponse)
async def obtener_empresa(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    empresa = EmpresaService.obtener(db, id)
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")
    return EmpresaResponse.model_validate(empresa)


@router.post("/empresas", response_model=EmpresaResponse, status_code=201)
async def crear_empresa(
    datos: EmpresaCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    try:
        empresa = EmpresaService.crear(db, datos.model_dump(), usuario=current_user.email)
        return EmpresaResponse.model_validate(empresa)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al crear empresa: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear la empresa")


@router.put("/empresas/{id}", response_model=EmpresaResponse)
async def actualizar_empresa(
    id: str,
    datos: EmpresaUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    d = datos.model_dump(exclude_unset=True)
    if not d:
        raise HTTPException(400, "No hay datos para actualizar")
    try:
        empresa = EmpresaService.actualizar(db, id, d, usuario=current_user.email)
        if not empresa:
            raise HTTPException(404, "Empresa no encontrada")
        return EmpresaResponse.model_validate(empresa)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al actualizar empresa: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar la empresa")


@router.delete("/empresas/{id}")
async def eliminar_empresa(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    if not EmpresaService.eliminar(db, id):
        raise HTTPException(404, "Empresa no encontrada")
    return {"message": "Empresa eliminada"}


# ─── Domicilios ───────────────────────────────────────────────────────────────


@router.post("/empresas/{id}/domicilios", response_model=EmpresaDomicilioResponse, status_code=201)
async def agregar_domicilio(
    id: str,
    datos: EmpresaDomicilioCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    try:
        dom = EmpresaService.agregar_domicilio(db, id, datos.model_dump(), usuario=current_user.email)
        return EmpresaDomicilioResponse.model_validate(dom)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.error(f"Error al agregar domicilio: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al agregar el domicilio")


@router.delete("/empresas/{id}/domicilios/{dom_id}")
async def eliminar_domicilio(
    id: str,
    dom_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    if not EmpresaService.eliminar_domicilio(db, id, dom_id):
        raise HTTPException(404, "Domicilio no encontrado")
    return {"message": "Domicilio eliminado"}


# ─── Usuarios de Empresa ─────────────────────────────────────────────────────


@router.get("/empresas/{id}/usuarios", response_model=list[UsuarioEmpresaResponse])
async def listar_usuarios_empresa(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    # Verificar que la empresa existe
    empresa = EmpresaService.obtener(db, id)
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")
    usuarios = EmpresaService.listar_usuarios(db, id)
    return [UsuarioEmpresaResponse.model_validate(u) for u in usuarios]


@router.post("/empresas/{id}/usuarios", response_model=UsuarioEmpresaResponse, status_code=201)
async def agregar_usuario_empresa(
    id: str,
    usuario_id: str = Query(..., description="ID del usuario a asociar"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    try:
        EmpresaService.agregar_usuario(db, id, usuario_id)
        # Retornar la asociación recién creada
        usuarios = EmpresaService.listar_usuarios(db, id)
        asociacion = next((u for u in usuarios if u["usuario_id"] == usuario_id), None)
        if not asociacion:
            raise HTTPException(500, "Error inesperado al obtener la asociación")
        return UsuarioEmpresaResponse.model_validate(asociacion)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error(f"Error al agregar usuario a empresa: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al agregar el usuario")


@router.delete("/empresas/{id}/usuarios/{user_id}")
async def quitar_usuario_empresa(
    id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    if not EmpresaService.quitar_usuario(db, id, user_id):
        raise HTTPException(404, "Asociación usuario-empresa no encontrada")
    return {"message": "Usuario desasociado de la empresa"}


# ─── Empresas de un Usuario ──────────────────────────────────────────────────


@router.get("/usuarios/{id}/empresas", response_model=list[EmpresaResponse])
async def listar_empresas_usuario(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    empresas = EmpresaService.listar_empresas_usuario(db, id)
    return [EmpresaResponse.model_validate(e) for e in empresas]


# ─── Logo de Empresa ──────────────────────────────────────────────────────────


@router.post("/empresas/{id}/logo", response_model=EmpresaResponse)
async def subir_logo_empresa(
    id: str,
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Sube o reemplaza el logo de una empresa."""
    empresa = EmpresaService.obtener(db, id)
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")

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
    if empresa.logo:
        old_filename = empresa.logo.split("/")[-1]
        old_path = LOGOS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    file_path = LOGOS_DIR / filename
    with open(file_path, "wb") as f:
        f.write(content)

    logo_url = f"/files/empresas-logo/{filename}"
    actualizado = EmpresaService.actualizar(db, id, {"logo": logo_url}, usuario=current_user.email)
    return EmpresaResponse.model_validate(actualizado)


@router.delete("/empresas/{id}/logo", response_model=EmpresaResponse)
async def eliminar_logo_empresa(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Elimina el logo de una empresa."""
    empresa = EmpresaService.obtener(db, id)
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")

    if empresa.logo:
        old_filename = empresa.logo.split("/")[-1]
        old_path = LOGOS_DIR / old_filename
        if old_path.exists():
            old_path.unlink()

    actualizado = EmpresaService.actualizar(db, id, {"logo": None}, usuario=current_user.email)
    return EmpresaResponse.model_validate(actualizado)
