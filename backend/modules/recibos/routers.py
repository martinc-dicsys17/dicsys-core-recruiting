"""
Routers para el módulo de Recibos de Sueldo.

- router (admin): CRUD de lotes, listado de recibos, reprocesamiento
- public_router (empleado): mis recibos, descarga, firma de duplicado
"""

import hashlib
import logging
import re
import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.storage import cloud_storage
from backend.database import get_db
from backend.dependencies import get_empresa_activa, get_empresa_cuit, require_submodulo
from backend.modules.nomina.models import Empleado
from backend.modules.recibos.pdf_service import PDFService, carpeta_lote
from backend.modules.recibos.schemas import (
    LoteReciboList,
    LoteReciboResponse,
    ReciboList,
    ReciboLogResponse,
    ReciboResponse,
)
from backend.modules.recibos.services import LoteReciboService, ReciboLogService, ReciboService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/recibos", tags=["Recibos de Sueldo"])
public_router = APIRouter(prefix="/recibos", tags=["Recibos de Sueldo - Portal"])
nomina_router = APIRouter(prefix="/recibos", tags=["Recibos de Sueldo - Nómina"])

# Shortcuts de submódulo
require_mis_recibos = Depends(require_submodulo("recibos", "mis_recibos"))
require_recibos_nomina = Depends(require_submodulo("nomina", "empleados"))

logger = logging.getLogger(__name__)


def _get_recibos_allowed_emails() -> list[str]:
    """Parsea la whitelist de emails permitidos para admin de recibos."""
    raw = settings.recibos_admin_allowed_emails
    if not raw.strip():
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


async def require_recibos_admin(
    current_user: Usuario = Depends(require_submodulo("admin_contable", "recibos")),
) -> Usuario:
    """
    Verifica acceso al módulo admin de recibos.
    Doble check: primero el permiso normal (admin_contable.recibos),
    luego el email debe estar en RECIBOS_ADMIN_ALLOWED_EMAILS.
    No hay bypass por rol admin — el whitelist es obligatorio para todos.
    """
    allowed = _get_recibos_allowed_emails()
    if not allowed:
        raise HTTPException(status_code=403, detail="Módulo de recibos no configurado (whitelist vacía)")

    email = (current_user.email or "").lower()
    if email not in allowed:
        raise HTTPException(status_code=403, detail="No tenés acceso al módulo de administración de recibos")

    return current_user


require_admin_recibos = Depends(require_recibos_admin)

# Configuración de archivos
PDF_MAX_SIZE = 50 * 1024 * 1024  # 50MB para PDF masivo
FIRMADO_MAX_SIZE = 10 * 1024 * 1024  # 10MB para duplicado firmado


def _content_disposition(filename: Optional[str], fallback: str = "recibo.pdf") -> str:
    """Genera un header Content-Disposition seguro (RFC 5987).

    Sanitiza CR/LF y comillas dobles del nombre para evitar header injection
    cuando el nombre viene de input del usuario (ej: nombre del PDF subido).
    """
    name = filename or fallback
    safe_ascii = re.sub(r'[\r\n"\\]', "_", name)
    return f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{quote(name, safe='')}"


# ─── Admin: Lotes ─────────────────────────────────────────────────────────────


@router.post("/lotes", response_model=LoteReciboResponse, status_code=201)
async def subir_pdf_masivo(
    archivo: UploadFile = File(...),
    periodo: str = Form(...),
    tipo_liquidacion: str = Form(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user=require_admin_recibos,
):
    """Sube un PDF masivo y crea un lote de recibos."""
    try:
        # Validar archivo PDF
        content = await archivo.read()
        PDFService.validar_archivo_pdf(archivo.content_type, len(content), PDF_MAX_SIZE)

        # Validar periodo formato YYYY-MM
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", periodo):
            raise HTTPException(422, "El período debe tener formato YYYY-MM (ej: 2024-06)")

        if not tipo_liquidacion or not tipo_liquidacion.strip():
            raise HTTPException(422, "Tipo de liquidación es obligatorio")
        tipo_liquidacion = tipo_liquidacion.strip()

        # Un segundo lote activo del mismo período y tipo escribiría en la misma
        # carpeta y pisaría los PDF del primero. Se valida antes de subir el
        # masivo para no dejar un archivo huérfano en el storage.
        duplicado = LoteReciboService.buscar_activo(db, empresa_id, periodo, tipo_liquidacion)
        if duplicado:
            raise HTTPException(
                409,
                f"Ya existe un lote activo de '{duplicado.tipo_liquidacion}' para el "
                f"período {periodo} (id {duplicado.id}). Eliminá ese lote antes de "
                f"subir uno nuevo.",
            )

        # Subir PDF masivo al storage
        folder = carpeta_lote(empresa_cuit, periodo, tipo_liquidacion)
        masivo_key = cloud_storage.build_key(folder, content, ext=".pdf", prefix="masivo")
        cloud_storage.upload(masivo_key, content, "application/pdf")

        # Crear lote en estado pendiente
        lote = LoteReciboService.crear(
            db=db,
            empresa_id=empresa_id,
            datos={"periodo": periodo, "tipo_liquidacion": tipo_liquidacion},
            archivo_original_path=masivo_key,
            archivo_nombre=archivo.filename or "sin_nombre.pdf",
            usuario=None,
        )

        # Procesar PDF masivo
        resultado = PDFService.procesar_pdf_masivo(
            pdf_bytes=content,
            empresa_id=str(empresa_id),
            empresa_cuit=empresa_cuit,
            periodo=periodo,
            tipo_liquidacion=tipo_liquidacion,
            lote_id=str(lote.id),
            db=db,
        )

        # Actualizar estado del lote
        LoteReciboService.actualizar_estado(db, lote, resultado)

        return LoteReciboResponse.model_validate(lote)

    except ValueError as e:
        raise HTTPException(409, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al subir PDF masivo: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al procesar el PDF masivo")


@router.get("/lotes", response_model=LoteReciboList)
async def listar_lotes(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    periodo: Optional[str] = None,
    estado: Optional[str] = None,
    tipo_liquidacion: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_recibos,
):
    """Lista lotes paginados con filtros opcionales."""
    filtros = {}
    if periodo:
        filtros["periodo"] = periodo
    if estado:
        filtros["estado"] = estado
    if tipo_liquidacion:
        filtros["tipo_liquidacion"] = tipo_liquidacion

    resultado = LoteReciboService.listar(db, empresa_id, pagina, por_pagina, filtros)
    from sqlalchemy import func

    from backend.modules.recibos.models import Recibo

    lote_ids = [lote.id for lote in resultado["items"]]
    firmados_map = {}
    if lote_ids:
        rows = (
            db.query(Recibo.lote_id, func.count(Recibo.id))
            .filter(
                Recibo.lote_id.in_(lote_ids),
                Recibo.empresa_id == empresa_id,
                Recibo.deleted_at.is_(None),
                Recibo.estado == "firmado",
            )
            .group_by(Recibo.lote_id)
            .all()
        )
        firmados_map = {lid: cnt for lid, cnt in rows}
    items = []
    for lote in resultado["items"]:
        resp = LoteReciboResponse.model_validate(lote)
        resp.total_firmados = firmados_map.get(lote.id, 0)
        items.append(resp)
    return LoteReciboList(
        items=items,
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/lotes/{id}", response_model=LoteReciboResponse)
async def obtener_lote(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_recibos,
):
    """Obtiene el detalle de un lote con errores."""
    lote = LoteReciboService.obtener(db, empresa_id, id)
    if not lote:
        raise HTTPException(404, "Lote no encontrado")
    from backend.modules.recibos.models import Recibo

    total_firmados = (
        db.query(Recibo)
        .filter(
            Recibo.lote_id == lote.id,
            Recibo.empresa_id == empresa_id,
            Recibo.deleted_at.is_(None),
            Recibo.estado == "firmado",
        )
        .count()
    )
    response = LoteReciboResponse.model_validate(lote)
    response.total_firmados = total_firmados
    # Los avisos de 'sin empleado en nómina' dejan de aplicar si el empleado se
    # dio de alta después de cargar el lote. Se revalidan al leer.
    response.errores_detalle = LoteReciboService.avisos_vigentes(db, empresa_id, lote)
    return response


@router.delete("/lotes/{id}")
async def eliminar_lote(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_recibos,
):
    """Soft delete de un lote y todos sus recibos."""
    if not LoteReciboService.eliminar(db, empresa_id, id):
        raise HTTPException(404, "Lote no encontrado")
    return {"message": "Lote eliminado"}


@router.get("/lotes/{id}/descargar-pdf")
async def descargar_pdf_lote(
    id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_recibos,
):
    """Descarga el PDF masivo original del lote."""
    lote = LoteReciboService.obtener(db, empresa_id, id)
    if not lote:
        raise HTTPException(404, "Lote no encontrado")

    try:
        content = cloud_storage.download(lote.archivo_original)
    except FileNotFoundError:
        raise HTTPException(404, "El archivo PDF original no se encuentra disponible")

    # Auditoría: registrar descarga del PDF masivo (datos sensibles)
    ip = request.client.host if request and request.client else None
    logger.info(
        "[RECIBOS_AUDIT] descarga_lote lote_id=%s empresa_id=%s usuario=%s ip=%s archivo=%s",
        id,
        empresa_id,
        current_user.email,
        ip,
        lote.archivo_nombre,
    )

    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(lote.archivo_nombre)},
    )


@router.post("/lotes/{id}/reprocesar", response_model=LoteReciboResponse)
async def reprocesar_lote(
    id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user=require_admin_recibos,
):
    """Reprocesa un lote leyendo el PDF original desde cloud_storage."""
    try:
        lote = LoteReciboService.obtener(db, empresa_id, id)
        if not lote:
            raise HTTPException(404, "Lote no encontrado")

        # Leer PDF original desde storage
        try:
            pdf_bytes = cloud_storage.download(lote.archivo_original)
        except FileNotFoundError:
            raise HTTPException(404, "El archivo PDF original no se encuentra en storage")

        lote = LoteReciboService.reprocesar(db, empresa_id, id, pdf_bytes, empresa_cuit)
        return LoteReciboResponse.model_validate(lote)

    except ValueError as e:
        raise HTTPException(409, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al reprocesar lote: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al reprocesar el lote")


@router.post("/lotes/{id}/actualizar")
async def actualizar_recibos_lote(
    id: str,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user=require_admin_recibos,
):
    """
    Actualiza recibos específicos de un lote a partir de un PDF parcial.

    El PDF debe contener los recibos a actualizar con el mismo formato que el
    PDF masivo original (pares duplicado→original por CUIL). Por cada CUIL
    detectado, se eliminan los recibos previos del lote (junto con su historial
    de actividades) y se cargan los nuevos.
    """
    try:
        content = await archivo.read()
        PDFService.validar_archivo_pdf(archivo.content_type, len(content), PDF_MAX_SIZE)

        resultado = LoteReciboService.actualizar_recibos(
            db=db,
            empresa_id=empresa_id,
            id=id,
            pdf_bytes=content,
            empresa_cuit=empresa_cuit,
        )

        lote_resp = LoteReciboResponse.model_validate(resultado["lote"])
        return {
            "lote": lote_resp.model_dump(),
            "cuils_actualizados": [str(c) for c in resultado["cuils_actualizados"]],
            "recibos_eliminados": resultado["recibos_eliminados"],
            "recibos_creados": len(resultado["recibos_creados"]),
        }

    except ValueError as e:
        raise HTTPException(409, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al actualizar recibos del lote: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al actualizar los recibos del lote")


@router.get("/lotes/{id}/recibos", response_model=ReciboList)
async def listar_recibos_lote(
    id: str,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    buscar: Optional[str] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user=require_admin_recibos,
):
    """Lista recibos de un lote paginados con búsqueda opcional."""
    lote = LoteReciboService.obtener(db, empresa_id, id)
    if not lote:
        raise HTTPException(404, "Lote no encontrado")

    resultado = ReciboService.listar_por_lote(db, empresa_id, id, pagina, por_pagina, buscar=buscar, estado=estado)
    return ReciboList(
        items=[
            ReciboResponse.from_model(i["recibo"], empleado_nombre_override=i.get("empleado_nombre"))
            for i in resultado["items"]
        ],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


# ─── Nómina: Recibos por empleado ──────────────────────────────────


@nomina_router.get("/empleado/{empleado_id}", response_model=ReciboList)
async def listar_recibos_empleado(
    empleado_id: str,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_recibos_nomina,
):
    """Lista recibos de un empleado (vista nómina, requiere `nomina.empleados`)."""
    resultado = ReciboService.listar_por_empleado(db, empresa_id, empleado_id, pagina, por_pagina)
    return ReciboList(
        items=[
            ReciboResponse.from_model(i["recibo"], empleado_nombre_override=i.get("empleado_nombre"))
            for i in resultado["items"]
        ],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


# ─── Público: Mis Recibos ─────────────────────────────────────────────────────


@public_router.get("/mis-recibos", response_model=ReciboList)
async def mis_recibos(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_recibos,
):
    """Lista recibos del empleado autenticado (busca por DNI → CUIL)."""
    if not current_user.dni:
        raise HTTPException(404, "No se encontró un empleado asociado a tu cuenta")

    # Buscar empleado por DNI para obtener su CUIL
    empleado = (
        db.query(Empleado)
        .filter(
            Empleado.dni == current_user.dni,
            Empleado.empresa_id == empresa_id,
            Empleado.deleted_at.is_(None),
        )
        .first()
    )

    if empleado:
        resultado = ReciboService.listar_por_empleado(db, empresa_id, str(empleado.id), pagina, por_pagina)
    else:
        # Si no hay empleado en nómina, buscar recibos directamente por CUIL del usuario
        # (el CUIL se puede derivar del DNI pero no siempre, así que retornamos vacío)
        resultado = {"items": [], "total": 0, "pagina": pagina, "por_pagina": por_pagina, "total_paginas": 1}
    return ReciboList(
        items=[
            ReciboResponse.from_model(i["recibo"], empleado_nombre_override=i.get("empleado_nombre"))
            for i in resultado["items"]
        ],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


# ─── Admin: Descargar recibo individual ──────────────────────────────────────


@router.get("/admin/descargar/{recibo_id}/{tipo}")
async def descargar_recibo_admin(
    recibo_id: str,
    tipo: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Descarga de recibo individual para el admin de recibos.

    No valida propiedad por DNI/CUIL: el admin de recibos
    (permiso `admin_contable.recibos` + whitelist `RECIBOS_ADMIN_ALLOWED_EMAILS`)
    puede descargar cualquier recibo de su empresa.
    """
    if tipo not in ("original", "duplicado", "firmado"):
        raise HTTPException(400, "Tipo debe ser 'original', 'duplicado' o 'firmado'")

    recibo = ReciboService.obtener(db, empresa_id, recibo_id)
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado")

    if tipo == "original":
        archivo_key = recibo.archivo_original
    elif tipo == "duplicado":
        # El duplicado es opcional: hay recibos que vienen en una sola hoja.
        if not recibo.archivo_duplicado:
            raise HTTPException(400, "Este recibo no tiene duplicado: viene en una sola hoja")
        archivo_key = recibo.archivo_duplicado
    else:  # firmado
        if not recibo.archivo_firmado:
            raise HTTPException(404, "El recibo no tiene un duplicado firmado")
        archivo_key = recibo.archivo_firmado

    try:
        content = cloud_storage.download(archivo_key)
    except FileNotFoundError:
        raise HTTPException(404, "El archivo del recibo no se encuentra disponible")

    ReciboLogService.registrar(
        db,
        recibo.id,
        empresa_id,
        accion=f"descarga_admin_{tipo}",
        usuario_email=current_user.email,
        usuario_nombre=f"{current_user.nombre} {current_user.apellido or ''}".strip(),
        ip=request.client.host if request and request.client else None,
        detalle=f"Descarga admin de {tipo}",
    )
    db.commit()

    filename = archivo_key.split("/")[-1]
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# ─── Público: Descargar PDF ───────────────────────────────────────────────────


@public_router.get("/descargar/{recibo_id}/{tipo}")
async def descargar_recibo(
    recibo_id: str,
    tipo: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_recibos,
):
    """Descarga de recibo del portal del empleado.

    Siempre exige que el recibo pertenezca al usuario autenticado
    (DNI → Empleado → CUIL == recibo.cuil_extraido). No hay bypass por rol admin:
    para descargar recibos ajenos se debe usar el endpoint admin con whitelist.
    """
    if tipo not in ("original", "duplicado", "firmado"):
        raise HTTPException(400, "Tipo debe ser 'original', 'duplicado' o 'firmado'")

    recibo = ReciboService.obtener(db, empresa_id, recibo_id)
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado")

    # Validar propiedad del recibo (siempre, sin bypass por rol admin)
    if not current_user.dni:
        raise HTTPException(403, "No tenés acceso a este recibo")

    empleado = (
        db.query(Empleado)
        .filter(
            Empleado.dni == current_user.dni,
            Empleado.empresa_id == empresa_id,
            Empleado.deleted_at.is_(None),
        )
        .first()
    )

    if not empleado or not empleado.cuil or recibo.cuil_extraido != empleado.cuil:
        raise HTTPException(403, "No tenés acceso a este recibo")

    # Determinar key del archivo
    if tipo == "original":
        archivo_key = recibo.archivo_original
    elif tipo == "duplicado":
        # El duplicado es opcional: hay recibos que vienen en una sola hoja.
        if not recibo.archivo_duplicado:
            raise HTTPException(400, "Este recibo no tiene duplicado: viene en una sola hoja")
        archivo_key = recibo.archivo_duplicado
    else:  # firmado
        if not recibo.archivo_firmado:
            raise HTTPException(404, "El recibo no tiene un duplicado firmado")
        archivo_key = recibo.archivo_firmado

    try:
        content = cloud_storage.download(archivo_key)
    except FileNotFoundError:
        raise HTTPException(404, "El archivo del recibo no se encuentra disponible")

    # Registrar log de descarga
    ReciboLogService.registrar(
        db,
        recibo.id,
        empresa_id,
        accion=f"descarga_{tipo}",
        usuario_email=current_user.email,
        usuario_nombre=f"{current_user.nombre} {current_user.apellido or ''}".strip(),
        ip=request.client.host if request and request.client else None,
        detalle=f"Descarga de {tipo}",
    )
    db.commit()

    filename = archivo_key.split("/")[-1]
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


# ─── Público: Dónde estampar la firma ─────────────────────────────────────────


@public_router.get("/{recibo_id}/firma-posicion")
async def firma_posicion(
    recibo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_mis_recibos,
):
    """Coordenadas donde el front tiene que estampar la firma del empleado.

    En los recibos sin duplicado el bloque de firmas se corre verticalmente según
    la cantidad de conceptos, así que la posición se calcula leyendo
    el PDF en vez de hardcodearla. Devuelve `posicion: null` para los recibos
    con duplicado, cuyo pie sí está a una altura fija.
    """
    recibo = ReciboService.obtener(db, empresa_id, recibo_id)
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado")

    # Misma validación de propiedad que la descarga: sin bypass por rol admin.
    if not current_user.dni:
        raise HTTPException(403, "No tenés acceso a este recibo")

    empleado = (
        db.query(Empleado)
        .filter(
            Empleado.dni == current_user.dni,
            Empleado.empresa_id == empresa_id,
            Empleado.deleted_at.is_(None),
        )
        .first()
    )

    if not empleado or not empleado.cuil or recibo.cuil_extraido != empleado.cuil:
        raise HTTPException(403, "No tenés acceso a este recibo")

    archivo_key = recibo.archivo_duplicado or recibo.archivo_original
    try:
        content = cloud_storage.download(archivo_key)
    except FileNotFoundError:
        raise HTTPException(404, "El archivo del recibo no se encuentra disponible")

    try:
        posicion = PDFService.calcular_posicion_firma(content)
    except Exception as e:
        # No romper la firma por esto: el front cae a su posición por defecto.
        logger.warning(f"No se pudo calcular la posición de firma de {recibo_id}: {e}")
        posicion = None

    nombre = f"{empleado.apellido}, {empleado.nombre}" if empleado.apellido else empleado.nombre
    return {"posicion": posicion, "empleado_nombre": nombre}


# ─── Público: Firmar duplicado ────────────────────────────────────────────────


@public_router.post("/{recibo_id}/firmar", response_model=ReciboResponse)
async def firmar_recibo(
    recibo_id: str,
    archivo: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    empresa_cuit: str = Depends(get_empresa_cuit),
    current_user: Usuario = require_mis_recibos,
):
    """Sube un duplicado firmado por el empleado."""
    try:
        # Validar archivo PDF
        content = await archivo.read()
        PDFService.validar_archivo_pdf(archivo.content_type, len(content), FIRMADO_MAX_SIZE)

        recibo = ReciboService.obtener(db, empresa_id, recibo_id)
        if not recibo:
            raise HTTPException(404, "Recibo no encontrado")

        # Validar que el empleado sea dueño del recibo
        if not current_user.dni:
            raise HTTPException(403, "No tenés acceso a este recibo")

        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.dni == current_user.dni,
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .first()
        )

        if not empleado or not empleado.cuil or recibo.cuil_extraido != empleado.cuil:
            raise HTTPException(403, "No tenés acceso a este recibo")

        # Obtener lote para el periodo
        lote = recibo.lote_rel

        # Subir archivo firmado al storage
        folder = f"{carpeta_lote(empresa_cuit, lote.periodo, lote.tipo_liquidacion)}/firmados"
        file_hash = hashlib.sha256(content).hexdigest()[:16]
        unique_id = uuid.uuid4().hex[:8]
        firmado_key = f"{folder}/{recibo_id}_{file_hash}_{unique_id}.pdf"
        cloud_storage.upload(firmado_key, content, "application/pdf")

        # Actualizar recibo
        recibo_actualizado = ReciboService.firmar(
            db=db,
            empresa_id=empresa_id,
            recibo_id=recibo_id,
            archivo_firmado_path=firmado_key,
            usuario=current_user.email,
            ip_firma=request.client.host if request and request.client else None,
        )

        if not recibo_actualizado:
            raise HTTPException(404, "Recibo no encontrado")

        # Registrar log de firma
        ReciboLogService.registrar(
            db,
            recibo.id,
            empresa_id,
            accion="firma",
            usuario_email=current_user.email,
            usuario_nombre=f"{current_user.nombre} {current_user.apellido or ''}".strip(),
            ip=request.client.host if request and request.client else None,
            detalle="Firma del duplicado",
        )
        db.commit()

        return ReciboResponse.from_model(recibo_actualizado)

    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al firmar recibo: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al firmar el recibo")


# ─── Admin: Logs y reversión de firma ─────────────────────────────────────────


@router.get("/admin/recibos/{recibo_id}/logs", response_model=list[ReciboLogResponse])
async def listar_logs_recibo_admin(
    recibo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Lista los logs de actividad de un recibo (vista admin de recibos)."""
    logs = ReciboLogService.listar(db, empresa_id, recibo_id)
    return [ReciboLogResponse.model_validate(log) for log in logs]


@router.post("/admin/recibos/{recibo_id}/revertir-firma")
async def revertir_firma_recibo_admin(
    recibo_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Revierte la firma de un recibo (vista admin de recibos)."""
    recibo = ReciboService.revertir_firma(db, empresa_id, recibo_id, usuario=current_user.email)
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado")

    ReciboLogService.registrar(
        db,
        recibo.id,
        empresa_id,
        accion="reversion_firma",
        usuario_email=current_user.email,
        usuario_nombre=f"{current_user.nombre} {current_user.apellido or ''}".strip(),
        ip=request.client.host if request and request.client else None,
        detalle="Reversión de firma desde admin de recibos",
    )
    db.commit()
    return {"message": "Firma revertida"}


# ─── Nómina: Logs y reversión de firma ────────────────────────────────────────


@nomina_router.get("/nomina/recibos/{recibo_id}/logs", response_model=list[ReciboLogResponse])
async def listar_logs_recibo_nomina(
    recibo_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_recibos_nomina,
):
    """Lista los logs de actividad de un recibo (vista nómina, requiere `nomina.empleados`)."""
    logs = ReciboLogService.listar(db, empresa_id, recibo_id)
    return [ReciboLogResponse.model_validate(log) for log in logs]


@nomina_router.post("/nomina/recibos/{recibo_id}/revertir-firma")
async def revertir_firma_recibo_nomina(
    recibo_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_recibos_nomina,
):
    """Revierte la firma de un recibo (vista nómina, requiere `nomina.empleados`)."""
    recibo = ReciboService.revertir_firma(db, empresa_id, recibo_id, usuario=current_user.email)
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado")

    ReciboLogService.registrar(
        db,
        recibo.id,
        empresa_id,
        accion="reversion_firma",
        usuario_email=current_user.email,
        usuario_nombre=f"{current_user.nombre} {current_user.apellido or ''}".strip(),
        ip=request.client.host if request and request.client else None,
        detalle="Reversión de firma desde nómina (vista de empleado)",
    )
    db.commit()
    return {"message": "Firma revertida"}
