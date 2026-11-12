"""
Services HRBP - Lógica de negocio
"""

import math
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.core.utils import utc_now
from backend.modules.hrbp.models import HRBPEntrega, HRBPItemTipo


class ItemTipoService:
    """Servicio para gestión de tipos de items"""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> HRBPItemTipo:
        try:
            if usuario:
                datos["updated_by"] = usuario
            item = HRBPItemTipo(empresa_id=empresa_id, **datos)
            db.add(item)
            db.commit()
            db.refresh(item)
            return item
        except IntegrityError:
            db.rollback()
            raise ValueError("Ya existe un item con ese nombre")

    @staticmethod
    def obtener(
        db: Session, empresa_id: uuid.UUID, id: str, incluir_eliminados: bool = False
    ) -> Optional[HRBPItemTipo]:
        query = db.query(HRBPItemTipo).filter(HRBPItemTipo.id == uuid.UUID(id), HRBPItemTipo.empresa_id == empresa_id)
        if not incluir_eliminados:
            query = query.filter(HRBPItemTipo.deleted_at.is_(None))
        return query.first()

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        query = db.query(HRBPItemTipo).filter(HRBPItemTipo.deleted_at.is_(None), HRBPItemTipo.empresa_id == empresa_id)

        if filtros:
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(or_(HRBPItemTipo.nombre.ilike(buscar), HRBPItemTipo.descripcion.ilike(buscar)))
            if "stock_bajo" in filtros and filtros["stock_bajo"]:
                query = query.filter(HRBPItemTipo.stock_actual <= HRBPItemTipo.stock_minimo)

        total = query.count()
        items = query.order_by(HRBPItemTipo.nombre.asc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None
    ) -> Optional[HRBPItemTipo]:
        item = (
            db.query(HRBPItemTipo)
            .filter(
                HRBPItemTipo.id == uuid.UUID(id),
                HRBPItemTipo.empresa_id == empresa_id,
                HRBPItemTipo.deleted_at.is_(None),
            )
            .first()
        )
        if not item:
            return None
        for campo, valor in datos.items():
            if hasattr(item, campo) and campo not in ("id", "empresa_id"):
                setattr(item, campo, valor)
        item.updated_at = utc_now()
        if usuario:
            item.updated_by = usuario
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        item = (
            db.query(HRBPItemTipo)
            .filter(
                HRBPItemTipo.id == uuid.UUID(id),
                HRBPItemTipo.empresa_id == empresa_id,
                HRBPItemTipo.deleted_at.is_(None),
            )
            .first()
        )
        if not item:
            return False
        item.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def ajustar_stock(
        db: Session, empresa_id: uuid.UUID, id: str, cantidad: int, usuario: str = None
    ) -> Optional[HRBPItemTipo]:
        """Ajusta el stock (positivo suma, negativo resta)"""
        item = (
            db.query(HRBPItemTipo)
            .filter(
                HRBPItemTipo.id == uuid.UUID(id),
                HRBPItemTipo.empresa_id == empresa_id,
                HRBPItemTipo.deleted_at.is_(None),
            )
            .first()
        )
        if not item:
            return None

        nuevo_stock = item.stock_actual + cantidad
        if nuevo_stock < 0:
            raise ValueError("Stock insuficiente")

        item.stock_actual = nuevo_stock
        item.updated_at = utc_now()
        if usuario:
            item.updated_by = usuario
        db.commit()
        db.refresh(item)
        return item


class EntregaService:
    """Servicio para gestión de entregas"""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], hrbp_usuario_id: str) -> HRBPEntrega:
        # Verificar stock disponible
        item_tipo = (
            db.query(HRBPItemTipo)
            .filter(
                HRBPItemTipo.id == uuid.UUID(datos["item_tipo_id"]),
                HRBPItemTipo.empresa_id == empresa_id,
                HRBPItemTipo.deleted_at.is_(None),
            )
            .first()
        )

        if not item_tipo:
            raise ValueError("Tipo de item no encontrado")

        cantidad = datos.get("cantidad", 1)
        if item_tipo.stock_actual < cantidad:
            raise ValueError(f"Stock insuficiente. Disponible: {item_tipo.stock_actual}")

        # Crear entrega
        entrega = HRBPEntrega(
            empresa_id=empresa_id,
            item_tipo_id=uuid.UUID(datos["item_tipo_id"]),
            empleado_id=uuid.UUID(datos["empleado_id"]),
            hrbp_usuario_id=uuid.UUID(hrbp_usuario_id),
            cantidad=cantidad,
            observaciones=datos.get("observaciones"),
            fecha_entrega=datos.get("fecha_entrega") or utc_now(),
        )

        # Descontar stock
        item_tipo.stock_actual -= cantidad
        item_tipo.updated_at = utc_now()

        db.add(entrega)
        db.commit()
        db.refresh(entrega)
        return entrega

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[HRBPEntrega]:
        return (
            db.query(HRBPEntrega)
            .options(
                joinedload(HRBPEntrega.item_tipo),
                joinedload(HRBPEntrega.empleado),
                joinedload(HRBPEntrega.hrbp_usuario),
            )
            .filter(
                HRBPEntrega.id == uuid.UUID(id), HRBPEntrega.empresa_id == empresa_id, HRBPEntrega.deleted_at.is_(None)
            )
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        query = (
            db.query(HRBPEntrega)
            .options(
                joinedload(HRBPEntrega.item_tipo),
                joinedload(HRBPEntrega.empleado),
                joinedload(HRBPEntrega.hrbp_usuario),
            )
            .filter(HRBPEntrega.deleted_at.is_(None), HRBPEntrega.empresa_id == empresa_id)
        )

        if filtros:
            if "item_tipo_id" in filtros and filtros["item_tipo_id"]:
                query = query.filter(HRBPEntrega.item_tipo_id == uuid.UUID(filtros["item_tipo_id"]))
            if "empleado_id" in filtros and filtros["empleado_id"]:
                query = query.filter(HRBPEntrega.empleado_id == uuid.UUID(filtros["empleado_id"]))
            if "hrbp_usuario_id" in filtros and filtros["hrbp_usuario_id"]:
                query = query.filter(HRBPEntrega.hrbp_usuario_id == uuid.UUID(filtros["hrbp_usuario_id"]))
            if "fecha_desde" in filtros and filtros["fecha_desde"]:
                query = query.filter(HRBPEntrega.fecha_entrega >= filtros["fecha_desde"])
            if "fecha_hasta" in filtros and filtros["fecha_hasta"]:
                query = query.filter(HRBPEntrega.fecha_entrega <= filtros["fecha_hasta"])

        total = query.count()
        items = (
            query.order_by(HRBPEntrega.fecha_entrega.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        )

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        """Elimina entrega y devuelve stock"""
        entrega = (
            db.query(HRBPEntrega)
            .filter(
                HRBPEntrega.id == uuid.UUID(id), HRBPEntrega.empresa_id == empresa_id, HRBPEntrega.deleted_at.is_(None)
            )
            .first()
        )
        if not entrega:
            return False

        # Devolver stock
        item_tipo = db.query(HRBPItemTipo).filter(HRBPItemTipo.id == entrega.item_tipo_id).first()
        if item_tipo:
            item_tipo.stock_actual += entrega.cantidad
            item_tipo.updated_at = utc_now()

        entrega.deleted_at = utc_now()
        db.commit()
        return True
