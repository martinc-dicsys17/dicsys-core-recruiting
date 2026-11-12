"""
Routers para Star Miles.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.empresa.models import core_usuario_empresa
from backend.modules.nomina.services import EmpleadoService
from backend.modules.notificaciones_internas.services import NotificacionInternaService
from backend.modules.starmiles.models import Canje, ContenidoCMS, Desafio, InscripcionDesafio
from backend.modules.starmiles.schemas import (
    CalcularMillasRequest,
    CalcularMillasResponse,
    CanjeAprobar,
    CanjeCreate,
    CanjeEntregar,
    CanjeList,
    CanjeRechazar,
    CanjeRechazarYReintegrar,
    CanjeResponse,
    CategoriaDesafioCreate,
    CategoriaDesafioResponse,
    CategoriaDesafioUpdate,
    ContenidoCMSCreate,
    ContenidoCMSList,
    ContenidoCMSResponse,
    ContenidoCMSUpdate,
    DesafioCreate,
    DesafioList,
    DesafioResponse,
    DesafioUpdate,
    Empleado360List,
    EmpleadoStarMilesResponse,
    InscripcionAprobar,
    InscripcionCancelar,
    InscripcionCreate,
    InscripcionFinalizar,
    InscripcionIncompleta,
    InscripcionList,
    InscripcionRechazar,
    InscripcionResponse,
    InscripcionRevocar,
    ItemCanjeCreate,
    ItemCanjeList,
    ItemCanjeResponse,
    ItemCanjeUpdate,
    MercadoLibrePrecioResponse,
)
from backend.modules.starmiles.services import (
    STAR_MILES_POR_USD,
    CanjeService,
    CategoriaDesafioService,
    ContenidoCMSService,
    CotizacionService,
    DesafioService,
    EmpleadoStarMilesService,
    InscripcionDesafioService,
    ItemCanjeService,
    MercadoLibreService,
    StarMilesFileService,
    Vista360Service,
)
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/starmiles", tags=["Star Miles"])

# Router público: endpoints de empleado
public_router = APIRouter(prefix="/starmiles", tags=["Star Miles - Empleado"])

# Shortcuts de submódulo
require_home = Depends(require_submodulo("starmiles", "home"))
require_aprobar_inscripciones = Depends(require_submodulo("starmiles", "aprobar_inscripciones"))
require_aprobar_canjes = Depends(require_submodulo("starmiles", "aprobar_canjes"))
require_admin_empleados = Depends(require_submodulo("starmiles", "admin_empleados"))
require_admin_desafios = Depends(require_submodulo("starmiles", "admin_desafios"))
require_admin_canjes = Depends(require_submodulo("starmiles", "admin_canjes"))
require_admin_categorias = Depends(require_submodulo("starmiles", "admin_categorias"))
require_admin_cms = Depends(require_submodulo("starmiles", "admin_cms"))


# ============ HELPERS ============


def _desafio_to_response(d: Desafio) -> DesafioResponse:
    inscripciones_activas = [i for i in d.inscripciones if i.deleted_at is None] if d.inscripciones else []
    total_inscriptos = len([i for i in inscripciones_activas if i.estado in ("pendiente", "aprobada")])
    total_completados = len([i for i in inscripciones_activas if i.estado == "completada"])
    millas_distribuidas = total_completados * d.star_miles
    return DesafioResponse(
        id=str(d.id),
        categoria_id=str(d.categoria_id) if d.categoria_id else None,
        categoria_nombre=d.categoria.nombre if d.categoria else None,
        nombre=d.nombre,
        descripcion=d.descripcion,
        alcance=d.alcance,
        star_miles=d.star_miles,
        fecha_inicio=d.fecha_inicio,
        fecha_vencimiento=d.fecha_vencimiento,
        activo=d.activo,
        inscripcion_unica_por_empleado=d.inscripcion_unica_por_empleado,
        imagen_url=d.imagen_url,
        vigente=DesafioService.esta_vigente(d),
        total_inscriptos=total_inscriptos,
        total_completados=total_completados,
        millas_distribuidas=millas_distribuidas,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _notificar_empleado(
    db: Session,
    empresa_id: uuid.UUID,
    empleado,
    *,
    titulo: str,
    mensaje: str,
    enlace: str,
    tipo: str,
    origen: str,
) -> None:
    usuario = (
        db.query(Usuario)
        .join(
            core_usuario_empresa,
            core_usuario_empresa.c.usuario_id == Usuario.id,
        )
        .filter(
            Usuario.dni == empleado.dni,
            Usuario.activo.is_(True),
            Usuario.deleted_at.is_(None),
            core_usuario_empresa.c.empresa_id == empresa_id,
        )
        .first()
    )
    if not usuario:
        logging.getLogger(__name__).error("No se encontro usuario activo para notificar al empleado %s", empleado.id)
        return
    try:
        NotificacionInternaService.enviar(
            db,
            empresa_id,
            titulo=titulo,
            mensaje=mensaje,
            usuario_ids=[str(usuario.id)],
            enlace=enlace,
            tipo=tipo,
            origen=origen,
        )
    except Exception:
        logging.getLogger(__name__).exception("No se pudo enviar una notificacion interna de Star Miles")


def _inscripcion_to_response(i: InscripcionDesafio) -> InscripcionResponse:
    return InscripcionResponse(
        id=str(i.id),
        desafio_id=str(i.desafio_id),
        desafio_nombre=i.desafio.nombre,
        desafio_star_miles=i.desafio.star_miles,
        empleado_id=str(i.empleado_id),
        empleado_nombre=i.empleado.empleado_nombre_completo,
        estado=i.estado,
        fecha_solicitud=i.fecha_solicitud,
        fecha_aprobacion=i.fecha_aprobacion,
        fecha_finalizacion=i.fecha_finalizacion,
        fecha_rechazo=i.fecha_rechazo,
        aprobador_id=str(i.aprobador_id) if i.aprobador_id else None,
        aprobador_nombre=i.aprobador.empleado_nombre_completo if i.aprobador else None,
        comentario_solicitud=i.comentario_solicitud,
        comentario_aprobador=i.comentario_aprobador,
        created_at=i.created_at,
    )


def _canje_to_response(c: Canje) -> CanjeResponse:
    return CanjeResponse(
        id=str(c.id),
        item_id=str(c.item_id),
        item_nombre=c.item.nombre,
        item_tipo=c.item.tipo,
        item_imagen_url=c.item.imagen_url,
        empleado_id=str(c.empleado_id),
        empleado_nombre=c.empleado.empleado_nombre_completo,
        cantidad=c.cantidad,
        star_miles_total=c.star_miles_total,
        mercadolibre_url=c.mercadolibre_url,
        mercadolibre_precio=float(c.mercadolibre_precio) if c.mercadolibre_precio else None,
        estado=c.estado,
        fecha_solicitud=c.fecha_solicitud,
        fecha_aprobacion=c.fecha_aprobacion,
        fecha_entrega=c.fecha_entrega,
        fecha_rechazo=c.fecha_rechazo,
        aprobador_id=str(c.aprobador_id) if c.aprobador_id else None,
        aprobador_nombre=c.aprobador.empleado_nombre_completo if c.aprobador else None,
        comentario=c.comentario,
        created_at=c.created_at,
    )


def _contenido_to_response(c: ContenidoCMS) -> ContenidoCMSResponse:
    return ContenidoCMSResponse(
        id=str(c.id),
        tipo=c.tipo,
        titulo=c.titulo,
        contenido=c.contenido,
        imagen_url=c.imagen_url,
        empleado_id=str(c.empleado_id) if c.empleado_id else None,
        empleado_nombre=c.empleado.empleado_nombre_completo if c.empleado else None,
        orden=c.orden,
        visible=c.visible,
        fecha_publicacion=c.fecha_publicacion,
        fecha_expiracion=c.fecha_expiracion,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


# ============ CATEGORIAS (lectura pública para filtros) ============


@public_router.get("/categorias", response_model=list[CategoriaDesafioResponse])
async def listar_categorias(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    items = CategoriaDesafioService.listar(db, empresa_id)
    return [CategoriaDesafioResponse.model_validate(c) for c in items]


# ============ CATEGORIAS ADMIN ============


@router.post("/categorias", response_model=CategoriaDesafioResponse, status_code=201)
async def crear_categoria(
    datos: CategoriaDesafioCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_categorias,
):
    try:
        return CategoriaDesafioResponse.model_validate(
            CategoriaDesafioService.crear(db, empresa_id, datos.model_dump())
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear categoría: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear la categoría")


@router.put("/categorias/{id}", response_model=CategoriaDesafioResponse)
async def actualizar_categoria(
    id: str,
    datos: CategoriaDesafioUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_categorias,
):
    try:
        datos_dict = datos.model_dump(exclude_unset=True)
        if not datos_dict:
            raise HTTPException(400, "No hay datos")
        cat = CategoriaDesafioService.actualizar(db, empresa_id, id, datos_dict)
        if not cat:
            raise HTTPException(404, "Categoría no encontrada")
        return CategoriaDesafioResponse.model_validate(cat)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar categoría: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar la categoría")


@router.delete("/categorias/{id}")
async def eliminar_categoria(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_categorias,
):
    try:
        if not CategoriaDesafioService.eliminar(db, empresa_id, id):
            raise HTTPException(404, "Categoría no encontrada")
        return {"message": "Eliminada"}
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al eliminar categoría: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al eliminar la categoría")


# ============ DESAFIOS (lectura pública) ============


@public_router.get("/desafios", response_model=DesafioList)
async def listar_desafios(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    categoria_id: Optional[str] = None,
    alcance: Optional[str] = None,
    ordenar_por: Optional[str] = Query(None, pattern=r"^(nombre|star_miles|fecha_vencimiento|created_at)$"),
    ordenar_dir: Optional[str] = Query("asc", pattern=r"^(asc|desc)$"),
    solo_vigentes: bool = False,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    filtros = {}
    if buscar:
        filtros["buscar"] = buscar
    if categoria_id:
        filtros["categoria_id"] = categoria_id
    if alcance:
        filtros["alcance"] = alcance

    resultado = DesafioService.listar(
        db,
        empresa_id,
        pagina,
        por_pagina,
        filtros,
        solo_vigentes,
        ordenar_por=ordenar_por,
        ordenar_dir=ordenar_dir or "asc",
    )
    return DesafioList(
        items=[_desafio_to_response(d) for d in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@public_router.get("/desafios/{id}", response_model=DesafioResponse)
async def obtener_desafio(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    desafio = DesafioService.obtener(db, empresa_id, id)
    if not desafio:
        raise HTTPException(404, "Desafío no encontrado")
    return _desafio_to_response(desafio)


@public_router.get("/desafios-alcances")
async def listar_alcances(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    """Retorna los valores únicos de alcance (área) de los desafíos."""
    try:
        return DesafioService.obtener_alcances(db, empresa_id)
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al obtener alcances: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al obtener alcances")


# ============ DESAFIOS ADMIN ============


@router.post("/desafios", response_model=DesafioResponse, status_code=201)
async def crear_desafio(
    datos: DesafioCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_desafios,
):
    try:
        return _desafio_to_response(DesafioService.crear(db, empresa_id, datos.model_dump()))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear desafío: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el desafío")


@router.put("/desafios/{id}", response_model=DesafioResponse)
async def actualizar_desafio(
    id: str,
    datos: DesafioUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_desafios,
):
    try:
        datos_dict = datos.model_dump(exclude_unset=True)
        if not datos_dict:
            raise HTTPException(400, "No hay datos")
        desafio = DesafioService.actualizar(db, empresa_id, id, datos_dict)
        if not desafio:
            raise HTTPException(404, "Desafío no encontrado")
        return _desafio_to_response(desafio)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar desafío: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar el desafío")


@router.delete("/desafios/{id}")
async def eliminar_desafio(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_desafios,
):
    try:
        if not DesafioService.eliminar(db, empresa_id, id):
            raise HTTPException(404, "Desafío no encontrado")
        return {"message": "Eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al eliminar desafío: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al eliminar el desafío")


# ============ INSCRIPCIONES (empleado) ============


@public_router.get("/inscripciones", response_model=InscripcionList)
async def listar_inscripciones(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    empleado_id: Optional[str] = None,
    estado: Optional[str] = None,
    buscar: Optional[str] = None,
    desafio_id: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    # Empleados solo ven sus propias inscripciones (resolver por DNI como soporte)
    if current_user.rol != "admin":
        from backend.modules.permisos.services import GrupoService

        permisos = GrupoService.obtener_permisos_usuario(db, str(current_user.id), empresa_id)
        puede_ver_todos = permisos.get("starmiles.aprobar_inscripciones") or permisos.get("starmiles.admin_empleados")
        if not puede_ver_todos:
            emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
            if not emp:
                # Sin ficha de empleado no hay nada propio que mostrar: lista vacía, nunca la de toda la empresa (PG-21)
                return InscripcionList(items=[], total=0, pagina=pagina, por_pagina=por_pagina, total_paginas=1)
            empleado_id = str(emp.id)

    filtros = {}
    if empleado_id:
        filtros["empleado_id"] = empleado_id
    if estado:
        filtros["estado"] = estado
    if buscar:
        filtros["buscar"] = buscar
    if desafio_id:
        filtros["desafio_id"] = desafio_id
    if fecha_desde:
        filtros["fecha_desde"] = fecha_desde
    if fecha_hasta:
        filtros["fecha_hasta"] = fecha_hasta

    resultado = InscripcionDesafioService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return InscripcionList(
        items=[_inscripcion_to_response(i) for i in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@public_router.post("/inscripciones", response_model=InscripcionResponse, status_code=201)
async def crear_inscripcion(
    datos: InscripcionCreate,
    empleado_id: str = Query(..., description="ID del empleado que se inscribe"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    # Validar que solo se inscriba a sí mismo (resolver por DNI como soporte)
    if not current_user.dni:
        raise HTTPException(403, "No tenés un empleado asociado")
    emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni)
    if not emp or str(emp.id) != empleado_id:
        raise HTTPException(403, "Solo podés inscribirte vos mismo")
    try:
        inscripcion = InscripcionDesafioService.crear(db, empresa_id, empleado_id, datos.model_dump())
        return _inscripcion_to_response(inscripcion)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============ INSCRIPCIONES (aprobador) ============


@router.put("/inscripciones/{id}/aprobar", response_model=InscripcionResponse)
async def aprobar_inscripcion(
    id: str,
    datos: InscripcionAprobar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para aprobar")
        inscripcion = InscripcionDesafioService.aprobar(db, empresa_id, id, str(emp.id), datos.comentario_aprobador)
        _notificar_empleado(
            db,
            empresa_id,
            inscripcion.empleado,
            titulo="Inscripcion aprobada",
            mensaje=f'Tu inscripcion al desafio "{inscripcion.desafio.nombre}" fue aprobada.',
            enlace="/starmiles/mis-inscripciones",
            tipo="success",
            origen="starmiles.inscripcion_aprobada",
        )
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al aprobar inscripción: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al aprobar la inscripción")


@router.put("/inscripciones/{id}/rechazar", response_model=InscripcionResponse)
async def rechazar_inscripcion(
    id: str,
    datos: InscripcionRechazar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para rechazar")
        inscripcion = InscripcionDesafioService.rechazar(db, empresa_id, id, str(emp.id), datos.comentario_aprobador)
        _notificar_empleado(
            db,
            empresa_id,
            inscripcion.empleado,
            titulo="Inscripcion rechazada",
            mensaje=f'Tu inscripcion al desafio "{inscripcion.desafio.nombre}" fue rechazada. Motivo: {datos.comentario_aprobador}',
            enlace="/starmiles/mis-inscripciones",
            tipo="warning",
            origen="starmiles.inscripcion_rechazada",
        )
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al rechazar inscripción: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al rechazar la inscripción")


@router.put("/inscripciones/{id}/cancelar", response_model=InscripcionResponse)
async def cancelar_inscripcion(
    id: str,
    datos: InscripcionCancelar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenes un empleado asociado para cancelar")
        inscripcion = InscripcionDesafioService.cancelar(db, empresa_id, id, str(emp.id), datos.comentario_aprobador)
        _notificar_empleado(
            db,
            empresa_id,
            inscripcion.empleado,
            titulo="Inscripcion cancelada",
            mensaje=f'Tu inscripcion al desafio "{inscripcion.desafio.nombre}" fue cancelada. Motivo: {datos.comentario_aprobador}',
            enlace="/starmiles/mis-inscripciones",
            tipo="warning",
            origen="starmiles.inscripcion_cancelada",
        )
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al cancelar inscripcion: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al cancelar la inscripcion")


@router.put("/inscripciones/{id}/finalizar", response_model=InscripcionResponse)
async def finalizar_inscripcion(
    id: str,
    datos: InscripcionFinalizar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para finalizar")
        inscripcion = InscripcionDesafioService.finalizar(db, empresa_id, id, str(emp.id), datos.comentario_aprobador)
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al finalizar inscripción: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al finalizar la inscripción")


@router.put("/inscripciones/{id}/incompleta", response_model=InscripcionResponse)
async def marcar_inscripcion_incompleta(
    id: str,
    datos: InscripcionIncompleta,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado")
        inscripcion = InscripcionDesafioService.marcar_incompleta(
            db, empresa_id, id, str(emp.id), datos.comentario_aprobador
        )
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al marcar inscripción incompleta: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al marcar la inscripción como incompleta")


@router.put("/inscripciones/{id}/revocar", response_model=InscripcionResponse)
async def revocar_inscripcion(
    id: str,
    datos: InscripcionRevocar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_inscripciones,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenes un empleado asociado para revocar")
        inscripcion = InscripcionDesafioService.revocar(db, empresa_id, id, str(emp.id), datos.comentario_aprobador)
        _notificar_empleado(
            db,
            empresa_id,
            inscripcion.empleado,
            titulo="Inscripcion revocada",
            mensaje=f'Tu inscripcion al desafio "{inscripcion.desafio.nombre}" fue revocada. Motivo: {datos.comentario_aprobador}',
            enlace="/starmiles/mis-inscripciones",
            tipo="warning",
            origen="starmiles.inscripcion_revocada",
        )
        return _inscripcion_to_response(inscripcion)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al revocar inscripcion: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al revocar la inscripcion")


# ============ MERCADOLIBRE Y CALCULADORA (empleado) ============


@public_router.get("/mercadolibre/precio", response_model=MercadoLibrePrecioResponse)
async def obtener_precio_mercadolibre(
    url: str = Query(..., description="URL del producto de MercadoLibre"), current_user=require_home
):
    """Obtiene el precio de un producto de MercadoLibre y calcula las Star Miles."""
    try:
        resultado = await MercadoLibreService.obtener_precio(url)
        return MercadoLibrePrecioResponse(**resultado)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al consultar MercadoLibre: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al consultar MercadoLibre")


@public_router.post("/calcular-millas", response_model=CalcularMillasResponse)
async def calcular_millas_desde_precio(datos: CalcularMillasRequest, current_user=require_home):
    """Calcula las Star Miles desde un precio en pesos usando cotización del dólar."""
    try:
        cotizacion_usd = await CotizacionService.obtener_cotizacion_usd()
        precio_usd = datos.precio / cotizacion_usd
        star_miles = int(precio_usd * STAR_MILES_POR_USD)

        return CalcularMillasResponse(
            precio_ars=datos.precio,
            cotizacion_usd=round(cotizacion_usd, 2),
            precio_usd=round(precio_usd, 2),
            star_miles=star_miles,
        )
    except Exception as e:
        logging.getLogger(__name__).error(f"Error al calcular millas: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al calcular millas")


# ============ ITEMS CANJE (lectura pública) ============


@public_router.get("/items-canje", response_model=ItemCanjeList)
async def listar_items_canje(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    solo_activos: bool = False,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    filtros = {"buscar": buscar} if buscar else {}
    resultado = ItemCanjeService.listar(db, empresa_id, pagina, por_pagina, filtros, solo_activos)
    return ItemCanjeList(
        items=[ItemCanjeResponse.model_validate(i) for i in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@public_router.get("/items-canje/{id}", response_model=ItemCanjeResponse)
async def obtener_item_canje(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    item = ItemCanjeService.obtener(db, empresa_id, id)
    if not item:
        raise HTTPException(404, "Item no encontrado")
    return ItemCanjeResponse.model_validate(item)


# ============ ITEMS CANJE ADMIN ============


@router.post("/items-canje", response_model=ItemCanjeResponse, status_code=201)
async def crear_item_canje(
    datos: ItemCanjeCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_canjes,
):
    try:
        return ItemCanjeResponse.model_validate(ItemCanjeService.crear(db, empresa_id, datos.model_dump()))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear item de canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el item de canje")


@router.put("/items-canje/{id}", response_model=ItemCanjeResponse)
async def actualizar_item_canje(
    id: str,
    datos: ItemCanjeUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_canjes,
):
    try:
        datos_dict = datos.model_dump(exclude_unset=True)
        if not datos_dict:
            raise HTTPException(400, "No hay datos")
        item = ItemCanjeService.actualizar(db, empresa_id, id, datos_dict)
        if not item:
            raise HTTPException(404, "Item no encontrado")
        return ItemCanjeResponse.model_validate(item)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar item de canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar el item de canje")


@router.delete("/items-canje/{id}")
async def eliminar_item_canje(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_canjes,
):
    try:
        if not ItemCanjeService.eliminar(db, empresa_id, id):
            raise HTTPException(404, "Item no encontrado")
        return {"message": "Eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al eliminar item de canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al eliminar el item de canje")


# ============ CANJES (empleado) ============


@public_router.get("/canjes", response_model=CanjeList)
async def listar_canjes(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    empleado_id: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    # Empleados solo ven sus propios canjes (resolver por DNI como soporte)
    if current_user.rol != "admin":
        from backend.modules.permisos.services import GrupoService

        permisos = GrupoService.obtener_permisos_usuario(db, str(current_user.id), empresa_id)
        puede_ver_todos = permisos.get("starmiles.aprobar_canjes") or permisos.get("starmiles.admin_empleados")
        if not puede_ver_todos:
            emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
            if not emp:
                # Sin ficha de empleado no hay nada propio que mostrar: lista vacía, nunca la de toda la empresa (PG-21)
                return CanjeList(items=[], total=0, pagina=pagina, por_pagina=por_pagina, total_paginas=1)
            empleado_id = str(emp.id)

    filtros = {}
    if empleado_id:
        filtros["empleado_id"] = empleado_id
    if estado:
        filtros["estado"] = estado

    resultado = CanjeService.listar(db, empresa_id, pagina, por_pagina, filtros)
    return CanjeList(
        items=[_canje_to_response(c) for c in resultado["items"]],
        total=resultado["total"],
        pagina=resultado["pagina"],
        por_pagina=resultado["por_pagina"],
        total_paginas=resultado["total_paginas"],
    )


@public_router.post("/canjes", response_model=CanjeResponse, status_code=201)
async def crear_canje(
    datos: CanjeCreate,
    empleado_id: str = Query(..., description="ID del empleado que canjea"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    # Validar que solo canjee para sí mismo (resolver por DNI como soporte)
    if not current_user.dni:
        raise HTTPException(403, "No tenés un empleado asociado")
    emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni)
    if not emp or str(emp.id) != empleado_id:
        raise HTTPException(403, "Solo podés canjear vos mismo")
    try:
        canje = CanjeService.crear(db, empresa_id, empleado_id, datos.model_dump())
        return _canje_to_response(canje)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ============ CANJES (aprobador) ============


@router.put("/canjes/{id}/aprobar", response_model=CanjeResponse)
async def aprobar_canje(
    id: str,
    datos: CanjeAprobar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_canjes,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para aprobar")
        canje = CanjeService.aprobar(db, empresa_id, id, str(emp.id), datos.comentario)
        _notificar_empleado(
            db,
            empresa_id,
            canje.empleado,
            titulo="Canje aprobado",
            mensaje=f'Tu canje de "{canje.item.nombre}" fue aprobado.',
            enlace="/starmiles/mis-canjes",
            tipo="success",
            origen="starmiles.canje_aprobado",
        )
        return _canje_to_response(canje)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al aprobar canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al aprobar el canje")


@router.put("/canjes/{id}/rechazar", response_model=CanjeResponse)
async def rechazar_canje(
    id: str,
    datos: CanjeRechazar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_canjes,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para rechazar")
        canje = CanjeService.rechazar(db, empresa_id, id, str(emp.id), datos.comentario)
        _notificar_empleado(
            db,
            empresa_id,
            canje.empleado,
            titulo="Canje rechazado",
            mensaje=f'Tu canje de "{canje.item.nombre}" fue rechazado. Motivo: {datos.comentario}',
            enlace="/starmiles/mis-canjes",
            tipo="warning",
            origen="starmiles.canje_rechazado",
        )
        return _canje_to_response(canje)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al rechazar canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al rechazar el canje")


@router.put("/canjes/{id}/rechazar-y-reintegrar", response_model=CanjeResponse)
async def rechazar_y_reintegrar_canje(
    id: str,
    datos: CanjeRechazarYReintegrar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_canjes,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenes un empleado asociado para rechazar")
        canje = CanjeService.rechazar_y_reintegrar(db, empresa_id, id, str(emp.id), datos.comentario)
        _notificar_empleado(
            db,
            empresa_id,
            canje.empleado,
            titulo="Canje rechazado y millas reintegradas",
            mensaje=f'Tu canje de "{canje.item.nombre}" fue rechazado y se reintegraron {canje.star_miles_total} Star Miles. Motivo: {datos.comentario}',
            enlace="/starmiles/mis-canjes",
            tipo="warning",
            origen="starmiles.canje_reintegrado",
        )
        return _canje_to_response(canje)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al reintegrar canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al rechazar y reintegrar el canje")


@router.put("/canjes/{id}/entregar", response_model=CanjeResponse)
async def entregar_canje(
    id: str,
    datos: CanjeEntregar,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_aprobar_canjes,
):
    try:
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni) if current_user.dni else None
        if not emp:
            raise HTTPException(403, "No tenés un empleado asociado para entregar")
        canje = CanjeService.entregar(db, empresa_id, id, str(emp.id), datos.comentario)
        _notificar_empleado(
            db,
            empresa_id,
            canje.empleado,
            titulo="Canje entregado",
            mensaje=f'Tu canje de "{canje.item.nombre}" fue entregado.',
            enlace="/starmiles/mis-canjes",
            tipo="success",
            origen="starmiles.canje_entregado",
        )
        return _canje_to_response(canje)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al entregar canje: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al entregar el canje")


# ============ MIS MILLAS (empleado) ============


@public_router.get("/mis-millas/{empleado_id}", response_model=EmpleadoStarMilesResponse)
async def obtener_mis_millas(
    empleado_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    # Validar que solo consulte sus propias millas (resolver por DNI como soporte)
    if current_user.rol != "admin":
        if not current_user.dni:
            raise HTTPException(403, "No tenés un empleado asociado")
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni)
        if not emp or str(emp.id) != empleado_id:
            raise HTTPException(403, "Solo podés consultar tus propias millas")

    cuenta = EmpleadoStarMilesService.obtener_o_crear(db, empresa_id, empleado_id)
    return EmpleadoStarMilesResponse(
        id=str(cuenta.id),
        empleado_id=str(cuenta.empleado_id),
        empleado_nombre=cuenta.empleado.empleado_nombre_completo,
        millas_historicas=cuenta.millas_historicas,
        millas_disponibles=cuenta.millas_disponibles,
        created_at=cuenta.created_at,
        updated_at=cuenta.updated_at,
    )


# ============ CMS (lectura pública) ============


@public_router.get("/cms", response_model=ContenidoCMSList)
async def listar_contenido_cms(
    tipo: Optional[str] = None,
    solo_visibles: bool = False,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    resultado = ContenidoCMSService.listar(db, empresa_id, tipo, solo_visibles)
    return ContenidoCMSList(items=[_contenido_to_response(c) for c in resultado["items"]], total=resultado["total"])


@public_router.get("/cms/{id}", response_model=ContenidoCMSResponse)
async def obtener_contenido_cms(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_home,
):
    contenido = ContenidoCMSService.obtener(db, empresa_id, id)
    if not contenido:
        raise HTTPException(404, "Contenido no encontrado")
    return _contenido_to_response(contenido)


# ============ CMS ADMIN ============


@router.post("/cms", response_model=ContenidoCMSResponse, status_code=201)
async def crear_contenido_cms(
    datos: ContenidoCMSCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_cms,
):
    try:
        return _contenido_to_response(ContenidoCMSService.crear(db, empresa_id, datos.model_dump()))
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al crear contenido CMS: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear el contenido")


@router.put("/cms/{id}", response_model=ContenidoCMSResponse)
async def actualizar_contenido_cms(
    id: str,
    datos: ContenidoCMSUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_cms,
):
    try:
        datos_dict = datos.model_dump(exclude_unset=True)
        if not datos_dict:
            raise HTTPException(400, "No hay datos")
        contenido = ContenidoCMSService.actualizar(db, empresa_id, id, datos_dict)
        if not contenido:
            raise HTTPException(404, "Contenido no encontrado")
        return _contenido_to_response(contenido)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al actualizar contenido CMS: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar el contenido")


@router.delete("/cms/{id}")
async def eliminar_contenido_cms(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_cms,
):
    try:
        if not ContenidoCMSService.eliminar(db, empresa_id, id):
            raise HTTPException(404, "Contenido no encontrado")
        return {"message": "Eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error inesperado al eliminar contenido CMS: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al eliminar el contenido")


# ============ VISTA 360 EMPLEADOS ============


@router.get("/empleados-360", response_model=Empleado360List)
async def listar_empleados_360(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    orden: Optional[str] = Query("millas_historicas", pattern=r"^(millas_historicas|millas_disponibles|nombre)$"),
    direccion: Optional[str] = Query("desc", pattern=r"^(asc|desc)$"),
    millas_min: Optional[int] = Query(None, ge=0),
    millas_max: Optional[int] = Query(None, ge=0),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_empleados,
):
    """Vista 360 de todos los empleados con sus millas, inscripciones y canjes."""
    filtros = {
        "buscar": buscar,
        "orden": orden,
        "direccion": direccion,
        "millas_min": millas_min,
        "millas_max": millas_max,
    }
    resultado = Vista360Service.listar_empleados_360(db, empresa_id, pagina, por_pagina, filtros)
    return Empleado360List(**resultado)


@router.get("/empleados-360/{empleado_id}")
async def obtener_empleado_360(
    empleado_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_empleados,
):
    """Detalle 360 de un empleado específico."""
    resultado = Vista360Service.obtener_empleado_360(db, empresa_id, empleado_id)
    if not resultado:
        raise HTTPException(404, "Empleado no encontrado")
    return resultado


# ============ UPLOAD DE IMÁGENES ============


@router.post("/upload-imagen")
async def upload_imagen_starmiles(
    file: UploadFile = File(...), context: str = Form("default"), current_user=require_admin_cms
):
    """Sube una imagen para Star Miles comprimida según el contexto de uso.

    Args:
        file: Archivo de imagen.
        context: Contexto de uso que determina las dimensiones de compresión.
                 Valores: 'desafio', 'canje', 'cms_banner', 'cms_noticia', 'default'.
    """
    try:
        url = await StarMilesFileService.save_image(file, context=context)
        return {"url": url, "filename": file.filename}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Error inesperado al subir imagen")
