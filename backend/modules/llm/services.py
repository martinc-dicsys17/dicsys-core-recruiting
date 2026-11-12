"""
Servicios para el módulo LLM.

- LLMRequestService.registrar: inserta el registro de uso (llamado por core/llm).
- listar: listado paginado con filtros, búsqueda y orden.
- sumarizar_por_mes_y_modulo: resumen anidado período → módulos.
- obtener / eliminar (soft delete) / obtener_raw.
"""

import logging
import math
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.core.llm import logging_store
from backend.core.utils import utc_now
from backend.modules.llm.models import LLMRequest

logger = logging.getLogger(__name__)


def limpiar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitiza campos string: trim, colapsar espacios, None si vacío."""
    limpio = {}
    for campo, valor in datos.items():
        if isinstance(valor, str):
            valor = " ".join(valor.strip().split())
            limpio[campo] = valor if valor else None
        else:
            limpio[campo] = valor
    return limpio


# Columnas permitidas para ordenar (whitelist anti-inyección).
_ORDEN_COLUMNAS = {
    "created_at": LLMRequest.created_at,
    "modulo": LLMRequest.modulo,
    "model_name": LLMRequest.model_name,
    "tokens_total": LLMRequest.tokens_total,
    "tokens_input": LLMRequest.tokens_input,
    "tokens_output": LLMRequest.tokens_output,
    "costo_usd": LLMRequest.costo_usd,
    "status": LLMRequest.status,
    "latencia_ms": LLMRequest.latencia_ms,
}


class LLMRequestService:
    """Servicio para registros de uso de LLM."""

    @staticmethod
    def listar_periodos_disponibles(db: Session) -> List[str]:
        """Devuelve los períodos con actividad, ordenados descendentemente."""
        query = db.query(LLMRequest.periodo).filter(LLMRequest.deleted_at.is_(None))
        query = query.distinct().order_by(LLMRequest.periodo.desc())
        return [row.periodo for row in query.all() if row.periodo]

    @staticmethod
    def registrar(db: Session, datos: Dict[str, Any], usuario: str = None) -> LLMRequest:
        """Inserta un registro de uso de LLM."""
        datos = limpiar_datos(datos)

        # Derivar período del id/fecha si no viene.
        if not datos.get("periodo"):
            datos["periodo"] = utc_now().strftime("%Y-%m")

        if usuario:
            datos["updated_by"] = usuario

        registro = LLMRequest(**datos)
        db.add(registro)
        db.commit()
        db.refresh(registro)
        return registro

    @staticmethod
    def obtener(db: Session, id: str) -> Optional[LLMRequest]:
        """Obtiene un registro por ID (no eliminado)."""
        try:
            return (
                db.query(LLMRequest)
                .filter(
                    LLMRequest.id == uuid.UUID(id),
                    LLMRequest.deleted_at.is_(None),
                )
                .first()
            )
        except ValueError:
            return None

    @staticmethod
    def listar(db: Session, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        """Lista registros con paginación, filtros, búsqueda y orden."""
        filtros = filtros or {}
        query = db.query(LLMRequest).filter(LLMRequest.deleted_at.is_(None))

        if filtros.get("buscar"):
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(
                or_(
                    LLMRequest.modulo.ilike(buscar),
                    LLMRequest.model_name.ilike(buscar),
                )
            )
        if filtros.get("modulo"):
            query = query.filter(LLMRequest.modulo == filtros["modulo"])
        if filtros.get("periodo"):
            query = query.filter(LLMRequest.periodo == filtros["periodo"])
        if filtros.get("model_name"):
            query = query.filter(LLMRequest.model_name == filtros["model_name"])
        if filtros.get("status"):
            query = query.filter(LLMRequest.status == filtros["status"])
        if filtros.get("fecha_desde"):
            query = query.filter(LLMRequest.created_at >= filtros["fecha_desde"])
        if filtros.get("fecha_hasta"):
            query = query.filter(LLMRequest.created_at <= filtros["fecha_hasta"])

        # Orden (whitelist).
        columna = _ORDEN_COLUMNAS.get(filtros.get("orden_por"), LLMRequest.created_at)
        if (filtros.get("orden_dir") or "desc").lower() == "asc":
            query = query.order_by(columna.asc())
        else:
            query = query.order_by(columna.desc())

        total = query.count()
        items = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def sumarizar_por_mes_y_modulo(db: Session, periodo: str = None) -> Dict:
        """
        Devuelve el uso agregado por período (mes) y módulo, con totales
        globales. Estructura lista para el dashboard (acordeón).
        """
        query = db.query(
            LLMRequest.periodo,
            LLMRequest.modulo,
            func.count(LLMRequest.id).label("requests"),
            func.coalesce(func.sum(LLMRequest.tokens_input), 0).label("tokens_input"),
            func.coalesce(func.sum(LLMRequest.tokens_output), 0).label("tokens_output"),
            func.coalesce(func.sum(LLMRequest.tokens_cache), 0).label("tokens_cache"),
            func.coalesce(func.sum(LLMRequest.tokens_total), 0).label("tokens_total"),
            func.coalesce(func.sum(LLMRequest.costo_usd), 0).label("costo_usd"),
        ).filter(LLMRequest.deleted_at.is_(None))

        if periodo:
            query = query.filter(LLMRequest.periodo == periodo)

        query = query.group_by(LLMRequest.periodo, LLMRequest.modulo)
        query = query.order_by(LLMRequest.periodo.desc(), LLMRequest.modulo.asc())

        # Agrupar en estructura anidada período → módulos.
        periodos: Dict[str, Dict] = {}
        total_requests = 0
        total_tokens = 0
        total_costo = Decimal("0")

        for row in query.all():
            p = periodos.setdefault(
                row.periodo,
                {
                    "periodo": row.periodo,
                    "requests": 0,
                    "tokens_input": 0,
                    "tokens_output": 0,
                    "tokens_cache": 0,
                    "tokens_total": 0,
                    "costo_usd": Decimal("0"),
                    "modulos": [],
                },
            )
            costo = Decimal(str(row.costo_usd or 0))
            p["modulos"].append(
                {
                    "modulo": row.modulo,
                    "requests": int(row.requests),
                    "tokens_input": int(row.tokens_input),
                    "tokens_output": int(row.tokens_output),
                    "tokens_cache": int(row.tokens_cache),
                    "tokens_total": int(row.tokens_total),
                    "costo_usd": costo,
                }
            )
            p["requests"] += int(row.requests)
            p["tokens_input"] += int(row.tokens_input)
            p["tokens_output"] += int(row.tokens_output)
            p["tokens_cache"] += int(row.tokens_cache)
            p["tokens_total"] += int(row.tokens_total)
            p["costo_usd"] += costo

            total_requests += int(row.requests)
            total_tokens += int(row.tokens_total)
            total_costo += costo

        return {
            "periodos_disponibles": LLMRequestService.listar_periodos_disponibles(db),
            "periodos": list(periodos.values()),
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_costo_usd": total_costo,
        }

    @staticmethod
    def obtener_raw(db: Session, id: str, tipo: str) -> Optional[str]:
        """Devuelve el contenido del raw request/response de un registro."""
        registro = LLMRequestService.obtener(db, id)
        if not registro:
            return None
        ruta = registro.request_file if tipo == "request" else registro.response_file
        return logging_store.leer_raw(ruta) if ruta else None

    @staticmethod
    def eliminar(db: Session, id: str, usuario: str = None) -> bool:
        """Soft delete de un registro."""
        registro = LLMRequestService.obtener(db, id)
        if not registro:
            return False
        registro.deleted_at = utc_now()
        registro.updated_at = utc_now()
        if usuario:
            registro.updated_by = usuario
        db.commit()
        return True
