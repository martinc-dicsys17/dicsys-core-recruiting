"""
Routers de la evaluación de proveedores (Administración → Proveedores).

- Evaluación de Proveedores (admin_contable.evaluacion_proveedores): tablero y
  respuestas. Quien además tiene evaluacion_config ve todo (D-76).
- Configuración (admin_contable.evaluacion_config): campañas,
  configuración, importación del Sheet, seguimiento y avisos.
"""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.dependencies import get_db, get_empresa_activa, require_submodulo
from backend.modules.administracion import (
    evaluacion_proveedores_avisos as avisos,
    evaluacion_proveedores_importacion as importacion,
)
from backend.modules.administracion.evaluacion_proveedores_schemas import (
    AutogeneracionDatos,
    AutogeneracionResponse,
    AvisoLog,
    AvisoSolicitud,
    ConfiguracionDatos,
    ConfiguracionResponse,
    ConfirmacionImportacion,
    EvaluacionCreate,
    EvaluacionFechas,
    EvaluacionResponse,
    ItemDetalle,
    PruebaCanales,
    RespuestaEvaluacion,
    ResultadoAviso,
    ResultadoImportacion,
    Seguimiento,
    Tablero,
    VistaPreviaImportacion,
)
from backend.modules.administracion.evaluacion_proveedores_services import (
    AsignacionService,
    AutogeneracionService,
    ConfiguracionService,
    EvaluacionCerrada,
    EvaluacionInvalida,
    EvaluacionService,
    NoEsEvaluador,
    PeriodoDuplicado,
    TableroService,
    empleado_del_usuario,
)
from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_comun import ReferenciaInvalida
from backend.modules.administracion.proveedores_services import OperacionNoPermitida, ProveedorDuplicado
from backend.modules.permisos.services import GrupoService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/evaluaciones-proveedores", tags=["Administración - Evaluación de proveedores"])
logger = logging.getLogger(__name__)

CLAVE_ADMIN = "admin_contable.evaluacion_config"
require_evaluacion = Depends(require_submodulo("admin_contable", "evaluacion_proveedores"))
require_config = Depends(require_submodulo("admin_contable", "evaluacion_config"))


def _error(exc: Exception, accion: str):
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ReferenciaInvalida):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NoEsEvaluador):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (EvaluacionCerrada, PeriodoDuplicado, OperacionNoPermitida, ProveedorDuplicado)):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (EvaluacionInvalida, importacion.ErrorImportacion, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc))
    logger.error(f"Error al {accion}: {exc}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error inesperado al {accion}")


def es_admin_evaluacion(db: Session, usuario: Usuario, empresa_id: uuid.UUID) -> bool:
    if usuario.rol == "admin":
        return True
    permisos = GrupoService.obtener_permisos_usuario(db, str(usuario.id), empresa_id)
    return bool(permisos.get("admin_contable") and permisos.get(CLAVE_ADMIN))


# ─── Evaluación de Proveedores (tablero) ────────────────────────────────────────


@router.get("/tablero", response_model=Tablero)
async def obtener_tablero(
    evaluacion_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_evaluacion,
):
    """Métricas, ítems y opciones de la evaluación vigente (o de una anterior, solo admin)."""
    try:
        return TableroService.armar(
            db, empresa_id, current_user, es_admin_evaluacion(db, current_user, empresa_id), evaluacion_id
        )
    except Exception as exc:
        _error(exc, "cargar el tablero")


@router.get("/items/{item_id}", response_model=ItemDetalle)
async def obtener_item(
    item_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_evaluacion,
):
    """La evaluación completa de un proveedor: para el admin o el referente asignado."""
    try:
        return TableroService.detalle(
            db, empresa_id, item_id, current_user, es_admin_evaluacion(db, current_user, empresa_id)
        )
    except Exception as exc:
        _error(exc, "obtener la evaluación")


@router.put("/items/{item_id}")
async def responder_item(
    item_id: str,
    datos: RespuestaEvaluacion,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_evaluacion,
):
    """Guarda la evaluación (referente asignado o admin), dentro de la ventana de fechas."""
    try:
        item = TableroService.responder(
            db,
            empresa_id,
            item_id,
            datos.model_dump(),
            current_user,
            Actor.desde_request(request, current_user),
            es_admin=es_admin_evaluacion(db, current_user, empresa_id),
        )
        return {"id": str(item.id), "evaluado_at": item.evaluado_at, "con_hallazgo": bool(item.con_hallazgo)}
    except Exception as exc:
        db.rollback()
        _error(exc, "guardar la evaluación")


# ─── Agregar proveedores a la evaluación activa (desde el tablero) ──────────────


class AgregarProveedores(BaseModel):
    proveedor_ids: List[str] = Field(..., min_length=1, max_length=100)


class CandidatoEvaluacion(BaseModel):
    id: str
    nombre: str
    tipo: str
    activo: bool
    cuit: Optional[str] = None
    referente: Optional[str] = None
    en_evaluacion: bool = False


class Candidatos(BaseModel):
    total: int
    items: List[CandidatoEvaluacion]


def _item_agregado(item) -> dict:
    return {"id": str(item.id), "proveedor_id": str(item.proveedor_id)}


def _quien_agrega(db: Session, usuario: Usuario, empresa_id: uuid.UUID) -> dict:
    """El admin agrega cualquiera del registro; el evaluador, los que tiene asignados."""
    if es_admin_evaluacion(db, usuario, empresa_id):
        return {"es_admin": True}
    return {"es_admin": False, "empleado": empleado_del_usuario(db, empresa_id, usuario)}


@router.get("/candidatos", response_model=Candidatos)
async def listar_candidatos(
    buscar: str = Query(""),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_evaluacion,
):
    """Busca en el registro (el evaluador, entre los suyos); los que ya están vienen marcados."""
    try:
        return AsignacionService.candidatos(db, empresa_id, buscar, **_quien_agrega(db, current_user, empresa_id))
    except Exception as exc:
        _error(exc, "buscar proveedores")


@router.post("/items", status_code=201)
async def agregar_a_la_evaluacion(
    datos: AgregarProveedores,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_evaluacion,
):
    """
    Suma uno o varios proveedores a la evaluación activa, todos o ninguno: el admin, cualquiera
    (un inactivo no se agrega: primero se activa); el evaluador, los que tiene asignados como usuario referente.
    """
    try:
        items = AsignacionService.agregar(
            db,
            empresa_id,
            datos.proveedor_ids,
            Actor.desde_request(request, current_user),
            **_quien_agrega(db, current_user, empresa_id),
        )
        return {"agregados": [_item_agregado(item) for item in items]}
    except Exception as exc:
        db.rollback()
        _error(exc, "agregar el proveedor")


# ─── Configuración: fuente de datos, recordatorios y canales ────────────────────


@router.get("/configuracion", response_model=ConfiguracionResponse)
async def obtener_configuracion(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    return ConfiguracionService.como_dict(ConfiguracionService.obtener(db, empresa_id))


@router.put("/configuracion", response_model=ConfiguracionResponse)
async def guardar_configuracion(
    datos: ConfiguracionDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    try:
        configuracion = ConfiguracionService.guardar(
            db, empresa_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return ConfiguracionService.como_dict(configuracion)
    except Exception as exc:
        db.rollback()
        _error(exc, "guardar la configuración")


# ─── Configuración: auto-generación anual ───────────────────────────────────────


@router.get("/autogeneracion", response_model=AutogeneracionResponse)
async def obtener_autogeneracion(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    return AutogeneracionService.como_dict(db, empresa_id, ConfiguracionService.obtener(db, empresa_id))


@router.put("/autogeneracion", response_model=AutogeneracionResponse)
async def guardar_autogeneracion(
    datos: AutogeneracionDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Activa y configura la evaluación anual automática (arranca apagada)."""
    try:
        configuracion = AutogeneracionService.guardar(
            db, empresa_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return AutogeneracionService.como_dict(db, empresa_id, configuracion)
    except Exception as exc:
        db.rollback()
        _error(exc, "guardar la auto-generación")


# ─── Configuración: campañas ────────────────────────────────────────────────────


@router.get("/evaluaciones", response_model=List[EvaluacionResponse])
async def listar_evaluaciones(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    return [EvaluacionService.resumen(db, e) for e in EvaluacionService.listar(db, empresa_id)]


@router.post("/evaluaciones", response_model=EvaluacionResponse, status_code=201)
async def crear_evaluacion(
    datos: EvaluacionCreate,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Crea la campaña: reemplaza a la vigente y suma a todos los proveedores activos."""
    try:
        evaluacion = EvaluacionService.crear(
            db, empresa_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return EvaluacionService.resumen(db, evaluacion)
    except Exception as exc:
        db.rollback()
        _error(exc, "crear la evaluación")


@router.put("/evaluaciones/{evaluacion_id}", response_model=EvaluacionResponse)
async def cambiar_fechas_evaluacion(
    evaluacion_id: str,
    datos: EvaluacionFechas,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Cambia apertura y cierre de la vigente; ampliar el cierre la reabre."""
    try:
        evaluacion = EvaluacionService.cambiar_fechas(
            db, empresa_id, evaluacion_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return EvaluacionService.resumen(db, evaluacion)
    except Exception as exc:
        db.rollback()
        _error(exc, "cambiar las fechas")


@router.delete("/evaluaciones/{evaluacion_id}")
async def eliminar_evaluacion(
    evaluacion_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Baja lógica de la campaña y de sus ítems; la pantalla pide confirmación."""
    try:
        EvaluacionService.eliminar(db, empresa_id, evaluacion_id, Actor.desde_request(request, current_user))
        return {"message": "Eliminada"}
    except Exception as exc:
        db.rollback()
        _error(exc, "eliminar la evaluación")


# ─── Configuración: importación del Sheet ───────────────────────────────────────


@router.post("/importaciones", response_model=VistaPreviaImportacion, status_code=201)
async def generar_vista_previa(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Lee el Sheet y arma la vista previa (altas, sin cambios y cambios de referente)."""
    try:
        vista = importacion.generar_vista_previa(db, empresa_id, current_user.id)
        return importacion.resumen(db, vista)
    except Exception as exc:
        db.rollback()
        _error(exc, "importar el Sheet")


@router.get("/importaciones/{importacion_id}", response_model=VistaPreviaImportacion)
async def obtener_vista_previa(
    importacion_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    try:
        return importacion.resumen(db, importacion.obtener(db, empresa_id, importacion_id))
    except Exception as exc:
        _error(exc, "obtener la vista previa")


@router.post("/importaciones/{importacion_id}/confirmar", response_model=ResultadoImportacion)
async def confirmar_importacion(
    importacion_id: str,
    datos: ConfirmacionImportacion,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    try:
        return importacion.confirmar(
            db, empresa_id, importacion_id, datos.cambios_confirmados, Actor.desde_request(request, current_user)
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "confirmar la importación")


@router.delete("/importaciones/{importacion_id}")
async def cancelar_importacion(
    importacion_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    try:
        importacion.cancelar(db, empresa_id, importacion_id)
        return {"message": "Cancelada"}
    except Exception as exc:
        db.rollback()
        _error(exc, "cancelar la importación")


# ─── Configuración: seguimiento y avisos ────────────────────────────────────────


@router.get("/seguimiento", response_model=Seguimiento)
async def obtener_seguimiento(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    return avisos.seguimiento(db, empresa_id)


@router.post("/seguimiento/avisar", response_model=List[ResultadoAviso])
async def avisar_pendientes(
    datos: AvisoSolicitud,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Avisa a los evaluadores elegidos por los canales activos (el mensaje lo arma el servidor)."""
    try:
        return avisos.enviar(db, empresa_id, datos.evaluadores, "manual", Actor.desde_request(request, current_user))
    except Exception as exc:
        db.rollback()
        _error(exc, "enviar los avisos")


@router.post("/seguimiento/probar", response_model=List[ResultadoAviso])
async def probar_canales(
    datos: PruebaCanales,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    """Manda al evaluador elegido su aviso marcado [Prueba], por los canales como están en pantalla."""
    try:
        return avisos.probar(
            db, empresa_id, datos.evaluador_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "probar los canales")


@router.get("/avisos", response_model=List[AvisoLog])
async def historial_avisos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_config,
):
    return avisos.historial(db, empresa_id)
