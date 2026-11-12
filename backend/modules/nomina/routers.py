"""
Routers para el módulo de Nómina - Empleados, Departamentos y Perfiles.
"""

import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.dependencies import get_current_user, get_db, get_empresa_activa, get_empresa_cuit, require_submodulo
from backend.modules.nomina.schemas import (
    CarreraCreate,
    CarreraList,
    CarreraResponse,
    CarreraUpdate,
    CategoriaCreate,
    CategoriaList,
    CategoriaResponse,
    CategoriaUpdate,
    DepartamentoCreate,
    DepartamentoList,
    DepartamentoResponse,
    DepartamentoUpdate,
    EmpleadoBaja,
    EmpleadoCreate,
    EmpleadoList,
    EmpleadoMiPerfilUpdate,
    EmpleadoResponse,
    EmpleadoUpdate,
    PerfilCreate,
    PerfilList,
    PerfilResponse,
    PerfilUpdate,
)
from backend.modules.nomina.services import (
    CarreraService,
    CategoriaService,
    DepartamentoService,
    EmpleadoService,
    ManagerInvalido,
    PerfilService,
)
from backend.modules.usuarios import emails_corporativos
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/nomina", tags=["Nómina"])
public_router = APIRouter(prefix="/nomina", tags=["Nómina - Perfil"])

# Shortcuts de submódulo
require_empleados = Depends(require_submodulo("nomina", "empleados"))
require_departamentos = Depends(require_submodulo("nomina", "departamentos"))
require_perfiles = Depends(require_submodulo("nomina", "perfiles"))
require_categorias = Depends(require_submodulo("nomina", "categorias"))
require_carreras = Depends(require_submodulo("nomina", "carreras"))

# Configuración de fotos de empleados
FOTOS_DIR = Path("/data/nomina/fotos")
FOTOS_THUMB_DIR = Path("/data/nomina/fotos/thumbnails")
FOTOS_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}
FOTOS_MAX_SIZE = 5 * 1024 * 1024  # 5MB
THUMB_SIZE = (110, 110)


# ============ DEPARTAMENTOS ============
@router.get("/departamentos", response_model=DepartamentoList)
async def listar_departamentos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(100, ge=1, le=100),
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_departamentos,
):
    filtros = {"buscar": buscar} if buscar else {}
    resultado = DepartamentoService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return DepartamentoList(
        items=[DepartamentoResponse.from_model(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/departamentos/todos", response_model=List[DepartamentoResponse])
async def listar_todos_departamentos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_departamentos,
):
    """Lista todos los departamentos para selects."""
    items = DepartamentoService.listar_todos(db, empresa_id)
    return [DepartamentoResponse.from_model(i) for i in items]


@router.get("/departamentos/{id}", response_model=DepartamentoResponse)
async def obtener_departamento(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_departamentos,
):
    entidad = DepartamentoService.obtener(db, empresa_id, id)
    if not entidad:
        raise HTTPException(404, "Departamento no encontrado")
    return DepartamentoResponse.from_model(entidad)


@router.post("/departamentos", response_model=DepartamentoResponse, status_code=201)
async def crear_departamento(
    datos: DepartamentoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_departamentos,
):
    try:
        depto = DepartamentoService.crear(db, empresa_id, datos.model_dump(), current_user.email)
    except ManagerInvalido as e:
        raise HTTPException(422, str(e))
    return DepartamentoResponse.from_model(depto)


@router.put("/departamentos/{id}", response_model=DepartamentoResponse)
async def actualizar_departamento(
    id: str,
    datos: DepartamentoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_departamentos,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos")
    try:
        entidad = DepartamentoService.actualizar(db, empresa_id, id, datos_dict, current_user.email)
    except ManagerInvalido as e:
        raise HTTPException(422, str(e))
    if not entidad:
        raise HTTPException(404, "Departamento no encontrado")
    return DepartamentoResponse.from_model(entidad)


@router.delete("/departamentos/{id}")
async def eliminar_departamento(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_departamentos,
):
    if not DepartamentoService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Departamento no encontrado")
    return {"message": "Departamento eliminado"}


# ============ PERFILES ============
@router.get("/perfiles", response_model=PerfilList)
async def listar_perfiles(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(100, ge=1, le=100),
    buscar: Optional[str] = None,
    categoria_id: Optional[str] = None,
    departamento_id: Optional[str] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_perfiles,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if categoria_id:
        filtros["categoria_id"] = categoria_id
    if departamento_id:
        filtros["departamento_id"] = departamento_id
    if tipo:
        filtros["tipo"] = tipo
    resultado = PerfilService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return PerfilList(
        items=[PerfilResponse.from_model(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/perfiles/todos", response_model=List[PerfilResponse])
async def listar_todos_perfiles(
    categoria_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_perfiles,
):
    """Lista todos los perfiles para selects, opcionalmente filtrados por categoría."""
    items = PerfilService.listar_todos(db, empresa_id, categoria_id=categoria_id)
    return [PerfilResponse.from_model(i) for i in items]


@router.get("/perfiles/{id}", response_model=PerfilResponse)
async def obtener_perfil(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_perfiles,
):
    entidad = PerfilService.obtener(db, empresa_id, id)
    if not entidad:
        raise HTTPException(404, "Perfil no encontrado")
    return PerfilResponse.from_model(entidad)


@router.post("/perfiles", response_model=PerfilResponse, status_code=201)
async def crear_perfil(
    datos: PerfilCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_perfiles,
):
    try:
        return PerfilResponse.from_model(PerfilService.crear(db, empresa_id, datos.model_dump(), current_user.email))
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/perfiles/{id}", response_model=PerfilResponse)
async def actualizar_perfil(
    id: str,
    datos: PerfilUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_perfiles,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos")
    entidad = PerfilService.actualizar(db, empresa_id, id, datos_dict, current_user.email)
    if not entidad:
        raise HTTPException(404, "Perfil no encontrado")
    return PerfilResponse.from_model(entidad)


@router.delete("/perfiles/{id}")
async def eliminar_perfil(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_perfiles,
):
    if not PerfilService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Perfil no encontrado")
    return {"message": "Perfil eliminado"}


# ============ CATEGORIAS ============
@router.get("/categorias", response_model=CategoriaList)
async def listar_categorias(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(100, ge=1, le=100),
    buscar: Optional[str] = None,
    departamento_id: Optional[str] = None,
    ordenar_por: Optional[str] = None,
    ordenar_dir: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_categorias,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if departamento_id:
        filtros["departamento_id"] = departamento_id
    if ordenar_por:
        filtros["ordenar_por"] = ordenar_por
    if ordenar_dir:
        filtros["ordenar_dir"] = ordenar_dir
    resultado = CategoriaService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return CategoriaList(
        items=[CategoriaResponse.from_model(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/categorias/todos", response_model=List[CategoriaResponse])
async def listar_todas_categorias(
    departamento_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_categorias,
):
    """Lista todas las categorías para selects, opcionalmente filtradas por departamento."""
    items = CategoriaService.listar_todos(db, empresa_id, departamento_id=departamento_id)
    return [CategoriaResponse.from_model(i) for i in items]


@router.get("/categorias/{id}", response_model=CategoriaResponse)
async def obtener_categoria(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_categorias,
):
    entidad = CategoriaService.obtener(db, empresa_id, id)
    if not entidad:
        raise HTTPException(404, "Categoría no encontrada")
    return CategoriaResponse.from_model(entidad)


@router.post("/categorias", response_model=CategoriaResponse, status_code=201)
async def crear_categoria(
    datos: CategoriaCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_categorias,
):
    try:
        return CategoriaResponse.from_model(
            CategoriaService.crear(db, empresa_id, datos.model_dump(), current_user.email)
        )
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/categorias/{id}", response_model=CategoriaResponse)
async def actualizar_categoria(
    id: str,
    datos: CategoriaUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_categorias,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos")
    entidad = CategoriaService.actualizar(db, empresa_id, id, datos_dict, current_user.email)
    if not entidad:
        raise HTTPException(404, "Categoría no encontrada")
    return CategoriaResponse.from_model(entidad)


@router.delete("/categorias/{id}")
async def eliminar_categoria(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_categorias,
):
    if not CategoriaService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Categoría no encontrada")
    return {"message": "Categoría eliminada"}


# ============ CARRERAS ============
@router.get("/carreras", response_model=CarreraList)
async def listar_carreras(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(100, ge=1, le=100),
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_carreras,
):
    filtros = {"buscar": buscar} if buscar else {}
    resultado = CarreraService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return CarreraList(
        items=[CarreraResponse.model_validate(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@public_router.get("/carreras/todos", response_model=List[CarreraResponse])
async def listar_todas_carreras(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    # Usa get_current_user (sin require_submodulo) a propósito: el dropdown
    # de carreras se usa en "Mi Perfil" y necesita ser accesible para
    # cualquier usuario logueado, sin permiso de nómina.
    current_user: Usuario = Depends(get_current_user),
):
    """Lista todas las carreras para selects (accesible desde perfil, sin permiso de nómina)."""
    items = CarreraService.listar_todos(db, empresa_id)
    return [CarreraResponse.model_validate(i) for i in items]


@router.get("/carreras/{id}", response_model=CarreraResponse)
async def obtener_carrera(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_carreras,
):
    entidad = CarreraService.obtener(db, empresa_id, id)
    if not entidad:
        raise HTTPException(404, "Carrera no encontrada")
    return CarreraResponse.model_validate(entidad)


@router.post("/carreras", response_model=CarreraResponse, status_code=201)
async def crear_carrera(
    datos: CarreraCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_carreras,
):
    try:
        return CarreraResponse.model_validate(
            CarreraService.crear(db, empresa_id, datos.model_dump(), current_user.email)
        )
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/carreras/{id}", response_model=CarreraResponse)
async def actualizar_carrera(
    id: str,
    datos: CarreraUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_carreras,
):
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(400, "No hay datos")
    entidad = CarreraService.actualizar(db, empresa_id, id, datos_dict, current_user.email)
    if not entidad:
        raise HTTPException(404, "Carrera no encontrada")
    return CarreraResponse.model_validate(entidad)


@router.delete("/carreras/{id}")
async def eliminar_carrera(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_carreras,
):
    if not CarreraService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Carrera no encontrada")
    return {"message": "Carrera eliminada"}


# ============ EMPLEADOS ============


@router.get("/empleados/buscar-select")
async def buscar_empleados_select(
    q: Optional[str] = None,
    seniority: Optional[str] = None,
    perfil_tipo: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_empleados,
):
    empleados = EmpleadoService.listar_para_select(db, empresa_id, q, seniority=seniority, perfil_tipo=perfil_tipo)
    return [{"id": str(e.id), "nombre": e.empleado_nombre_completo, "codigo": e.codigo} for e in empleados]


@router.get("/empleados/buscar-hrbp")
async def buscar_hrbps_select(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_empleados,
):
    empleados = EmpleadoService.listar_hrbps(db, empresa_id, q)
    return [{"id": str(e.id), "nombre": e.empleado_nombre_completo, "codigo": e.codigo} for e in empleados]


@router.get("/empleados", response_model=EmpleadoList)
async def listar_empleados(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=100),
    buscar: Optional[str] = None,
    departamento_id: Optional[str] = None,
    perfil_id: Optional[str] = None,
    activo: Optional[str] = None,
    seniority: Optional[str] = None,
    antiguedad_rango: Optional[str] = None,
    agrupar_por: Optional[str] = None,
    ordenar_por: Optional[str] = None,
    ordenar_dir: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_empleados,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if departamento_id:
        filtros["departamento_id"] = departamento_id
    if perfil_id:
        filtros["perfil_id"] = perfil_id
    if activo is not None and activo != "":
        filtros["activo"] = activo.lower() == "true"
    if seniority:
        filtros["seniority"] = seniority
    if antiguedad_rango:
        filtros["antiguedad_rango"] = antiguedad_rango
    if agrupar_por:
        filtros["agrupar_por"] = agrupar_por
    if ordenar_por:
        filtros["ordenar_por"] = ordenar_por
    if ordenar_dir:
        filtros["ordenar_dir"] = ordenar_dir
    resultado = EmpleadoService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return EmpleadoList(
        items=[EmpleadoResponse.from_model(emp) for emp in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
        grupos=resultado.get("grupos", []),
    )


@public_router.get("/empleados/por-dni/{dni}", response_model=EmpleadoResponse)
async def obtener_empleado_por_dni(
    dni: int,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    # Usa get_current_user (sin require_submodulo) a propósito: el empleado
    # necesita consultar su propio registro desde "Mi Perfil" sin tener
    # permiso de nómina. La restricción es por DNI propio (línea siguiente).
    current_user: Usuario = Depends(get_current_user),
):
    """Obtiene un empleado por DNI. Solo permite consultar el propio DNI."""
    if current_user.dni != dni:
        raise HTTPException(status_code=403, detail="Solo podés consultar tu propio registro")
    empleado = EmpleadoService.obtener_por_dni(db, empresa_id, dni)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return EmpleadoResponse.from_model(empleado)


@public_router.put("/empleados/{id}/mi-perfil", response_model=EmpleadoResponse)
async def actualizar_mi_perfil_empleado(
    id: str,
    datos: EmpleadoMiPerfilUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    # Usa get_current_user (sin require_submodulo) a propósito: cualquier
    # usuario logueado puede editar su propio perfil de empleado sin necesitar
    # permiso de nómina. La restricción es por DNI propio (se valida abajo).
    current_user: Usuario = Depends(get_current_user),
):
    empleado = EmpleadoService.obtener(db, empresa_id, id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if empleado.dni != current_user.dni:
        raise HTTPException(status_code=403, detail="Solo podés editar tu propio registro")
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")
    # El email personal es de la ficha: no cambia el email de la cuenta, que lo cambia un admin en Usuarios (F22)
    try:
        empleado = EmpleadoService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        return EmpleadoResponse.from_model(empleado)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error inesperado en mi-perfil: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar perfil")


@router.get("/empleados/{id}", response_model=EmpleadoResponse)
async def obtener_empleado(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_empleados,
):
    """Obtiene un empleado por ID, con el email secundario de su cuenta (F22)."""
    empleado = EmpleadoService.obtener(db, empresa_id, id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    respuesta = EmpleadoResponse.from_model(empleado)
    cuenta = emails_corporativos.cuenta_de_dni(db, empleado.dni)
    respuesta.email_secundario = cuenta.email_secundario if cuenta else None
    return respuesta


@router.post("/empleados", response_model=EmpleadoResponse, status_code=201)
async def crear_empleado(
    datos: EmpleadoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Crea un nuevo empleado."""
    try:
        empleado = EmpleadoService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return EmpleadoResponse.from_model(empleado)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error inesperado al crear empleado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear empleado")


@router.put("/empleados/{id}", response_model=EmpleadoResponse)
async def actualizar_empleado(
    id: str,
    datos: EmpleadoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Actualiza un empleado."""
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")
    try:
        empleado = EmpleadoService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        return EmpleadoResponse.from_model(empleado)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error inesperado al actualizar empleado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar empleado")


@router.delete("/empleados/{id}")
async def eliminar_empleado(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Elimina un empleado (soft delete real - solo para casos extremos)."""
    if not EmpleadoService.eliminar(db, empresa_id, id):
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return {"message": "Empleado eliminado correctamente"}


@router.put("/empleados/{id}/baja", response_model=EmpleadoResponse)
async def dar_baja_empleado(
    id: str,
    datos: EmpleadoBaja,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Da de baja a un empleado con fecha y motivo."""
    empleado = EmpleadoService.dar_de_baja(
        db, empresa_id, id, datos.fecha_baja, datos.motivo_baja, usuario=current_user.email
    )
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado o ya está dado de baja")
    return EmpleadoResponse.from_model(empleado)


@router.put("/empleados/{id}/reactivar", response_model=EmpleadoResponse)
async def reactivar_empleado(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Reactiva un empleado dado de baja."""
    empleado = EmpleadoService.reactivar(db, empresa_id, id, usuario=current_user.email)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado o ya está activo")
    return EmpleadoResponse.from_model(empleado)


@router.put("/empleados/{id}/restaurar", response_model=EmpleadoResponse)
async def restaurar_empleado(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Restaura un empleado eliminado."""
    empleado = EmpleadoService.restaurar(db, empresa_id, id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado o no está eliminado")
    return EmpleadoResponse.from_model(empleado)


@router.post("/empleados/{id}/foto", response_model=EmpleadoResponse)
async def subir_foto_empleado(
    id: str,
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user: Usuario = require_empleados,
):
    """Sube o reemplaza la foto de un empleado."""
    from backend.core.storage import cloud_storage

    empleado = EmpleadoService.obtener(db, empresa_id, id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    ext = Path(foto.filename).suffix.lower()
    if ext not in FOTOS_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Formato no permitido. Use: {', '.join(FOTOS_ALLOWED_EXT)}")
    content = await foto.read()
    if len(content) > FOTOS_MAX_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 5MB")

    # Eliminar foto anterior del storage si existe
    if empleado.foto:
        cloud_storage.delete_image(empleado.foto)

    # Subir foto con thumbnail al storage
    folder = f"nomina-{empresa_cuit}"
    key = cloud_storage.build_key(folder, content, ext=ext)
    result = cloud_storage.upload_image(key, content, f"image/{ext.lstrip('.')}", thumbnail_size=THUMB_SIZE)

    foto_url = result["key"]
    empleado_actualizado = EmpleadoService.actualizar(
        db, empresa_id, id, {"foto": foto_url}, usuario=current_user.email
    )
    return EmpleadoResponse.from_model(empleado_actualizado)


@router.delete("/empleados/{id}/foto", response_model=EmpleadoResponse)
async def eliminar_foto_empleado(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_empleados,
):
    """Elimina la foto de un empleado."""
    empleado = EmpleadoService.obtener(db, empresa_id, id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    if empleado.foto:
        old_filename = empleado.foto.split("/")[-1]
        old_path = FOTOS_DIR / old_filename
        old_thumb = FOTOS_THUMB_DIR / old_filename
        if old_path.exists():
            old_path.unlink()
        if old_thumb.exists():
            old_thumb.unlink()
    empleado_actualizado = EmpleadoService.actualizar(db, empresa_id, id, {"foto": None}, usuario=current_user.email)
    return EmpleadoResponse.from_model(empleado_actualizado)
