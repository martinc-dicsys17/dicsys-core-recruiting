"""
Servicios para el módulo de Clientes.
"""

import logging
import math
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.administracion.clientes_models import CategoriaCliente, Cliente, ClienteDomicilio

logger = logging.getLogger(__name__)


def limpiar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    limpio = {}
    for campo, valor in datos.items():
        if isinstance(valor, str):
            valor = valor.strip()
            valor = " ".join(valor.split())
            valor = valor if valor else None
        limpio[campo] = valor
    return limpio


# ─── CategoriaCliente ─────────────────────────────────────────────────────────


class CategoriaClienteService:
    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, solo_activas: bool = False) -> List[CategoriaCliente]:
        q = db.query(CategoriaCliente).filter(
            CategoriaCliente.deleted_at.is_(None), CategoriaCliente.empresa_id == empresa_id
        )
        if solo_activas:
            q = q.filter(CategoriaCliente.activo == True)
        return q.order_by(CategoriaCliente.nombre).all()

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[CategoriaCliente]:
        try:
            return (
                db.query(CategoriaCliente)
                .filter(
                    CategoriaCliente.id == uuid.UUID(id),
                    CategoriaCliente.deleted_at.is_(None),
                    CategoriaCliente.empresa_id == empresa_id,
                )
                .first()
            )
        except ValueError:
            return None

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> CategoriaCliente:
        datos = limpiar_datos(datos)
        existente = (
            db.query(CategoriaCliente)
            .filter(
                CategoriaCliente.nombre == datos["nombre"],
                CategoriaCliente.deleted_at.is_(None),
                CategoriaCliente.empresa_id == empresa_id,
            )
            .first()
        )
        if existente:
            raise ValueError(f"Ya existe una categoría con el nombre '{datos['nombre']}'")
        if usuario:
            datos["updated_by"] = usuario
        try:
            cat = CategoriaCliente(empresa_id=empresa_id, **datos)
            db.add(cat)
            db.commit()
            db.refresh(cat)
            return cat
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe una categoría con el nombre '{datos.get('nombre', '')}'")

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[CategoriaCliente]:
        cat = CategoriaClienteService.obtener(db, empresa_id, id)
        if not cat:
            return None
        datos = limpiar_datos(datos)
        if "nombre" in datos and datos["nombre"] and datos["nombre"] != cat.nombre:
            existente = (
                db.query(CategoriaCliente)
                .filter(
                    CategoriaCliente.nombre == datos["nombre"],
                    CategoriaCliente.deleted_at.is_(None),
                    CategoriaCliente.empresa_id == empresa_id,
                    CategoriaCliente.id != cat.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe una categoría con el nombre '{datos['nombre']}'")
        for campo, valor in datos.items():
            if hasattr(cat, campo) and campo not in ("id", "empresa_id"):
                setattr(cat, campo, valor)
        cat.updated_at = utc_now()
        if usuario:
            cat.updated_by = usuario
        db.commit()
        db.refresh(cat)
        return cat

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        cat = CategoriaClienteService.obtener(db, empresa_id, id)
        if not cat:
            return False
        cat.deleted_at = utc_now()
        db.commit()
        return True


# ─── Cliente ──────────────────────────────────────────────────────────────────


class ClienteService:
    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        q = db.query(Cliente).filter(Cliente.deleted_at.is_(None), Cliente.empresa_id == empresa_id)

        if filtros:
            if filtros.get("buscar"):
                buscar = f"%{filtros['buscar']}%"
                q = q.filter(
                    or_(
                        Cliente.razon_social.ilike(buscar),
                        Cliente.nombre_fantasia.ilike(buscar),
                        Cliente.cuit.ilike(buscar),
                    )
                )
            if filtros.get("tipo"):
                q = q.filter(Cliente.tipo == filtros["tipo"])
            if filtros.get("activo") is not None:
                q = q.filter(Cliente.activo == filtros["activo"])
            if filtros.get("categoria_id"):
                try:
                    cat_id = uuid.UUID(filtros["categoria_id"])
                    q = q.join(Cliente.categorias).filter(CategoriaCliente.id == cat_id)
                except ValueError:
                    pass

        total = q.count()

        # Ordenamiento dinámico
        ordenar_por = filtros.get("ordenar_por") if filtros else None
        ordenar_dir = filtros.get("ordenar_dir", "asc") if filtros else "asc"
        from sqlalchemy import asc, desc

        dir_fn = desc if ordenar_dir == "desc" else asc

        if ordenar_por == "cuit":
            q = q.order_by(dir_fn(Cliente.cuit))
        elif ordenar_por == "tipo":
            q = q.order_by(dir_fn(Cliente.tipo))
        elif ordenar_por == "activo":
            q = q.order_by(dir_fn(Cliente.activo))
        else:
            q = q.order_by(dir_fn(Cliente.razon_social))

        items = q.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Cliente]:
        try:
            return (
                db.query(Cliente)
                .filter(Cliente.id == uuid.UUID(id), Cliente.deleted_at.is_(None), Cliente.empresa_id == empresa_id)
                .first()
            )
        except ValueError:
            return None

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Cliente:
        categoria_ids = datos.pop("categoria_ids", []) or []
        domicilio_data = datos.pop("domicilio", None)

        datos = limpiar_datos(datos)

        # Validar unicidad CUIT dentro de la empresa
        existente = (
            db.query(Cliente)
            .filter(Cliente.cuit == datos["cuit"], Cliente.deleted_at.is_(None), Cliente.empresa_id == empresa_id)
            .first()
        )
        if existente:
            raise ValueError(f"Ya existe un cliente con el CUIT {datos['cuit']}")

        if usuario:
            datos["updated_by"] = usuario

        try:
            cliente = Cliente(empresa_id=empresa_id, **datos)
            db.add(cliente)
            db.flush()  # Para obtener el ID antes del commit

            # Asignar categorías (solo de la misma empresa)
            if categoria_ids:
                cats = (
                    db.query(CategoriaCliente)
                    .filter(
                        CategoriaCliente.id.in_([uuid.UUID(c) for c in categoria_ids if c]),
                        CategoriaCliente.deleted_at.is_(None),
                        CategoriaCliente.empresa_id == empresa_id,
                    )
                    .all()
                )
                cliente.categorias = cats

            # Crear domicilio inicial
            if domicilio_data:
                dom = ClienteDomicilio(
                    cliente_id=cliente.id,
                    empresa_id=empresa_id,
                    vigente=True,
                    updated_by=usuario,
                    **{k: v for k, v in domicilio_data.items() if k != "vigente"},
                )
                db.add(dom)

            db.commit()
            db.refresh(cliente)
            return cliente
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe un cliente con el CUIT {datos.get('cuit', '')}")

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[Cliente]:
        cliente = ClienteService.obtener(db, empresa_id, id)
        if not cliente:
            return None

        categoria_ids = datos.pop("categoria_ids", None)
        datos = limpiar_datos(datos)

        if "cuit" in datos and datos["cuit"] and datos["cuit"] != cliente.cuit:
            existente = (
                db.query(Cliente)
                .filter(
                    Cliente.cuit == datos["cuit"],
                    Cliente.deleted_at.is_(None),
                    Cliente.empresa_id == empresa_id,
                    Cliente.id != cliente.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un cliente con el CUIT {datos['cuit']}")

        for campo, valor in datos.items():
            if hasattr(cliente, campo) and campo not in ("id", "empresa_id"):
                setattr(cliente, campo, valor)

        cliente.updated_at = utc_now()
        if usuario:
            cliente.updated_by = usuario

        if categoria_ids is not None:
            try:
                cats = (
                    db.query(CategoriaCliente)
                    .filter(
                        CategoriaCliente.id.in_([uuid.UUID(c) for c in categoria_ids if c]),
                        CategoriaCliente.deleted_at.is_(None),
                        CategoriaCliente.empresa_id == empresa_id,
                    )
                    .all()
                )
                cliente.categorias = cats
            except ValueError:
                pass

        try:
            db.commit()
            db.refresh(cliente)
            return cliente
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe un cliente con el CUIT {datos.get('cuit', '')}")

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        cliente = ClienteService.obtener(db, empresa_id, id)
        if not cliente:
            return False
        cliente.deleted_at = utc_now()
        db.commit()
        return True

    # ─── Domicilios ───────────────────────────────────────────────────────────

    @staticmethod
    def agregar_domicilio(
        db: Session, empresa_id: uuid.UUID, cliente_id: str, datos: Dict[str, Any], usuario: str = None
    ) -> ClienteDomicilio:
        cliente = ClienteService.obtener(db, empresa_id, cliente_id)
        if not cliente:
            raise ValueError("Cliente no encontrado")

        # Desactivar domicilios anteriores
        db.query(ClienteDomicilio).filter(
            ClienteDomicilio.cliente_id == cliente.id,
            ClienteDomicilio.deleted_at.is_(None),
            ClienteDomicilio.vigente == True,
        ).update({"vigente": False})

        datos = limpiar_datos(datos)
        dom = ClienteDomicilio(cliente_id=cliente.id, empresa_id=empresa_id, vigente=True, updated_by=usuario, **datos)
        db.add(dom)
        db.commit()
        db.refresh(dom)
        return dom

    @staticmethod
    def eliminar_domicilio(db: Session, empresa_id: uuid.UUID, domicilio_id: str) -> bool:
        try:
            dom = (
                db.query(ClienteDomicilio)
                .filter(
                    ClienteDomicilio.id == uuid.UUID(domicilio_id),
                    ClienteDomicilio.deleted_at.is_(None),
                    ClienteDomicilio.empresa_id == empresa_id,
                )
                .first()
            )
            if not dom:
                return False
            dom.deleted_at = utc_now()
            db.commit()
            return True
        except ValueError:
            return False
