"""
Router para exportar recibos de sueldo agrupados por cliente y mes.

Acceso: permiso `admin_contable.export_recibos` + email del usuario presente en
la whitelist RECIBOS_ADMIN_ALLOWED_EMAILS (misma whitelist que recibos).
"""

import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.database import get_db
from backend.dependencies import get_empresa_activa, require_submodulo
from backend.modules.administracion.export_recibos_services import ExportRecibosService
from backend.modules.usuarios.models import Usuario

router = APIRouter(prefix="/administracion/export-recibos", tags=["Administración - Export Recibos"])


def _get_recibos_allowed_emails() -> list[str]:
    raw = settings.recibos_admin_allowed_emails
    if not raw.strip():
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


async def require_export_recibos_admin(
    current_user: Usuario = Depends(require_submodulo("admin_contable", "export_recibos")),
) -> Usuario:
    """Doble check: permiso admin_contable.export_recibos + whitelist de emails."""
    allowed = _get_recibos_allowed_emails()
    if not allowed:
        raise HTTPException(status_code=403, detail="Módulo de export de recibos no configurado (whitelist vacía)")
    email = (current_user.email or "").lower()
    if email not in allowed:
        raise HTTPException(status_code=403, detail="No tenés acceso al módulo de exportación de recibos")
    return current_user


require_admin_recibos = Depends(require_export_recibos_admin)


@router.get("/preview")
async def preview_export(
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Devuelve estructura agrupada cliente -> periodo -> empleados -> recibos."""
    return ExportRecibosService.listar_agrupado(db, empresa_id)


@router.get("/descargar")
async def descargar_zip(
    cliente: str = Query(..., min_length=1, max_length=100),
    periodo: str = Query(..., min_length=7, max_length=7, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    tipo_liquidacion: Optional[str] = Query(None, min_length=1, max_length=50),
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Descarga ZIP con los recibos del (cliente, periodo, tipo_liquidacion).

    Sin `tipo_liquidacion` trae todas las liquidaciones del mes.
    """
    try:
        contenido, nombre, _advertencias = ExportRecibosService.generar_zip(
            db, empresa_id, cliente, periodo, tipo_liquidacion
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error generando ZIP: {str(e)}")

    return Response(
        content=contenido,
        media_type="application/zip",
        headers={
            "Content-Disposition": (f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{quote(nombre, safe='')}")
        },
    )


@router.get("/recibo/{recibo_id}")
async def descargar_recibo(
    recibo_id: uuid.UUID,
    db: Session = Depends(get_db),
    empresa_id: uuid.UUID = Depends(get_empresa_activa),
    current_user: Usuario = require_admin_recibos,
):
    """Descarga un PDF de recibo individual (firmado si existe, sino original)."""
    try:
        contenido, nombre, content_type = ExportRecibosService.descargar_recibo_individual(db, empresa_id, recibo_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Error descargando recibo: {str(e)}")

    return Response(
        content=contenido,
        media_type=content_type,
        headers={
            "Content-Disposition": (f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{quote(nombre, safe='')}")
        },
    )
