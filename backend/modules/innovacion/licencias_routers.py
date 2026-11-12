"""
Routers para el módulo de Innovación - Gestión de Licencias.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.dependencies import get_db, get_empresa_activa, require_submodulo
from backend.modules.innovacion.licencias_schemas import (
    EmpleadoLicencias,
    EmpleadoLicenciasList,
    EmpleadoOpcion,
    EquipoLicencias,
    EquipoLicenciasList,
    EquipoOpcion,
    HerramientaCreate,
    HerramientaResponse,
    HerramientaUpdate,
    LicenciaCreate,
    LicenciaResponse,
    LicenciasLoteCreate,
    LicenciasLoteResponse,
    LicenciasMultipleCreate,
    LicenciaUpdate,
    MetricasGasto,
    ProveedorCreate,
    ProveedorResponse,
    RevocacionLicencias,
    RevocacionSeleccion,
)
from backend.modules.innovacion.licencias_services import (
    HerramientaService,
    LicenciaService,
    ProveedorService,
    ReferenciaInvalida,
)
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/innovacion", tags=["Innovación - Licencias"])
logger = logging.getLogger(__name__)

require_licencias = Depends(require_submodulo("innovacion", "licencias"))


# ============ CATÁLOGO DE HERRAMIENTAS ============


@router.get("/herramientas", response_model=List[HerramientaResponse])
async def listar_herramientas(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_licencias
):
    """Lista el catálogo de herramientas para selects y filtros."""
    herramientas = HerramientaService.listar(db, empresa_id)
    return [HerramientaResponse.from_model(h) for h in herramientas]


@router.get("/proveedores", response_model=List[ProveedorResponse])
async def listar_proveedores(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_licencias
):
    """Lista el catálogo de proveedores para selects y filtros."""
    return [ProveedorResponse.from_model(p) for p in ProveedorService.listar(db, empresa_id)]


@router.post("/proveedores", response_model=ProveedorResponse, status_code=201)
async def crear_proveedor(
    datos: ProveedorCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Crea un proveedor. Si el nombre plegado ya existe, devuelve el existente."""
    try:
        proveedor = ProveedorService.obtener_o_crear(db, empresa_id, datos.nombre, usuario=current_user.email)
        if proveedor is None:
            raise HTTPException(status_code=422, detail="El nombre es obligatorio")
        db.commit()
        return ProveedorResponse.from_model(proveedor)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear proveedor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear el proveedor")


@router.post("/herramientas", response_model=HerramientaResponse, status_code=201)
async def crear_herramienta(
    datos: HerramientaCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Crea una herramienta. Rechaza duplicados por nombre plegado."""
    try:
        herramienta = HerramientaService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return HerramientaResponse.from_model(herramienta)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al crear herramienta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear la herramienta")


@router.get("/licencias/equipos", response_model=List[EquipoOpcion])
async def listar_equipos(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_licencias
):
    """Equipos de la empresa para el filtro. El endpoint de operaciones exige
    otro modulo, asi que licencias expone su propia lista minima."""
    return [EquipoOpcion(**equipo) for equipo in LicenciaService.listar_equipos(db, empresa_id)]


@router.get("/licencias/empleados", response_model=List[EmpleadoOpcion])
async def listar_empleados(
    db: Session = Depends(get_db), empresa_id: uuid.UUID = Depends(get_empresa_activa), current_user=require_licencias
):
    """Opciones de empleados disponibles con el permiso propio de licencias."""
    return [EmpleadoOpcion.from_fila(empleado) for empleado in LicenciaService.listar_empleados(db, empresa_id)]


@router.put("/proveedores/{id}", response_model=ProveedorResponse)
async def actualizar_proveedor(
    id: str,
    datos: ProveedorCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Corrige el nombre sin cambiar las referencias de las herramientas."""
    try:
        proveedor = ProveedorService.actualizar(db, empresa_id, id, datos.nombre, usuario=current_user.email)
        return ProveedorResponse.from_model(proveedor)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar proveedor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar el proveedor")


@router.delete("/proveedores/{id}", status_code=204)
async def eliminar_proveedor(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Baja lógica en cascada del proveedor, sus herramientas y sus licencias."""
    try:
        ProveedorService.eliminar(db, empresa_id, id, usuario=current_user.email)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar proveedor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al eliminar el proveedor")


@router.put("/herramientas/{id}", response_model=HerramientaResponse)
async def actualizar_herramienta(
    id: str,
    datos: HerramientaUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Corrige nombre, proveedor o costo. Es como se arregla un typo."""
    try:
        herramienta = HerramientaService.actualizar(
            db, empresa_id, id, datos.model_dump(exclude_unset=True), usuario=current_user.email
        )
        return HerramientaResponse.from_model(herramienta)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar herramienta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar la herramienta")


@router.delete("/herramientas/{id}", status_code=204)
async def eliminar_herramienta(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Baja lógica en cascada de la herramienta y sus licencias."""
    try:
        HerramientaService.eliminar(db, empresa_id, id, usuario=current_user.email)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar herramienta: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al eliminar la herramienta")


# ============ LICENCIAS ============


@router.get("/licencias/por-empleado", response_model=EmpleadoLicenciasList)
async def listar_licencias_por_empleado(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
    buscar: Optional[str] = None,
    empleado_ids: Optional[List[str]] = Query(None, alias="empleado_id"),
    equipo_ids: Optional[List[str]] = Query(None, alias="equipo_id"),
    proveedor_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_licencias,
):
    """Una fila por empleado con sus licencias. Es la vista del listado."""
    filtros = {
        "buscar": buscar,
        "empleado_ids": empleado_ids,
        "equipo_ids": equipo_ids,
        "proveedor_id": proveedor_id,
    }
    filtros = {k: v for k, v in filtros.items() if v}
    resultado = LicenciaService.listar_por_empleado(db, empresa_id, pagina, por_pagina, filtros)
    metricas = LicenciaService.metricas_gasto(db, empresa_id, filtros)

    return EmpleadoLicenciasList(
        items=[EmpleadoLicencias.from_grupo(grupo) for grupo in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
        metricas=MetricasGasto(**metricas),
    )


@router.get("/licencias/por-equipo", response_model=EquipoLicenciasList)
async def listar_licencias_por_equipo(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
    buscar: Optional[str] = None,
    empleado_ids: Optional[List[str]] = Query(None, alias="empleado_id"),
    equipo_ids: Optional[List[str]] = Query(None, alias="equipo_id"),
    proveedor_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_licencias,
):
    """Equipo, empleados y licencias; pagina equipos sin cortar sus integrantes."""
    filtros = {
        k: v
        for k, v in {
            "buscar": buscar,
            "empleado_ids": empleado_ids,
            "equipo_ids": equipo_ids,
            "proveedor_id": proveedor_id,
        }.items()
        if v
    }
    resultado = LicenciaService.listar_por_equipo(db, empresa_id, pagina, por_pagina, filtros)
    return EquipoLicenciasList(
        **{k: v for k, v in resultado.items() if k != "items"},
        items=[EquipoLicencias.from_grupo(grupo) for grupo in resultado["items"]],
        metricas=MetricasGasto(**LicenciaService.metricas_gasto(db, empresa_id, filtros)),
    )


@router.get("/licencias/{id}", response_model=LicenciaResponse)
async def obtener_licencia(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_licencias,
):
    """Obtiene una licencia por ID."""
    licencia = LicenciaService.obtener(db, empresa_id, id)
    if not licencia:
        raise HTTPException(status_code=404, detail="Licencia no encontrada")
    return LicenciaResponse.from_model(licencia)


@router.post("/licencias/lote", response_model=LicenciasLoteResponse, status_code=201)
async def crear_licencias_lote(
    datos: LicenciasLoteCreate | LicenciasMultipleCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Asigna las mismas condiciones a los empleados elegidos, de forma atomica."""
    try:
        creadas = LicenciaService.crear_lote(
            db,
            empresa_id,
            datos.model_dump(),
            usuario=current_user.email,
        )
        return LicenciasLoteResponse(creadas=creadas)
    except ReferenciaInvalida as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except Exception as error:
        logger.error(f"Error al crear licencias por lote: {error}", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo completar la asignacion de licencias")


@router.post("/licencias", response_model=LicenciaResponse, status_code=201)
async def crear_licencia(
    datos: LicenciaCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Crea una nueva licencia."""
    try:
        licencia = LicenciaService.crear(db, empresa_id, datos.model_dump(), usuario=current_user.email)
        return LicenciaResponse.from_model(licencia)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al crear licencia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear la licencia")


@router.put("/licencias/{id}", response_model=LicenciaResponse)
async def actualizar_licencia(
    id: str,
    datos: LicenciaUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Actualiza una licencia."""
    datos_dict = datos.model_dump(exclude_unset=True)
    if not datos_dict:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    try:
        licencia = LicenciaService.actualizar(db, empresa_id, id, datos_dict, usuario=current_user.email)
        if not licencia:
            raise HTTPException(status_code=404, detail="Licencia no encontrada")
        return LicenciaResponse.from_model(licencia)
    except ReferenciaInvalida as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar licencia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar la licencia")


@router.post("/licencias/revocacion/preview")
async def preparar_revocacion(
    datos: RevocacionSeleccion,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    licencias = LicenciaService.preparar_revocacion(db, empresa_id, datos.model_dump())
    return {
        "licencia_ids": [str(lic.id) for lic in licencias],
        "empleados": len({lic.empleado_id for lic in licencias}),
    }


@router.delete("/licencias/revocacion")
async def revocar_licencias(
    datos: RevocacionLicencias,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    return {"revocadas": LicenciaService.revocar_lote(db, empresa_id, datos.licencia_ids, current_user.email)}


@router.delete("/licencias/{id}", status_code=204)
async def eliminar_licencia(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Baja lógica de la licencia, para sacar las que quedaron sucias."""
    if not LicenciaService.eliminar(db, empresa_id, id, usuario=current_user.email):
        raise HTTPException(status_code=404, detail="Licencia no encontrada")


@router.put("/licencias/{id}/activa/{activa}", response_model=LicenciaResponse)
async def cambiar_activa_licencia(
    id: str,
    activa: bool,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_licencias,
):
    """Activa o desactiva una licencia."""
    try:
        licencia = LicenciaService.cambiar_activa(db, empresa_id, id, activa, usuario=current_user.email)
        if not licencia:
            raise HTTPException(status_code=404, detail="Licencia no encontrada")
        return LicenciaResponse.from_model(licencia)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al activar/desactivar licencia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al cambiar el estado")
