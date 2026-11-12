"""
Routers del registro de proveedores (Administración → Proveedores).
Permiso: admin_contable.proveedores.
"""

import logging
import uuid
from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.core.storage import cloud_storage
from backend.dependencies import get_db, get_empresa_activa, require_submodulo
from backend.modules.administracion import proveedores_adjuntos as adjuntos, proveedores_miniaturas as miniaturas
from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_comun import ReferenciaInvalida
from backend.modules.administracion.proveedores_schemas import (
    ContactoDatos,
    ContactoResponse,
    DocumentoResponse,
    EmpleadoOpcion,
    EvaluacionHistorial,
    OficinaDatos,
    OficinaResponse,
    ProveedorCreate,
    ProveedorDetalle,
    ProveedorList,
    ProveedorResponse,
    ProveedorUpdate,
)
from backend.modules.administracion.proveedores_services import (
    ContactoService,
    DatosIncompletos,
    DocumentoService,
    OficinaService,
    OperacionNoPermitida,
    ProveedorDuplicado,
    ProveedorRegistroService,
)
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/proveedores", tags=["Administración - Proveedores"])
logger = logging.getLogger(__name__)

require_proveedores = Depends(require_submodulo("admin_contable", "proveedores"))


def _error(exc: Exception, accion: str):
    """Traduce las excepciones del servicio a HTTP (404, 409, 422, 500)."""
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, ReferenciaInvalida):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DatosIncompletos):
        raise HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (ProveedorDuplicado, OperacionNoPermitida)):
        raise HTTPException(status_code=409, detail=str(exc))
    logger.error(f"Error al {accion}: {exc}", exc_info=True)
    raise HTTPException(status_code=500, detail=f"Error inesperado al {accion}")


def _detalle(db: Session, proveedor) -> ProveedorDetalle:
    return ProveedorDetalle(
        **ProveedorResponse.from_model(proveedor).model_dump(),
        oficinas=[OficinaResponse.from_model(o) for o in proveedor.oficinas],
        contactos=[ContactoResponse.from_model(c) for c in proveedor.contactos],
        documentos=[DocumentoResponse.from_model(d) for d in proveedor.documentos],
        historial=[EvaluacionHistorial(**h) for h in ProveedorRegistroService.historial(db, proveedor)],
    )


# ─── Registro ───────────────────────────────────────────────────────────────────


@router.get("", response_model=ProveedorList)
async def listar_proveedores(
    buscar: str = Query(""),
    tipo: str = Query(""),
    referente_id: str = Query(""),
    sin_referente: bool = Query(False),
    estado: str = Query("activos", pattern="^(activos|baja|todos)$"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Registro con métricas (activos, sin referente, de baja) y filtros."""
    resultado = ProveedorRegistroService.listar(
        db,
        empresa_id,
        buscar=buscar,
        tipo=tipo,
        referente_id=referente_id,
        sin_referente=sin_referente,
        estado=estado,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return ProveedorList(**{**resultado, "items": [ProveedorResponse.from_model(p) for p in resultado["items"]]})


@router.get("/empleados", response_model=List[EmpleadoOpcion])
async def buscar_empleados(
    buscar: str = Query(""),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Empleados activos de la nómina para elegir el usuario referente."""
    return [
        EmpleadoOpcion(id=str(e.id), nombre=f"{e.apellido}, {e.nombre}", email=e.email_corporativo)
        for e in ProveedorRegistroService.buscar_empleados(db, empresa_id, buscar)
    ]


@router.post("", response_model=ProveedorResponse, status_code=201)
async def crear_proveedor(
    datos: ProveedorCreate,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        proveedor = ProveedorRegistroService.crear(
            db, empresa_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return ProveedorResponse.from_model(proveedor)
    except Exception as exc:
        db.rollback()
        _error(exc, "crear el proveedor")


@router.post("/con-adjunto", response_model=ProveedorResponse, status_code=201)
async def crear_proveedor_con_adjunto(
    request: Request,
    datos: str = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """
    Alta con el adjunto del acuerdo en el mismo pedido (multipart: `datos` en JSON
    y `archivo`): con acuerdo firmado, el proveedor no existe sin su adjunto.
    """
    try:
        proveedor_datos = ProveedorCreate.model_validate_json(datos)
    except ValidationError as exc:
        # Mismo 422 que el alta JSON: los errores, como si vinieran del body
        raise RequestValidationError([{**e, "loc": ("body", *e["loc"])} for e in exc.errors()])
    clave, nombre = await _subir_adjunto(archivo, empresa_id)
    try:
        proveedor = ProveedorRegistroService.crear(
            db,
            empresa_id,
            proveedor_datos.model_dump(),
            Actor.desde_request(request, current_user),
            adjunto=(clave, nombre),
        )
    except Exception as exc:
        db.rollback()
        _borrar_del_storage(clave)
        _error(exc, "crear el proveedor")
    return ProveedorResponse.from_model(proveedor)


@router.get("/{proveedor_id}", response_model=ProveedorDetalle)
async def obtener_proveedor(
    proveedor_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Ficha: datos, oficinas, contactos e historial de evaluaciones."""
    try:
        return _detalle(db, ProveedorRegistroService.obtener(db, empresa_id, proveedor_id))
    except Exception as exc:
        _error(exc, "obtener el proveedor")


@router.put("/{proveedor_id}", response_model=ProveedorResponse)
async def actualizar_proveedor(
    proveedor_id: str,
    datos: ProveedorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        proveedor = ProveedorRegistroService.actualizar(
            db, empresa_id, proveedor_id, datos.model_dump(), Actor.desde_request(request, current_user)
        )
        return ProveedorResponse.from_model(proveedor)
    except Exception as exc:
        db.rollback()
        _error(exc, "actualizar el proveedor")


@router.post("/{proveedor_id}/baja", response_model=ProveedorResponse)
async def dar_de_baja_proveedor(
    proveedor_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return ProveedorResponse.from_model(
            ProveedorRegistroService.dar_de_baja(
                db, empresa_id, proveedor_id, Actor.desde_request(request, current_user)
            )
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "dar de baja el proveedor")


@router.post("/{proveedor_id}/reactivar", response_model=ProveedorResponse)
async def reactivar_proveedor(
    proveedor_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return ProveedorResponse.from_model(
            ProveedorRegistroService.reactivar(db, empresa_id, proveedor_id, Actor.desde_request(request, current_user))
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "reactivar el proveedor")


@router.delete("/{proveedor_id}")
async def eliminar_proveedor(
    proveedor_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Solo si nunca fue evaluado; si no, se pasa a inactivo."""
    try:
        ProveedorRegistroService.eliminar(db, empresa_id, proveedor_id, Actor.desde_request(request, current_user))
        return {"message": "Eliminado"}
    except Exception as exc:
        db.rollback()
        _error(exc, "eliminar el proveedor")


# ─── Adjunto de política/NDA ────────────────────────────────────────────────────


async def _subir_adjunto(archivo: UploadFile, empresa_id: uuid.UUID) -> tuple:
    """Valida el archivo (pdf, jpg, png, doc, docx; hasta 10 MB) y lo sube: (clave, nombre)."""
    contenido = await archivo.read(adjuntos.TAMANO_MAXIMO + 1)
    try:
        extension, tipo = adjuntos.validar(archivo.filename or "", contenido)
    except adjuntos.AdjuntoInvalido as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    clave = adjuntos.clave_storage(empresa_id, extension)
    try:
        cloud_storage.upload(clave, contenido, tipo)
    except Exception as exc:
        _error(exc, "subir el adjunto")
    return clave, (archivo.filename or f"nda{extension}")[:255]


def _borrar_del_storage(clave: str) -> None:
    try:
        cloud_storage.delete(clave)
    except Exception:  # noqa: BLE001 - no dejar el archivo huérfano es best-effort
        pass


@router.post("/{proveedor_id}/nda", response_model=ProveedorResponse)
async def subir_nda(
    proveedor_id: str,
    request: Request,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Sube o reemplaza el adjunto (pdf, jpg, png, doc, docx; hasta 10 MB)."""
    try:
        ProveedorRegistroService.obtener(db, empresa_id, proveedor_id)
    except Exception as exc:
        _error(exc, "subir el adjunto")
    clave, nombre = await _subir_adjunto(archivo, empresa_id)
    try:
        proveedor, anterior = ProveedorRegistroService.guardar_nda(
            db, empresa_id, proveedor_id, clave, nombre, Actor.desde_request(request, current_user)
        )
    except Exception as exc:
        db.rollback()
        _borrar_del_storage(clave)
        _error(exc, "subir el adjunto")
    if anterior:
        try:
            cloud_storage.delete(anterior)
        except Exception as exc:  # noqa: BLE001 - el adjunto nuevo ya quedó; el viejo es basura
            logger.warning(f"No se pudo borrar el adjunto anterior {anterior}: {exc}")
    return ProveedorResponse.from_model(proveedor)


@router.get("/{proveedor_id}/nda")
async def descargar_nda(
    proveedor_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        proveedor = ProveedorRegistroService.obtener(db, empresa_id, proveedor_id)
    except Exception as exc:
        _error(exc, "descargar el adjunto")
    if not proveedor.politica_nda_archivo:
        raise HTTPException(status_code=404, detail="El proveedor no tiene adjunto")
    try:
        contenido = cloud_storage.download(proveedor.politica_nda_archivo)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No se encontró el archivo")
    nombre = proveedor.politica_nda_archivo_nombre or "nda"
    return Response(
        content=contenido,
        media_type=adjuntos.tipo_por_nombre(proveedor.politica_nda_archivo),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{proveedor_id}/nda", response_model=ProveedorResponse)
async def quitar_nda(
    proveedor_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        anterior = ProveedorRegistroService.quitar_nda(
            db, empresa_id, proveedor_id, Actor.desde_request(request, current_user)
        )
        proveedor = ProveedorRegistroService.obtener(db, empresa_id, proveedor_id)
    except Exception as exc:
        db.rollback()
        _error(exc, "quitar el adjunto")
    if anterior:
        try:
            cloud_storage.delete(anterior)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"No se pudo borrar el adjunto {anterior}: {exc}")
    return ProveedorResponse.from_model(proveedor)


# ─── Documentos ─────────────────────────────────────────────────────────────────

MAXIMO_POR_SUBIDA = 20


def _descarga(contenido: bytes, tipo: str, nombre: str) -> Response:
    return Response(
        content=contenido,
        media_type=tipo,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(nombre)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{proveedor_id}/documentos", response_model=List[DocumentoResponse])
async def listar_documentos(
    proveedor_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        proveedor = ProveedorRegistroService.obtener(db, empresa_id, proveedor_id)
        return [DocumentoResponse.from_model(d) for d in proveedor.documentos]
    except Exception as exc:
        _error(exc, "listar los documentos")


@router.post("/{proveedor_id}/documentos", response_model=List[DocumentoResponse], status_code=201)
async def subir_documentos(
    proveedor_id: str,
    request: Request,
    archivos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """
    Sube uno o varios documentos (pdf, xlsx, png, jpg, jpeg, doc, docx; hasta 10 MB cada uno)
    con su miniatura. Todos o ninguno: si uno no es válido, el mensaje dice cuál y no se sube nada.
    """
    try:
        proveedor = ProveedorRegistroService.obtener(db, empresa_id, proveedor_id)
    except Exception as exc:
        _error(exc, "subir los documentos")
    if len(archivos) > MAXIMO_POR_SUBIDA:
        raise HTTPException(status_code=422, detail=f"Se pueden subir hasta {MAXIMO_POR_SUBIDA} documentos por vez")
    leidos = []
    for archivo in archivos:
        nombre = (archivo.filename or "documento")[:255]
        contenido = await archivo.read(adjuntos.TAMANO_MAXIMO + 1)
        try:
            extension, tipo = adjuntos.validar(nombre, contenido, adjuntos.EXTENSIONES_DOCUMENTOS)
        except adjuntos.AdjuntoInvalido as exc:
            raise HTTPException(status_code=422, detail=f"«{nombre}»: {exc}")
        leidos.append((nombre, contenido, extension, tipo))

    en_storage: List[str] = []  # para no dejar archivos huérfanos si algo falla
    try:
        subidos = []
        for nombre, contenido, extension, tipo in leidos:
            documento_id = uuid.uuid4()
            clave = adjuntos.clave_documento(empresa_id, proveedor.id, documento_id, extension)
            cloud_storage.upload(clave, contenido, tipo)
            en_storage.append(clave)
            # Renderizar es CPU: fuera del loop de eventos
            miniatura = await run_in_threadpool(miniaturas.generar, contenido, extension)
            clave_miniatura = None
            if miniatura:
                clave_miniatura = adjuntos.clave_miniatura(clave)
                cloud_storage.upload(clave_miniatura, miniatura, "image/png")
                en_storage.append(clave_miniatura)
            subidos.append(
                {
                    "id": documento_id,
                    "nombre": nombre,
                    "clave": clave,
                    "tipo_mime": tipo,
                    "tamano": len(contenido),
                    "miniatura_clave": clave_miniatura,
                }
            )
        documentos = DocumentoService.registrar_subidos(
            db, empresa_id, proveedor, subidos, Actor.desde_request(request, current_user)
        )
    except Exception as exc:
        db.rollback()
        for clave in en_storage:
            _borrar_del_storage(clave)
        _error(exc, "subir los documentos")
    return [DocumentoResponse.from_model(d) for d in documentos]


@router.get("/{proveedor_id}/documentos/{documento_id}")
async def descargar_documento(
    proveedor_id: str,
    documento_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """Se descarga con su nombre original."""
    try:
        documento = DocumentoService.obtener(db, empresa_id, proveedor_id, documento_id)
    except Exception as exc:
        _error(exc, "descargar el documento")
    try:
        contenido = cloud_storage.download(documento.clave)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No se encontró el archivo")
    return _descarga(contenido, documento.tipo_mime, documento.nombre)


@router.get("/{proveedor_id}/documentos/{documento_id}/miniatura")
async def miniatura_documento(
    proveedor_id: str,
    documento_id: str,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    """El PNG del thumbnail; 404 si no tiene (la pantalla muestra el ícono del tipo)."""
    try:
        documento = DocumentoService.obtener(db, empresa_id, proveedor_id, documento_id)
    except Exception as exc:
        _error(exc, "mostrar la miniatura")
    if not documento.miniatura_clave:
        raise HTTPException(status_code=404, detail="El documento no tiene miniatura")
    try:
        contenido = cloud_storage.download(documento.miniatura_clave)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="No se encontró la miniatura")
    # No cambia nunca (si se reemplaza el documento es otro id): el navegador la puede guardar
    return Response(
        content=contenido,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{proveedor_id}/documentos/{documento_id}")
async def eliminar_documento(
    proveedor_id: str,
    documento_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        claves = DocumentoService.eliminar(
            db, empresa_id, proveedor_id, documento_id, Actor.desde_request(request, current_user)
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "eliminar el documento")
    for clave in claves:
        try:
            cloud_storage.delete(clave)
        except Exception as exc:  # noqa: BLE001 - la baja ya quedó; el archivo es basura
            logger.warning(f"No se pudo borrar {clave} del storage: {exc}")
    return {"message": "Eliminado"}


# ─── Oficinas ───────────────────────────────────────────────────────────────────


@router.post("/{proveedor_id}/oficinas", response_model=OficinaResponse, status_code=201)
async def crear_oficina(
    proveedor_id: str,
    datos: OficinaDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return OficinaResponse.from_model(
            OficinaService.crear(
                db, empresa_id, proveedor_id, datos.model_dump(), Actor.desde_request(request, current_user)
            )
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "crear la oficina")


@router.put("/{proveedor_id}/oficinas/{oficina_id}", response_model=OficinaResponse)
async def actualizar_oficina(
    proveedor_id: str,
    oficina_id: str,
    datos: OficinaDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return OficinaResponse.from_model(
            OficinaService.actualizar(
                db, empresa_id, proveedor_id, oficina_id, datos.model_dump(), Actor.desde_request(request, current_user)
            )
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "actualizar la oficina")


@router.delete("/{proveedor_id}/oficinas/{oficina_id}")
async def eliminar_oficina(
    proveedor_id: str,
    oficina_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        OficinaService.eliminar(db, empresa_id, proveedor_id, oficina_id, Actor.desde_request(request, current_user))
        return {"message": "Eliminado"}
    except Exception as exc:
        db.rollback()
        _error(exc, "eliminar la oficina")


# ─── Contactos ──────────────────────────────────────────────────────────────────


@router.post("/{proveedor_id}/contactos", response_model=ContactoResponse, status_code=201)
async def crear_contacto(
    proveedor_id: str,
    datos: ContactoDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return ContactoResponse.from_model(
            ContactoService.crear(
                db, empresa_id, proveedor_id, datos.model_dump(), Actor.desde_request(request, current_user)
            )
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "crear el contacto")


@router.put("/{proveedor_id}/contactos/{contacto_id}", response_model=ContactoResponse)
async def actualizar_contacto(
    proveedor_id: str,
    contacto_id: str,
    datos: ContactoDatos,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        return ContactoResponse.from_model(
            ContactoService.actualizar(
                db,
                empresa_id,
                proveedor_id,
                contacto_id,
                datos.model_dump(),
                Actor.desde_request(request, current_user),
            )
        )
    except Exception as exc:
        db.rollback()
        _error(exc, "actualizar el contacto")


@router.delete("/{proveedor_id}/contactos/{contacto_id}")
async def eliminar_contacto(
    proveedor_id: str,
    contacto_id: str,
    request: Request,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_proveedores,
):
    try:
        ContactoService.eliminar(db, empresa_id, proveedor_id, contacto_id, Actor.desde_request(request, current_user))
        return {"message": "Eliminado"}
    except Exception as exc:
        db.rollback()
        _error(exc, "eliminar el contacto")
