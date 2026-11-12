"""
Servicios para el módulo de Operaciones - Equipos.
"""

import math
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.nomina.models import Empleado
from backend.modules.operaciones.models import Equipo


class EquipoService:
    """Servicio para gestión de equipos."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Equipo:
        """Crea un nuevo equipo."""
        try:
            integrantes_ids = datos.pop("integrantes_ids", [])

            if usuario:
                datos["updated_by"] = usuario

            # Convertir UUIDs
            if datos.get("lider_id"):
                datos["lider_id"] = uuid.UUID(datos["lider_id"])
            if datos.get("cliente_id"):
                datos["cliente_id"] = uuid.UUID(datos["cliente_id"])

            equipo = Equipo(empresa_id=empresa_id, **datos)
            db.add(equipo)
            db.flush()

            # Agregar integrantes
            if integrantes_ids:
                for emp_id in integrantes_ids:
                    empleado = (
                        db.query(Empleado)
                        .filter(
                            Empleado.id == uuid.UUID(emp_id),
                            Empleado.deleted_at.is_(None),
                            Empleado.activo == True,
                            Empleado.empresa_id == empresa_id,
                        )
                        .first()
                    )
                    if empleado:
                        equipo.integrantes.append(empleado)

            db.commit()
            db.refresh(equipo)
            return equipo
        except IntegrityError:
            db.rollback()
            raise ValueError("Ya existe un equipo con esos datos")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str, incluir_eliminados: bool = False) -> Optional[Equipo]:
        """Obtiene un equipo por ID."""
        query = db.query(Equipo).filter(Equipo.id == uuid.UUID(id), Equipo.empresa_id == empresa_id)
        if not incluir_eliminados:
            query = query.filter(Equipo.deleted_at.is_(None))
        return query.first()

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        """Lista equipos con paginación y filtros."""
        query = db.query(Equipo).filter(Equipo.deleted_at.is_(None), Equipo.empresa_id == empresa_id)

        if filtros:
            if filtros.get("buscar"):
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(Equipo.nombre.ilike(buscar))

            if filtros.get("activo") is not None:
                query = query.filter(Equipo.activo == filtros["activo"])

        total = query.count()
        items = query.order_by(Equipo.created_at.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None) -> Optional[Equipo]:
        """Actualiza un equipo existente."""
        equipo = (
            db.query(Equipo)
            .filter(Equipo.id == uuid.UUID(id), Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None))
            .first()
        )

        if not equipo:
            return None

        integrantes_ids = datos.pop("integrantes_ids", None)

        # Actualizar campos simples
        for campo, valor in datos.items():
            if hasattr(equipo, campo) and campo not in ("id", "empresa_id"):
                if campo in ["lider_id", "cliente_id"] and valor:
                    valor = uuid.UUID(valor)
                setattr(equipo, campo, valor)

        equipo.updated_at = utc_now()
        if usuario:
            equipo.updated_by = usuario

        # Actualizar integrantes si se proporcionaron
        if integrantes_ids is not None:
            equipo.integrantes.clear()
            for emp_id in integrantes_ids:
                empleado = (
                    db.query(Empleado)
                    .filter(
                        Empleado.id == uuid.UUID(emp_id),
                        Empleado.deleted_at.is_(None),
                        Empleado.activo == True,
                        Empleado.empresa_id == empresa_id,
                    )
                    .first()
                )
                if empleado:
                    equipo.integrantes.append(empleado)

        db.commit()
        db.refresh(equipo)
        return equipo

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        """Elimina (soft delete) un equipo."""
        equipo = (
            db.query(Equipo)
            .filter(Equipo.id == uuid.UUID(id), Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None))
            .first()
        )

        if not equipo:
            return False

        equipo.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def restaurar(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Equipo]:
        """Restaura un equipo eliminado."""
        equipo = (
            db.query(Equipo)
            .filter(Equipo.id == uuid.UUID(id), Equipo.empresa_id == empresa_id, Equipo.deleted_at.isnot(None))
            .first()
        )

        if not equipo:
            return None

        equipo.deleted_at = None
        equipo.updated_at = utc_now()
        db.commit()
        db.refresh(equipo)
        return equipo
