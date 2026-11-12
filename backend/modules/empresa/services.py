"""
Servicios para el módulo de Empresa.

- EmpresaService: CRUD completo con soft-delete, validación unicidad CUIT, paginación y búsqueda
- Gestión de domicilios: crear, listar, eliminar, marcar vigente (solo uno a la vez)
- Gestión de asociación usuario-empresa: agregar, quitar, listar empresas de un usuario
"""

import logging
import math
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.empresa.models import Empresa, EmpresaDomicilio, core_usuario_empresa
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)


def limpiar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitiza todos los campos string: trim, colapsar espacios, None si vacío."""
    import json

    limpio = {}
    for campo, valor in datos.items():
        if campo == "dominios_email":
            # Convertir lista a JSON string para guardar en DB
            if isinstance(valor, list):
                # Limpiar y normalizar dominios
                dominios = [d.strip().lower() for d in valor if d and d.strip()]
                limpio[campo] = json.dumps(dominios) if dominios else None
            else:
                limpio[campo] = valor
        elif isinstance(valor, str):
            valor = valor.strip()
            valor = " ".join(valor.split())
            valor = valor if valor else None
            limpio[campo] = valor
        else:
            limpio[campo] = valor
    return limpio


# ─── EmpresaService ───────────────────────────────────────────────────────────


class EmpresaService:
    """Servicio para operaciones CRUD de Empresa."""

    @staticmethod
    def crear(db: Session, datos: Dict[str, Any], usuario: str = None) -> Empresa:
        """Crea una nueva empresa con validación de unicidad de CUIT."""
        datos = limpiar_datos(datos)

        # Validar unicidad CUIT (solo entre no eliminadas)
        if "cuit" in datos and datos["cuit"]:
            existente = db.query(Empresa).filter(Empresa.cuit == datos["cuit"], Empresa.deleted_at.is_(None)).first()
            if existente:
                raise ValueError(f"Ya existe una empresa con el CUIT {datos['cuit']}")

        if usuario:
            datos["updated_by"] = usuario

        try:
            empresa = Empresa(**datos)
            db.add(empresa)
            db.commit()
            db.refresh(empresa)
            return empresa
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe una empresa con el CUIT {datos.get('cuit', '')}")

    @staticmethod
    def obtener(db: Session, id: str, incluir_eliminados: bool = False) -> Optional[Empresa]:
        """Obtiene una empresa por ID."""
        try:
            query = db.query(Empresa).filter(Empresa.id == uuid.UUID(id))
            if not incluir_eliminados:
                query = query.filter(Empresa.deleted_at.is_(None))
            return query.first()
        except ValueError:
            return None

    @staticmethod
    def listar(db: Session, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        """Lista empresas con paginación, búsqueda y filtros."""
        query = db.query(Empresa).filter(Empresa.deleted_at.is_(None))

        if filtros:
            if filtros.get("buscar"):
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(
                    or_(
                        Empresa.razon_social.ilike(buscar),
                        Empresa.nombre_fantasia.ilike(buscar),
                        Empresa.cuit.ilike(buscar),
                    )
                )
            if filtros.get("activo") is not None:
                query = query.filter(Empresa.activo == filtros["activo"])

        total = query.count()
        items = query.order_by(Empresa.razon_social).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(db: Session, id: str, datos: Dict[str, Any], usuario: str = None) -> Optional[Empresa]:
        """Actualiza una empresa existente."""
        empresa = EmpresaService.obtener(db, id)
        if not empresa:
            return None

        datos = limpiar_datos(datos)

        # Validar unicidad CUIT si cambió
        if "cuit" in datos and datos["cuit"] and datos["cuit"] != empresa.cuit:
            existente = (
                db.query(Empresa)
                .filter(Empresa.cuit == datos["cuit"], Empresa.deleted_at.is_(None), Empresa.id != empresa.id)
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe una empresa con el CUIT {datos['cuit']}")

        for campo, valor in datos.items():
            if hasattr(empresa, campo) and campo != "id":
                setattr(empresa, campo, valor)

        empresa.updated_at = utc_now()
        if usuario:
            empresa.updated_by = usuario

        try:
            db.commit()
            db.refresh(empresa)
            return empresa
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe una empresa con el CUIT {datos.get('cuit', '')}")

    @staticmethod
    def eliminar(db: Session, id: str) -> bool:
        """Soft-delete de una empresa. No elimina asociaciones históricas."""
        empresa = EmpresaService.obtener(db, id)
        if not empresa:
            return False
        empresa.deleted_at = utc_now()
        db.commit()
        return True

    # ─── Domicilios ───────────────────────────────────────────────────────────

    @staticmethod
    def listar_domicilios(db: Session, empresa_id: str) -> List[EmpresaDomicilio]:
        """Lista los domicilios activos de una empresa."""
        try:
            return (
                db.query(EmpresaDomicilio)
                .filter(EmpresaDomicilio.empresa_id == uuid.UUID(empresa_id), EmpresaDomicilio.deleted_at.is_(None))
                .order_by(EmpresaDomicilio.vigente.desc(), EmpresaDomicilio.created_at.desc())
                .all()
            )
        except ValueError:
            return []

    @staticmethod
    def agregar_domicilio(db: Session, empresa_id: str, datos: Dict[str, Any], usuario: str = None) -> EmpresaDomicilio:
        """Crea un domicilio para una empresa. El nuevo domicilio queda como vigente."""
        empresa = EmpresaService.obtener(db, empresa_id)
        if not empresa:
            raise ValueError("Empresa no encontrada")

        # Desactivar domicilios vigentes anteriores
        db.query(EmpresaDomicilio).filter(
            EmpresaDomicilio.empresa_id == empresa.id,
            EmpresaDomicilio.deleted_at.is_(None),
            EmpresaDomicilio.vigente == True,
        ).update({"vigente": False})

        datos = limpiar_datos(datos)
        dom = EmpresaDomicilio(empresa_id=empresa.id, vigente=True, updated_by=usuario, **datos)
        db.add(dom)
        db.commit()
        db.refresh(dom)
        return dom

    @staticmethod
    def eliminar_domicilio(db: Session, empresa_id: str, domicilio_id: str) -> bool:
        """Soft-delete de un domicilio de empresa."""
        try:
            dom = (
                db.query(EmpresaDomicilio)
                .filter(
                    EmpresaDomicilio.id == uuid.UUID(domicilio_id),
                    EmpresaDomicilio.empresa_id == uuid.UUID(empresa_id),
                    EmpresaDomicilio.deleted_at.is_(None),
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

    @staticmethod
    def marcar_domicilio_vigente(db: Session, empresa_id: str, domicilio_id: str) -> Optional[EmpresaDomicilio]:
        """Marca un domicilio como vigente. Solo uno puede ser vigente a la vez."""
        try:
            eid = uuid.UUID(empresa_id)
            did = uuid.UUID(domicilio_id)
        except ValueError:
            return None

        dom = (
            db.query(EmpresaDomicilio)
            .filter(
                EmpresaDomicilio.id == did, EmpresaDomicilio.empresa_id == eid, EmpresaDomicilio.deleted_at.is_(None)
            )
            .first()
        )
        if not dom:
            return None

        # Desactivar todos los vigentes de esa empresa
        db.query(EmpresaDomicilio).filter(
            EmpresaDomicilio.empresa_id == eid, EmpresaDomicilio.deleted_at.is_(None), EmpresaDomicilio.vigente == True
        ).update({"vigente": False})

        dom.vigente = True
        dom.updated_at = utc_now()
        db.commit()
        db.refresh(dom)
        return dom

    # ─── Asociación Usuario-Empresa ───────────────────────────────────────────

    @staticmethod
    def agregar_usuario(db: Session, empresa_id: str, usuario_id: str) -> bool:
        """Asocia un usuario a una empresa."""
        try:
            eid = uuid.UUID(empresa_id)
            uid = uuid.UUID(usuario_id)
        except ValueError:
            raise ValueError("ID de empresa o usuario inválido")

        # Verificar que la empresa existe y no está eliminada
        empresa = db.query(Empresa).filter(Empresa.id == eid, Empresa.deleted_at.is_(None)).first()
        if not empresa:
            raise ValueError("Empresa no encontrada")

        # Verificar que el usuario existe y no está eliminado
        usuario = db.query(Usuario).filter(Usuario.id == uid, Usuario.deleted_at.is_(None)).first()
        if not usuario:
            raise ValueError("Usuario no encontrado")

        # Verificar que no exista ya la asociación (con usuario activo)
        existente = db.execute(
            core_usuario_empresa.select().where(
                core_usuario_empresa.c.usuario_id == uid, core_usuario_empresa.c.empresa_id == eid
            )
        ).first()
        if existente:
            # Si el usuario vinculado fue eliminado, limpiar la asociación huérfana
            usuario_asociado = db.query(Usuario).filter(Usuario.id == uid, Usuario.deleted_at.is_(None)).first()
            if not usuario_asociado:
                db.execute(
                    core_usuario_empresa.delete().where(
                        core_usuario_empresa.c.usuario_id == uid, core_usuario_empresa.c.empresa_id == eid
                    )
                )
                db.commit()
            else:
                raise ValueError("El usuario ya está asociado a esta empresa")

        db.execute(core_usuario_empresa.insert().values(usuario_id=uid, empresa_id=eid, created_at=utc_now()))
        db.commit()
        return True

    @staticmethod
    def quitar_usuario(db: Session, empresa_id: str, usuario_id: str) -> bool:
        """Quita la asociación de un usuario con una empresa."""
        try:
            eid = uuid.UUID(empresa_id)
            uid = uuid.UUID(usuario_id)
        except ValueError:
            return False

        result = db.execute(
            core_usuario_empresa.delete().where(
                core_usuario_empresa.c.usuario_id == uid, core_usuario_empresa.c.empresa_id == eid
            )
        )
        db.commit()
        return result.rowcount > 0

    @staticmethod
    def listar_usuarios(db: Session, empresa_id: str) -> List[Dict[str, Any]]:
        """Lista los usuarios asociados a una empresa."""
        try:
            eid = uuid.UUID(empresa_id)
        except ValueError:
            return []

        rows = db.execute(core_usuario_empresa.select().where(core_usuario_empresa.c.empresa_id == eid)).fetchall()

        resultado = []
        for row in rows:
            usuario = db.query(Usuario).filter(Usuario.id == row.usuario_id, Usuario.deleted_at.is_(None)).first()
            if usuario:
                resultado.append(
                    {
                        "usuario_id": str(row.usuario_id),
                        "empresa_id": str(row.empresa_id),
                        "usuario_nombre": f"{usuario.nombre} {usuario.apellido or ''}".strip(),
                        "usuario_email": usuario.email,
                        "created_at": row.created_at,
                    }
                )
        return resultado

    @staticmethod
    def listar_empresas_usuario(db: Session, usuario_id: str) -> List[Empresa]:
        """Lista las empresas activas (no eliminadas) asociadas a un usuario."""
        try:
            uid = uuid.UUID(usuario_id)
        except ValueError:
            return []

        rows = db.execute(core_usuario_empresa.select().where(core_usuario_empresa.c.usuario_id == uid)).fetchall()

        empresa_ids = [row.empresa_id for row in rows]
        if not empresa_ids:
            return []

        return (
            db.query(Empresa)
            .filter(Empresa.id.in_(empresa_ids), Empresa.deleted_at.is_(None), Empresa.activo == True)
            .order_by(Empresa.razon_social)
            .all()
        )
