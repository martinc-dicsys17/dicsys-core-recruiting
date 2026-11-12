"""
Rutas FastAPI para el módulo de Soporte Técnico (v28.0).
Restauración completa de funcionalidad normalizada.
"""

import logging
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_empresa_activa, get_empresa_cuit, require_submodulo
from backend.modules.nomina.services import EmpleadoService
from backend.modules.soporte import schemas
from backend.modules.soporte.constants import TicketEstado
from backend.modules.soporte.models import Ticket
from backend.modules.soporte.services import SoporteService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/soporte", tags=["soporte"])
logger = logging.getLogger("soporte")


# Shortcuts para las dependencies de cada submódulo
require_dashboard = Depends(require_submodulo("soporte", "dashboard"))
require_tickets = Depends(require_submodulo("soporte", "tickets_kanban"))
require_stock = Depends(require_submodulo("soporte", "stock_list"))
require_mis_solicitudes = Depends(require_submodulo("soporte", "mis_solicitudes"))

# ─── Gestión de Tickets ────────────────────────────────────────────


@router.get("/tickets", response_model=schemas.TicketListResponse)
async def listar_tickets(
    estado_id: Optional[str] = None,
    prioridad: Optional[str] = None,
    sub_id: Optional[str] = None,
    categoria_id: Optional[str] = None,
    buscar: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Lista tickets con filtros máster."""
    # Si viene categoria_id, usarlo como sub_id (son lo mismo, subcategorías)
    if categoria_id and not sub_id:
        sub_id = categoria_id

    tickets, total = SoporteService.listar_tickets(
        db,
        empresa_id,
        estado_id=estado_id,
        prioridad=prioridad,
        sub_id=sub_id,
        buscar=buscar,
        page=page,
        per_page=per_page,
    )
    return {"items": tickets, "total": total}


@router.get("/tickets/mis-tickets", response_model=schemas.TicketListResponse)
async def listar_mis_tickets(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Lista tickets del usuario actual resolviendo su identidad via DNI."""
    items, total = SoporteService.listar_mis_tickets(db, empresa_id, current_user.dni)
    return {"items": items, "total": total}


@router.post("/tickets", response_model=schemas.TicketResponse)
async def crear_ticket(
    datos: schemas.TicketCreateSchema,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Crea ticket polimórfico v28.0."""
    try:
        # Validar permiso para tickets de alta/baja
        sub = SoporteService.obtener_subcategoria(db, uuid.UUID(str(datos.subcategoria_id)), empresa_id)
        if sub and sub.tipo_ticket_asociado == "alta_baja":
            es_admin = current_user.rol == "admin"
            es_manager_reclutamiento = SoporteService._es_manager_hrbp(db, empresa_id, current_user.dni)
            if not es_admin and not es_manager_reclutamiento:
                raise HTTPException(
                    status_code=403, detail="Solo el manager de Reclutamiento puede crear tickets de alta/baja"
                )

        return SoporteService.crear_ticket(db, empresa_id, datos.model_dump(), current_user.email)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al crear ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear ticket")


# ─── Dashboard y Analítica (Vistas Especializadas) ───────────────────


@router.get("/tickets/kanban", response_model=schemas.KanbanResponse)
async def vista_kanban(
    categoria_id: Optional[str] = None,
    buscar: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Tablero Kanban puro v28.0 mapeado por estados."""
    return SoporteService.kanban(db, empresa_id, categoria_id, buscar)


@router.get("/tickets/stats")
async def obtener_stats_tickets(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Obtiene estadísticas de tickets."""
    resultado = SoporteService.kanban(db, empresa_id, None, None)
    return resultado.get("stats", {})


@router.get("/dashboard-metrics")
async def metricas_centro_mando(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_dashboard,
):
    """Métricas avanzadas para el Centro de Mando."""
    return SoporteService.dashboard_metrics(db, empresa_id)


# ─── Operaciones Individuales de Tickets ───────────────────────────


@router.get("/tickets/{ticket_id}", response_model=schemas.TicketResponse)
async def obtener_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    ticket_dict = SoporteService.obtener_ticket_completo(db, empresa_id, ticket_id)
    if not ticket_dict:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return schemas.TicketResponse.model_validate(ticket_dict)


@router.put("/tickets/{ticket_id}")
async def actualizar_ticket(
    ticket_id: str,
    datos: Dict = Body(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Actualiza campos de un ticket (alta/baja: activo_id, matriz, kit)."""
    try:
        SoporteService.validar_ticket_no_cerrado(db, empresa_id, ticket_id)
        ticket = SoporteService.actualizar_ticket(db, empresa_id, ticket_id, datos, current_user.email)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
        return {"message": "Ticket actualizado"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al actualizar ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar ticket")


@router.put("/tickets/{ticket_id}/estado")
async def cambiar_estado_ticket(
    ticket_id: str,
    nuevo_estado_id: str = Body(..., embed=True),
    resolucion: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    try:
        ticket = SoporteService.cambiar_estado(
            db, empresa_id, ticket_id, nuevo_estado_id, resolucion, current_user.email, current_user.dni
        )
        return {
            "message": "Estado actualizado",
            "estado": ticket.estado_rel.clave if ticket.estado_rel else "desconocido",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al cambiar estado de ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al cambiar estado")


@router.post("/tickets/{ticket_id}/cancelar-propia")
async def cancelar_mi_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Cancela una solicitud propia.

    Validaciones:
    - El ticket debe existir en la empresa activa.
    - El usuario autenticado debe ser el solicitante (match por DNI).
    - El ticket no puede estar ya en un estado terminal (resuelto/cerrado/cancelado).
    """
    try:
        ticket = (
            db.query(Ticket)
            .filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id, Ticket.deleted_at.is_(None))
            .first()
        )
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")

        # Validar ownership: el solicitante debe coincidir por DNI con el usuario actual
        if not current_user.dni or not ticket.solicitante or ticket.solicitante.dni != current_user.dni:
            raise HTTPException(status_code=403, detail="Solo podés cancelar tus propias solicitudes")

        estado_cancelado = SoporteService.obtener_estado_ticket(db, TicketEstado.CANCELADO)
        if not estado_cancelado:
            raise HTTPException(status_code=500, detail="Estado 'cancelado' no configurado")

        ticket_resultado = SoporteService.cambiar_estado(
            db,
            empresa_id,
            ticket_id,
            str(estado_cancelado.id),
            resolucion=None,
            usuario_email=current_user.email,
            usuario_dni=current_user.dni,
        )
        return {"message": "Solicitud cancelada", "estado": ticket_resultado.estado_rel.clave}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al cancelar solicitud propia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al cancelar la solicitud")


@router.delete("/tickets/{ticket_id}")
async def eliminar_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Elimina un ticket si el usuario tiene permiso (Solo Admin/Soporte) v28.0."""
    try:
        SoporteService.eliminar_ticket(db, empresa_id, ticket_id)
        return {"result": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al eliminar ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al eliminar ticket")


@router.post("/tickets/{ticket_id}/iniciar-peritaje", response_model=schemas.TicketResponse)
async def iniciar_peritaje(
    ticket_id: str,
    diagnostico: str = Body(..., embed=True),
    matriz_datos: Dict = Body(..., embed=True),
    activo_id: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Inicia la reparación técnica de un ticket.

    Cubre ambos escenarios:
      - Ticket genérico con falla detectada: se promueve a reparación. Requiere activo_id si el ticket aún no lo tiene vinculado.
      - Ticket nacido como tipo reparación: registra el peritaje de entrada y pasa a 'en_progreso' si estaba abierto.

    En ambos casos crea la matriz de estado, registra historial y deja el activo en estado EN_REPARACION.
    """
    try:
        return SoporteService.iniciar_peritaje(
            db, empresa_id, ticket_id, diagnostico, matriz_datos, current_user.email, activo_id=activo_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al iniciar peritaje: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al iniciar peritaje")


@router.post("/tickets/{ticket_id}/generar-pedido")
async def generar_pedido_reparacion(
    ticket_id: str,
    tipo_pedido: str = Body(..., embed=True),
    descripcion: str = Body(..., embed=True),
    monto_estimado: float = Body(0.0, embed=True),
    insumo_id: Optional[str] = Body(None, embed=True),
    cantidad_solicitada: int = Body(0, embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Genera un pedido de compra vinculado a un ticket."""
    try:
        pedido = SoporteService.generar_pedido_reparacion(
            db,
            empresa_id,
            ticket_id,
            tipo_pedido,
            descripcion,
            monto_estimado,
            current_user.email,
            insumo_id=insumo_id,
            cantidad_solicitada=cantidad_solicitada,
        )
        return {
            "message": "Pedido de compra creado exitosamente",
            "pedido_numero": pedido.numero,
            "pedido_id": str(pedido.id),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al generar pedido: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al generar pedido")


# ─── Pedidos de Compra ─────────────────────────────────────────────


@router.get("/pedidos", response_model=schemas.PedidoCompraListResponse)
async def listar_pedidos(
    estado: Optional[str] = Query(None),
    ticket_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Lista pedidos de compra con filtros opcionales."""
    items = SoporteService.listar_pedidos(db, empresa_id, estado_clave=estado, ticket_id=ticket_id)
    return {"items": [schemas.PedidoCompraResponse.model_validate(p) for p in items], "total": len(items)}


@router.get("/pedidos/{pedido_id}", response_model=schemas.PedidoCompraResponse)
async def obtener_pedido(
    pedido_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Detalle de un pedido con presupuestos y aprobaciones."""
    pedido = SoporteService.obtener_pedido(db, empresa_id, pedido_id)
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    resp = schemas.PedidoCompraResponse.model_validate(pedido)
    if pedido.insumo_rel:
        resp.insumo_nombre = pedido.insumo_rel.nombre
    return resp


@router.put("/pedidos/{pedido_id}/estado")
async def cambiar_estado_pedido(
    pedido_id: str,
    estado: str = Body(..., embed=True),
    cantidad_recibida: Optional[int] = Body(None, embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Cambia el estado de un pedido (enviar a aprobacion, cancelar, recibir)."""
    try:
        datos = {}
        if cantidad_recibida is not None:
            datos["cantidad_recibida"] = cantidad_recibida
        pedido = SoporteService.cambiar_estado_pedido(db, empresa_id, pedido_id, estado, current_user.email, datos)
        return schemas.PedidoCompraResponse.model_validate(pedido)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al cambiar estado de pedido: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al cambiar estado del pedido")


@router.put("/pedidos/{pedido_id}/presupuestos/{presupuesto_id}/seleccionar")
async def seleccionar_presupuesto(
    pedido_id: str,
    presupuesto_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Marca un presupuesto como el elegido por el técnico."""
    try:
        SoporteService.seleccionar_presupuesto(db, empresa_id, pedido_id, presupuesto_id, current_user.email)
        pedido = SoporteService.obtener_pedido(db, empresa_id, pedido_id)
        return schemas.PedidoCompraResponse.model_validate(pedido)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al seleccionar presupuesto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al seleccionar presupuesto")


@router.post("/pedidos/{pedido_id}/presupuestos")
async def agregar_presupuesto(
    pedido_id: str,
    proveedor: Optional[str] = Body(None, embed=True),
    articulo_descripcion: Optional[str] = Body(None, embed=True),
    monto: Optional[float] = Body(None, embed=True),
    es_obligatorio: bool = Body(True, embed=True),
    archivo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user: Usuario = require_tickets,
):
    """Agrega un presupuesto (con archivo opcional) a un pedido."""
    try:
        url_archivo = None
        if archivo and archivo.filename:
            # Usar el método del servicio para mantener la estructura organizada
            url_archivo = await SoporteService.subir_presupuesto_pedido(db, pedido_id, archivo, empresa_cuit)

        datos = {
            "proveedor": proveedor,
            "articulo_descripcion": articulo_descripcion,
            "monto": monto,
            "es_obligatorio": es_obligatorio,
        }
        presupuesto = SoporteService.agregar_presupuesto(
            db, empresa_id, pedido_id, datos, url_archivo, current_user.email
        )
        return schemas.PedidoPresupuestoResponse.model_validate(presupuesto)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al agregar presupuesto: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al agregar presupuesto")


@router.post("/tickets/{ticket_id}/imagen")
async def subir_imagen_ticket(
    ticket_id: str,
    file: UploadFile = File(...),
    categoria: str = Query("general", description="Categoría de la evidencia: general, acuerdo_firmado, estado_equipo"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user: Usuario = require_mis_solicitudes,
):
    """Sube una imagen y la vincula al ticket via auditoría v28.0."""
    try:
        SoporteService.validar_ticket_no_cerrado(db, empresa_id, ticket_id)
        return await SoporteService.subir_archivo_soporte(
            db, ticket_id, file, current_user.email, empresa_id, empresa_cuit, categoria
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al subir imagen: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al subir imagen")


@router.delete("/tickets/{ticket_id}/evidencia/{evidencia_id}")
async def eliminar_evidencia_ticket(
    ticket_id: str,
    evidencia_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Elimina (soft delete) una evidencia de un ticket."""
    try:
        SoporteService.eliminar_evidencia(db, empresa_id, ticket_id, evidencia_id)
        return {"message": "Evidencia eliminada"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al eliminar evidencia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al eliminar evidencia")


# ─── Gestión de Activos y Stock ────────────────────────────────────


@router.get("/activos", response_model=schemas.ActivoListResponse)
async def listar_activos(
    tipo_id: Optional[str] = None,
    estado: Optional[str] = None,
    buscar: Optional[str] = None,
    asignado_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Lista activos con filtros múltiples v28.0."""
    items = SoporteService.listar_activos(db, empresa_id, tipo_id, estado, buscar, asignado_id)
    return {"items": items, "total": len(items)}


@router.get("/activos/{activo_id}", response_model=schemas.ActivoResponse)
async def obtener_activo(
    activo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    item = SoporteService.obtener_activo(db, empresa_id, activo_id)

    if not item:
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    return item


@router.post("/activos", response_model=schemas.ActivoResponse)
async def crear_activo(
    datos: schemas.ActivoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    try:
        return SoporteService.crear_activo(db, empresa_id, datos.model_dump(), current_user.email)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error al crear activo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear activo")


@router.put("/activos/{activo_id}", response_model=schemas.ActivoResponse)
async def actualizar_activo(
    activo_id: str,
    datos: schemas.ActivoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Actualiza un activo con lógica de especificaciones v28.0."""
    try:
        item = SoporteService.actualizar_activo(
            db, empresa_id, activo_id, datos.model_dump(exclude_unset=True), current_user.email
        )
        if not item:
            raise HTTPException(status_code=404, detail="Activo no encontrado")
        return item
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error al actualizar activo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar activo")


@router.delete("/activos/{activo_id}")
async def eliminar_activo(
    activo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Elimina (soft delete) un activo de stock."""
    if not SoporteService.eliminar_activo(db, empresa_id, activo_id):
        raise HTTPException(status_code=404, detail="Activo no encontrado")
    return {"status": "ok"}


# ─── Matriz de Estado ──────────────────────────────────────────────


@router.post("/matriz-estado", response_model=schemas.MatrizEstadoResponse, status_code=201)
async def crear_matriz_estado(
    datos: schemas.MatrizEstadoBase,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Crea una nueva matriz de estado físico para un equipo."""
    return SoporteService.crear_matriz_estado(db, empresa_id, datos.model_dump(), current_user.email)


@router.get("/sistemas-disponibles")
async def listar_sistemas_disponibles(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Devuelve el catálogo de sistemas habilitables en un alta, desde la DB."""
    return {"sistemas": SoporteService.listar_sistemas_disponibles(db, empresa_id=empresa_id)}


@router.get("/colaborador-alta-info/{colaborador_id}")
async def obtener_info_colaborador_alta(
    colaborador_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Devuelve datos sensibles del colaborador para precargar el formulario de alta IT.

    Acceso restringido a admin o manager de Reclutamiento, ya que expone PII
    (DNI, teléfono personal, email personal, dirección).
    """
    es_admin = current_user.rol == "admin"
    es_manager_reclutamiento = SoporteService._es_manager_hrbp(db, empresa_id, current_user.dni)
    if not es_admin and not es_manager_reclutamiento:
        raise HTTPException(
            status_code=403, detail="Solo el manager de Reclutamiento puede consultar los datos de un colaborador"
        )
    try:
        return SoporteService.obtener_info_colaborador_alta(db, empresa_id, colaborador_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Checklist Alta/Baja ───────────────────────────────────────────


@router.get("/tickets/{ticket_id}/checklist")
async def obtener_checklist(
    ticket_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    items = SoporteService.obtener_checklist(db, empresa_id, ticket_id)
    return {
        "items": [
            {
                "id": str(i.id),
                "item_clave": i.item_clave,
                "item_label": i.item_label,
                "completado": i.completado,
                "completado_por": i.completado_por,
                "completado_at": i.completado_at.isoformat() if i.completado_at else None,
                "orden": i.orden,
            }
            for i in items
        ]
    }


@router.put("/checklist/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    try:
        item = SoporteService.toggle_checklist_item(db, empresa_id, item_id, current_user.email)
        return {
            "id": str(item.id),
            "completado": item.completado,
            "completado_por": item.completado_por,
            "completado_at": item.completado_at.isoformat() if item.completado_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/activos/disponibles/buscar")
async def buscar_activos_disponibles(
    q: str = Query("", description="Búsqueda por nombre, número de serie o inventario"),
    todos: bool = Query(False, description="Si True, incluye activos asignados (para mantenimiento)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Busca equipos disponibles para asignar (estado='disponible'). Con todos=True incluye asignados."""
    # Validación en backend: mínimo 2 caracteres
    if not q or len(q.strip()) < 2:
        return []

    # Validación de seguridad: solo admin puede usar todos=True
    if todos and current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="No autorizado para ver todos los activos")

    return SoporteService.buscar_activos_disponibles(db, empresa_id, q.strip(), todos)


@router.get("/activos/buscar")
async def buscar_activos(
    q: str = Query("", description="Búsqueda por nombre, número de serie, inventario o marca"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de activo (notebook, monitor, etc)"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """
    Busca activos con filtrado backend (reemplaza filtrado JS en frontend).
    Filtra por empresa_id y deleted_at automáticamente.
    """
    # Validación en backend: mínimo 2 caracteres
    if not q or len(q.strip()) < 2:
        return []

    from sqlalchemy import or_

    from backend.modules.soporte.models import Activo, ActivoTipo, SoporteActivosMarca

    query = (
        db.query(Activo)
        .join(ActivoTipo, Activo.tipo_id == ActivoTipo.id, isouter=True)
        .join(SoporteActivosMarca, Activo.marca_id == SoporteActivosMarca.id, isouter=True)
        .filter(Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
    )

    # Filtro de búsqueda por múltiples campos
    search_term = f"%{q.strip()}%"
    query = query.filter(
        or_(
            Activo.nombre.ilike(search_term),
            Activo.numero_inventario.ilike(search_term),
            Activo.numero_serie.ilike(search_term),
            SoporteActivosMarca.nombre.ilike(search_term),
        )
    )

    # Filtro opcional por tipo
    if tipo:
        query = query.filter(ActivoTipo.clave == tipo)

    activos = query.limit(50).all()

    return [
        {
            "id": str(a.id),
            "nombre": a.nombre,
            "numero_inventario": a.numero_inventario,
            "numero_serie": a.numero_serie,
            "marca": a.marca_rel.nombre if a.marca_rel else None,
            "tipo": a.tipo_rel.nombre if a.tipo_rel else None,
            "estado": a.estado,
        }
        for a in activos
    ]


# ─── Insumos ───────────────────────────────────────────────────────


@router.get("/insumos")
async def listar_insumos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    items = SoporteService.listar_insumos(db, empresa_id)
    return {"items": items}


@router.get("/insumos/{insumo_id}")
async def obtener_insumo(
    insumo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    insumo = SoporteService.obtener_insumo(db, empresa_id, insumo_id)
    if not insumo:
        raise HTTPException(404, "Insumo no encontrado")
    stock_actual = SoporteService.calcular_stock(db, empresa_id, insumo.id)
    return {
        "id": str(insumo.id),
        "nombre": insumo.nombre,
        "descripcion": insumo.descripcion,
        "stock_actual": stock_actual,
        "stock_minimo": insumo.stock_minimo,
        "unidad_medida": insumo.unidad_medida,
        "categoria_id": str(insumo.categoria_id) if insumo.categoria_id else None,
    }


@router.post("/insumos")
async def crear_insumo(
    datos: schemas.InsumoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    try:
        insumo = SoporteService.crear_insumo(db, empresa_id, datos.model_dump(), current_user.email)
        return {
            "id": str(insumo.id),
            "nombre": insumo.nombre,
            "descripcion": insumo.descripcion,
            "stock_actual": insumo.stock_actual,
            "stock_minimo": insumo.stock_minimo,
            "unidad_medida": insumo.unidad_medida,
        }
    except IntegrityError:
        raise HTTPException(422, "Referencia inválida: categoria_id no existe en la base de datos")
    except Exception as e:
        logger.error(f"Error al crear insumo: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al crear insumo")


@router.put("/insumos/{insumo_id}")
async def actualizar_insumo(
    insumo_id: str,
    datos: schemas.InsumoUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    try:
        insumo = SoporteService.actualizar_insumo(
            db, empresa_id, insumo_id, datos.model_dump(exclude_unset=True), current_user.email
        )
        if not insumo:
            raise HTTPException(404, "Insumo no encontrado")
        return {
            "id": str(insumo.id),
            "nombre": insumo.nombre,
            "descripcion": insumo.descripcion,
            "stock_minimo": insumo.stock_minimo,
            "unidad_medida": insumo.unidad_medida,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar insumo: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar insumo")


@router.delete("/insumos/{insumo_id}")
async def eliminar_insumo(
    insumo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    if not SoporteService.eliminar_insumo(db, empresa_id, insumo_id, current_user.email):
        raise HTTPException(404, "Insumo no encontrado")
    return {"message": "Insumo eliminado"}


@router.post("/insumos/{insumo_id}/ajustar-stock")
async def ajustar_stock_insumo(
    insumo_id: str,
    datos: schemas.AjusteStockSchema,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    try:
        cantidad = datos.cantidad
        motivo = datos.motivo
        movimiento = SoporteService.ajustar_stock_insumo(
            db, empresa_id, insumo_id, cantidad, motivo, current_user.email
        )
        return {
            "id": str(movimiento.id),
            "tipo": movimiento.tipo,
            "cantidad": movimiento.cantidad,
            "motivo": movimiento.motivo,
        }
    except IntegrityError:
        raise HTTPException(422, "Referencia inválida: insumo_id no existe en la base de datos")
    except Exception as e:
        logger.error(f"Error al ajustar stock: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al ajustar stock")


# ─── Insumos e Integración ─────────────────────────────────────────


@router.post("/tickets/{ticket_id}/insumos")
async def agregar_insumo_ticket(
    ticket_id: str,
    insumo_id: str = Body(..., embed=True),
    cantidad: int = Body(1, embed=True),
    generar_pedido: bool = Body(False, embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Vincula insumo con lógica de stock/compras v28.0."""
    try:
        return SoporteService.agregar_insumo_a_ticket(
            db, empresa_id, ticket_id, insumo_id, cantidad, generar_pedido, current_user.email
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al agregar insumo a ticket: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al agregar insumo")


@router.get("/insumos-consumos")
async def listar_consumos(
    insumo_id: Optional[str] = None,
    activo_id: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    resultado = SoporteService.listar_consumos_formateados(db, empresa_id, insumo_id, activo_id)
    return {"items": resultado, "total": len(resultado)}


@router.post("/insumos-consumos")
async def registrar_consumo_insumo(
    datos: schemas.MovimientoInsumoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    try:
        return SoporteService.registrar_movimiento_insumo(db, empresa_id, datos.model_dump(), current_user.email)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al registrar consumo: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al registrar consumo")


@router.post("/insumos/{insumo_id}/cantidad")
@router.post("/activos/{insumo_id}/cantidad")
async def actualizar_cantidad_insumo(
    insumo_id: str,
    incremento: int = Query(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Alias para actualización rápida de stock (HTMX) vía movimientos."""
    tipo = "ingreso" if incremento > 0 else "consumo"
    datos = {
        "insumo_id": insumo_id,
        "tipo": tipo,
        "cantidad": abs(incremento),
        "motivo": "Actualización rápida desde UI",
    }
    try:
        return SoporteService.registrar_movimiento_insumo(db, empresa_id, datos, current_user.email)
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(422, "Referencia inválida: insumo_id no existe")
    except Exception as e:
        logger.error(f"Error al actualizar cantidad: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar cantidad")


# ─── Configuraciones y Maestras ────────────────────────────────────


@router.get("/marcas", response_model=schemas.MarcaListResponse)
async def listar_marcas(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    return SoporteService.listar_marcas(db, empresa_id)


@router.get("/marcas/buscar")
async def buscar_marcas(
    q: str = Query("", description="Búsqueda por nombre de marca"),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Busca marcas para autocomplete (mínimo 1 carácter)."""
    if not q or len(q.strip()) < 1:
        return []

    from backend.modules.soporte.models import SoporteActivosMarca

    search_term = f"%{q.strip()}%"
    marcas = (
        db.query(SoporteActivosMarca)
        .filter(SoporteActivosMarca.empresa_id == empresa_id, SoporteActivosMarca.nombre.ilike(search_term))
        .order_by(SoporteActivosMarca.nombre)
        .limit(20)
        .all()
    )

    return [{"id": str(m.id), "nombre": m.nombre} for m in marcas]


@router.post("/marcas", response_model=schemas.MarcaResponse, status_code=201)
async def crear_marca(
    nombre: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Crea una nueva marca de activo."""
    try:
        if not nombre or not nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre de la marca es obligatorio")

        marca = SoporteService.crear_marca(db, empresa_id, nombre.strip(), current_user.email)
        return marca
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Ya existe una marca con el nombre '{nombre}'")
    except Exception as e:
        logger.error(f"Error al crear marca: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear marca")


@router.put("/marcas/{marca_id}", response_model=schemas.MarcaResponse)
async def actualizar_marca(
    marca_id: str,
    nombre: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Actualiza una marca existente."""
    try:
        marca = SoporteService.actualizar_marca(db, empresa_id, marca_id, {"nombre": nombre}, current_user.email)
        if not marca:
            raise HTTPException(status_code=404, detail="Marca no encontrada")
        return marca
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al actualizar marca: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar marca")


@router.delete("/marcas/{marca_id}")
async def eliminar_marca(
    marca_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Elimina una marca si no está en uso."""
    try:
        if not SoporteService.eliminar_marca(db, empresa_id, marca_id):
            raise HTTPException(status_code=404, detail="Marca no encontrada")
        return {"status": "ok", "message": "Marca eliminada exitosamente"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error al eliminar marca: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al eliminar marca")


@router.post("/marcas/seed")
async def ejecutar_seed_marcas(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Ejecuta el seed de marcas para la empresa actual (solo admin)."""
    if current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden ejecutar el seed")

    try:
        from backend.modules.soporte.seed_data import seed_marcas

        stats = seed_marcas(db, empresa_id, current_user.email)
        return {
            "status": "ok",
            "message": f"Seed completado: {stats['creadas']} marcas creadas, {stats['existentes']} ya existían",
            "stats": stats,
        }
    except Exception as e:
        logger.error(f"Error ejecutando seed de marcas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al ejecutar seed: {str(e)}")


@router.get("/tipos-activos", response_model=schemas.ActivoTipoListResponse)
async def listar_tipos_activos(
    activos_solo: bool = Query(False),
    por_pagina: int = Query(100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    return SoporteService.listar_tipos_activos(db, empresa_id, activos_solo=activos_solo)


@router.post("/tipos-activos", response_model=schemas.ActivoTipoResponse)
async def crear_tipo_activo(
    datos: schemas.ActivoTipoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = require_stock,
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
):
    return SoporteService.crear_tipo_activo(db, datos.model_dump(), current_user.email, empresa_id)


@router.delete("/tipos-activos/{tipo_id}")
async def eliminar_tipo_activo(
    tipo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Elimina (soft delete) un tipo de activo si no tiene activos vinculados."""
    try:
        if not SoporteService.eliminar_tipo_activo(db, tipo_id, empresa_id):
            raise HTTPException(status_code=404, detail="Tipo de activo no encontrado")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ─── Categorías y Subcategorías ────────────────────────────────────


@router.get("/mis-dispositivos")
async def mis_dispositivos(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Lista de dispositivos asignados al usuario actual v28.0."""
    if not current_user.dni:
        return {"dispositivos": []}
    empleado = EmpleadoService.obtener_por_dni(db, empresa_id, current_user.dni)
    if not empleado:
        return {"dispositivos": []}
    activos = SoporteService.listar_activos(db, empresa_id, asignado_id=str(empleado.id))
    return {"dispositivos": [schemas.ActivoResponse.model_validate(a) for a in activos]}


@router.get("/categorias")
async def listar_categorias(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Lista TODAS las categorías SIN filtrar (para visualización en Kanban y panel de gestión).
    Incluye categorías sin subcategorías para permitir su administración."""
    categorias = SoporteService.listar_categorias(
        db, empresa_id=empresa_id, usuario_dni=None, es_admin=True, incluir_vacias=True
    )
    return {"categorias": categorias}


@router.get("/categorias-disponibles")
async def listar_categorias_disponibles(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Lista categorías disponibles para crear tickets (CON filtro de permisos)."""
    es_admin = current_user.rol == "admin"
    usuario_dni = current_user.dni
    categorias = SoporteService.listar_categorias(db, empresa_id=empresa_id, usuario_dni=usuario_dni, es_admin=es_admin)
    return {"categorias": categorias}


@router.post("/categorias")
async def crear_categoria_endpoint(
    datos: schemas.CategoriaCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    try:
        resultado = SoporteService.crear_categoria(db, empresa_id, datos.model_dump(), current_user.email)
        return {
            "id": str(resultado.id),
            "nombre": resultado.nombre_display,
            "tipo_ticket_asociado": resultado.tipo_ticket_asociado,
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Error al crear categoría: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al crear categoría")


@router.put("/categorias/{categoria_id}")
async def actualizar_categoria_endpoint(
    categoria_id: str,
    datos: schemas.CategoriaUpdate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    try:
        resultado = SoporteService.actualizar_categoria(
            db, empresa_id, categoria_id, datos.model_dump(exclude_unset=True), current_user.email
        )
        return {
            "id": str(resultado.id),
            "nombre": resultado.nombre_display,
            "tipo_ticket_asociado": resultado.tipo_ticket_asociado,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error al actualizar categoría: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al actualizar categoría")


@router.delete("/categorias/{categoria_id}")
async def eliminar_categoria_endpoint(
    categoria_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    if not SoporteService.eliminar_categoria(db, empresa_id, categoria_id):
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return {"status": "ok"}


@router.get("/estados-maestros")
async def listar_estados(db: Session = Depends(get_db), current_user: Usuario = require_mis_solicitudes):
    return SoporteService.listar_estados(db)


@router.get("/valores-matriz")
async def listar_valores_matriz(db: Session = Depends(get_db), current_user: Usuario = require_stock):
    """Lista los valores permitidos para la matriz de estado."""
    return SoporteService.listar_valores_matriz(db)


@router.get("/tipos-ticket")
async def listar_tipos_ticket(current_user: Usuario = require_mis_solicitudes):
    """Lista los tipos de ticket disponibles (clave, label, color).

    Fuente: enum TipoTicket (backend/modules/soporte/constants.py).
    """
    return {"tipos": SoporteService.listar_tipos_ticket()}


@router.get("/usuarios-lista")
async def listar_usuarios_soporte(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Lista usuarios para asignar tickets."""
    return SoporteService.listar_usuarios_asignacion(db, empresa_id)


@router.get("/empleados-lista")
async def get_empleados_lista(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Lista de empleados activos para select simples v28.0."""
    empleados = EmpleadoService.listar_para_select(db, empresa_id)
    return {
        "empleados": [{"id": str(e.id), "nombre": f"{e.apellido}, {e.nombre}", "codigo": e.codigo} for e in empleados]
    }


@router.get("/tecnicos-soporte")
async def get_tecnicos_soporte(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_tickets,
):
    """Lista de empleados del departamento de Soporte IT para asignar a tickets."""
    from backend.modules.nomina.models import Departamento, Empleado

    # Buscar el departamento de Soporte IT
    depto_soporte = (
        db.query(Departamento)
        .filter(
            Departamento.nombre == "Soporte IT",
            Departamento.empresa_id == empresa_id,
            Departamento.deleted_at.is_(None),
        )
        .first()
    )

    if not depto_soporte:
        return []

    # Obtener empleados activos de ese departamento
    tecnicos = (
        db.query(Empleado)
        .filter(
            Empleado.departamento_id == depto_soporte.id,
            Empleado.empresa_id == empresa_id,
            Empleado.activo == True,
            Empleado.deleted_at.is_(None),
        )
        .order_by(Empleado.apellido, Empleado.nombre)
        .all()
    )

    return [{"id": str(e.id), "nombre": f"{e.apellido}, {e.nombre}"} for e in tecnicos]


@router.get("/buscar-empleado")
async def buscar_empleado(
    q: str = Query(None),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_solicitudes,
):
    """Buscador de empleados para selects (asignación de técnico, colaborador en alta/baja, etc.)."""
    # Validación en backend: mínimo 2 caracteres
    if not q or len(q.strip()) < 2:
        return {"items": []}

    empleados = EmpleadoService.listar_para_select(db, empresa_id, buscar=q.strip())
    return {"items": [{"id": str(e.id), "nombre": f"{e.apellido}, {e.nombre}", "codigo": e.codigo} for e in empleados]}


@router.get("/activos/{activo_id}/historial", response_model=List[schemas.HistorialActivoResponse])
async def historial_activo(
    activo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    return SoporteService.obtener_historial_activo(db, empresa_id, activo_id)


@router.post("/historial", response_model=schemas.HistorialActivoResponse)
async def registrar_evento_tecnico(
    datos: schemas.HistorialActivoCreate,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_stock,
):
    """Registra un evento técnico con auditoría de estado físico."""
    try:
        historial = SoporteService.registrar_evento_tecnico(
            db, empresa_id, datos.model_dump(), current_user.dni, current_user.email
        )
        return historial
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error al registrar evento técnico: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error inesperado al registrar evento técnico")
