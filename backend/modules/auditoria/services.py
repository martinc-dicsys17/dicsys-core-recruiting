"""
Servicios del módulo de Auditoría.
"""

import math
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.auditoria.models import AuditoriaLog


def _limpiar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitiza strings: trim, colapsar espacios, None si vacío."""
    limpio: Dict[str, Any] = {}
    for campo, valor in datos.items():
        if isinstance(valor, str):
            valor = valor.strip()
            valor = " ".join(valor.split())
            valor = valor if valor else None
        limpio[campo] = valor
    return limpio


class AuditoriaLogService:
    """Operaciones sobre logs de navegación (siempre con scope de empresa)."""

    @staticmethod
    def crear(
        db: Session,
        empresa_id: uuid.UUID,
        datos: Dict[str, Any],
        usuario: Optional[str] = None,
    ) -> AuditoriaLog:
        datos = _limpiar_datos(datos)

        if not datos.get("fecha_hora"):
            datos["fecha_hora"] = utc_now()

        if usuario:
            datos["updated_by"] = usuario

        # empresa_id viene del JWT, no del payload del cliente
        datos["empresa_id"] = empresa_id

        log = AuditoriaLog(**datos)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        pagina: int = 1,
        por_pagina: int = 50,
        filtros: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        query = db.query(AuditoriaLog).filter(
            AuditoriaLog.deleted_at.is_(None),
            AuditoriaLog.empresa_id == empresa_id,
        )

        if filtros:
            email = filtros.get("buscar_email")
            modulo = filtros.get("buscar_modulo")
            ruta = filtros.get("buscar_ruta")
            desde = filtros.get("desde")
            hasta = filtros.get("hasta")

            if email:
                query = query.filter(AuditoriaLog.email_usuario.ilike(f"%{email}%"))
            if modulo:
                query = query.filter(AuditoriaLog.modulo.ilike(f"%{modulo}%"))
            if ruta:
                query = query.filter(AuditoriaLog.ruta.ilike(f"%{ruta}%"))
            if desde:
                query = query.filter(AuditoriaLog.fecha_hora >= desde)
            if hasta:
                query = query.filter(AuditoriaLog.fecha_hora <= hasta)

        total = query.count()
        items = query.order_by(AuditoriaLog.fecha_hora.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) if total else 1,
        }
