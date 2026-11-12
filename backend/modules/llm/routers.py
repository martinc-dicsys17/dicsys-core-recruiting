"""
Routers para el módulo LLM (uso y registros).
Protegido a nivel de main.py con require_submodulo('configuracion', 'llm').
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.core.llm import LLMError, generate
from backend.database import get_db
from backend.dependencies import require_admin
from backend.modules.llm.schemas import (
    LLMRequestList,
    LLMRequestResponse,
    LLMUsageResponse,
)
from backend.modules.llm.services import LLMRequestService
from backend.modules.usuarios.models import Usuario

router = APIRouter(tags=["llm"])
logger = logging.getLogger(__name__)


@router.get("/llm/usage", response_model=LLMUsageResponse)
async def resumen_uso(
    periodo: Optional[str] = Query(None, description="Filtrar por período yyyy-mm"),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Resumen de uso por mes y módulo (para el dashboard)."""
    resumen = LLMRequestService.sumarizar_por_mes_y_modulo(db, periodo)
    return LLMUsageResponse(**resumen)


@router.post("/llm/example-call")
async def ejecutar_llamada_ejemplo(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Ejecuta una llamada real de ejemplo a la LLM para validar la integración."""
    try:
        resultado = generate(
            modulo="llm",
            contents="Respondé solo con OK.",
            db=db,
            usuario=current_user.email,
        )
        return {
            "message": "Llamada de ejemplo ejecutada",
            "result": {
                "id": resultado.id,
                "model_name": resultado.model_name,
                "text": resultado.text,
                "status": resultado.status,
                "tokens_total": resultado.tokens_total,
                "costo_usd": str(resultado.costo_usd),
            },
        }
    except LLMError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        logger.error("Error al ejecutar llamada LLM de ejemplo: %s", e, exc_info=True)
        raise HTTPException(500, "Error inesperado al ejecutar la llamada de ejemplo")


@router.get("/llm/requests", response_model=LLMRequestList)
async def listar_requests(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=200),
    buscar: Optional[str] = None,
    modulo: Optional[str] = None,
    periodo: Optional[str] = None,
    model_name: Optional[str] = None,
    status: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    orden_por: Optional[str] = None,
    orden_dir: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Listado detallado de registros de uso de LLM."""
    filtros = {
        "buscar": buscar,
        "modulo": modulo,
        "periodo": periodo,
        "model_name": model_name,
        "status": status,
        "orden_por": orden_por,
        "orden_dir": orden_dir,
    }
    for campo, valor in (("fecha_desde", fecha_desde), ("fecha_hasta", fecha_hasta)):
        if valor:
            try:
                filtros[campo] = datetime.fromisoformat(valor)
            except ValueError:
                raise HTTPException(400, f"Formato de fecha inválido en {campo}")

    resultado = LLMRequestService.listar(db, pagina, por_pagina, filtros)
    return LLMRequestList(
        items=[LLMRequestResponse.model_validate(i) for i in resultado["items"]],
        **{k: v for k, v in resultado.items() if k != "items"},
    )


@router.get("/llm/requests/{id}", response_model=LLMRequestResponse)
async def obtener_request(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    registro = LLMRequestService.obtener(db, id)
    if not registro:
        raise HTTPException(404, "Registro no encontrado")
    return LLMRequestResponse.model_validate(registro)


@router.get("/llm/requests/{id}/raw/{tipo}", response_class=PlainTextResponse)
async def obtener_raw(
    id: str,
    tipo: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    """Devuelve el raw request o response (tipo ∈ request|response)."""
    if tipo not in ("request", "response"):
        raise HTTPException(400, "Tipo inválido (use request|response)")
    contenido = LLMRequestService.obtener_raw(db, id, tipo)
    if contenido is None:
        raise HTTPException(404, "Archivo raw no encontrado")
    return PlainTextResponse(contenido, media_type="application/json")


@router.delete("/llm/requests/{id}")
async def eliminar_request(
    id: str,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_admin),
):
    try:
        if not LLMRequestService.eliminar(db, id, usuario=current_user.email):
            raise HTTPException(404, "Registro no encontrado")
        return {"message": "Registro eliminado"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al eliminar registro LLM: {e}", exc_info=True)
        raise HTTPException(500, "Error inesperado al eliminar el registro")
