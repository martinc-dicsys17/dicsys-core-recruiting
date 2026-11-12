"""
Servicios para el módulo Parámetros.

- consulta: listado con filtros por categoría y búsqueda libre.
- crear / actualizar / eliminar (soft delete): ABM de definiciones.
- actualizar_valor: edición del valor desde la UI principal.
- obtener_por_key: lectura usada por config.get_parameter.
- registrar_validador: un módulo valida el valor de sus parámetros antes de guardarlo.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from backend.core.utils import utc_now
from backend.modules.parametros.models import Parametro

logger = logging.getLogger(__name__)


class ValorInvalido(ValueError):
    """El valor no sirve para el módulo que usa el parámetro (el mensaje va a la pantalla)."""


# (aplica(key), validar(valor)): validar levanta ValueError con un mensaje legible
_VALIDADORES: List[Tuple[Callable[[str], bool], Callable[[Optional[str]], None]]] = []


def registrar_validador(aplica: Callable[[str], bool], validar: Callable[[Optional[str]], None]) -> None:
    """Un módulo registra cómo validar el valor de sus parámetros (ej. el horario de una tarea)."""
    _VALIDADORES.append((aplica, validar))


def validar_valor(key: str, valor: Optional[str]) -> None:
    """Corre los validadores que aplican a la key; un valor vacío lo decide cada validador."""
    for aplica, validar in _VALIDADORES:
        if aplica(key):
            try:
                validar(valor)
            except ValueError as exc:
                raise ValorInvalido(str(exc)) from exc


class ParametroService:
    """Servicio CRUD de parámetros del sistema."""

    @staticmethod
    def consulta(db: Session, buscar: Optional[str] = None, categoria: Optional[str] = None) -> Query:
        """Parámetros activos, ordenados por categoría/subcategoría/nombre (el router la pagina)."""
        query = db.query(Parametro).filter(Parametro.deleted_at.is_(None))

        if categoria:
            query = query.filter(Parametro.categoria == categoria)

        if buscar:
            patron = f"%{buscar.strip()}%"
            query = query.filter(
                or_(
                    Parametro.nombre.ilike(patron),
                    Parametro.key.ilike(patron),
                    Parametro.descripcion.ilike(patron),
                    Parametro.categoria.ilike(patron),
                    Parametro.subcategoria.ilike(patron),
                )
            )

        return query.order_by(
            Parametro.categoria.asc(), Parametro.subcategoria.asc().nullsfirst(), Parametro.nombre.asc()
        )

    @staticmethod
    def listar_categorias(db: Session) -> List[str]:
        """Devuelve las categorías existentes (para el filtro de la UI)."""
        rows = (
            db.query(Parametro.categoria)
            .filter(Parametro.deleted_at.is_(None))
            .distinct()
            .order_by(Parametro.categoria.asc())
            .all()
        )
        return [r.categoria for r in rows if r.categoria]

    @staticmethod
    def obtener(db: Session, id: str) -> Optional[Parametro]:
        """Obtiene un parámetro por ID (no eliminado)."""
        return db.query(Parametro).filter(Parametro.id == id, Parametro.deleted_at.is_(None)).first()

    @staticmethod
    def obtener_por_key(db: Session, key: str) -> Optional[Parametro]:
        """Obtiene un parámetro por su key (no eliminado)."""
        return db.query(Parametro).filter(Parametro.key == key, Parametro.deleted_at.is_(None)).first()

    @staticmethod
    def crear(db: Session, datos: Dict[str, Any], usuario: Optional[str] = None) -> Parametro:
        """
        Crea un parámetro. La key debe ser única en todo el sistema.
        Si existe un parámetro soft-deleted con la misma key, lo reactiva
        con los datos nuevos (la key tiene constraint unique a nivel DB).
        """
        existente = db.query(Parametro).filter(Parametro.key == datos["key"]).first()

        if existente and existente.deleted_at is None:
            raise ValueError(f"Ya existe un parámetro con la key '{datos['key']}'")
        validar_valor(datos["key"], datos.get("valor"))

        if existente:
            # Reactivar el soft-deleted reutilizando la fila
            for campo, valor in datos.items():
                setattr(existente, campo, valor)
            existente.deleted_at = None
            existente.updated_by = usuario
            db.commit()
            db.refresh(existente)
            return existente

        parametro = Parametro(**datos, updated_by=usuario)
        db.add(parametro)
        db.commit()
        db.refresh(parametro)
        return parametro

    @staticmethod
    def actualizar(db: Session, id: str, datos: Dict[str, Any], usuario: Optional[str] = None) -> Optional[Parametro]:
        """Actualiza la definición completa de un parámetro."""
        parametro = ParametroService.obtener(db, id)
        if not parametro:
            return None

        if datos.get("key") and datos["key"] != parametro.key:
            otro = db.query(Parametro).filter(Parametro.key == datos["key"], Parametro.id != parametro.id).first()
            if otro:
                raise ValueError(f"Ya existe un parámetro con la key '{datos['key']}'")
        validar_valor(datos.get("key") or parametro.key, datos.get("valor", parametro.valor))

        for campo, valor in datos.items():
            setattr(parametro, campo, valor)
        parametro.updated_by = usuario
        db.commit()
        db.refresh(parametro)
        return parametro

    @staticmethod
    def actualizar_valor(
        db: Session, id: str, valor: Optional[str], usuario: Optional[str] = None
    ) -> Optional[Parametro]:
        """Actualiza solo el valor de un parámetro (UI principal)."""
        parametro = ParametroService.obtener(db, id)
        if not parametro:
            return None
        validar_valor(parametro.key, valor)

        parametro.valor = valor
        parametro.updated_by = usuario
        db.commit()
        db.refresh(parametro)
        return parametro

    @staticmethod
    def eliminar(db: Session, id: str, usuario: Optional[str] = None) -> bool:
        """Soft delete de un parámetro."""
        parametro = ParametroService.obtener(db, id)
        if not parametro:
            return False

        parametro.deleted_at = utc_now()
        parametro.updated_by = usuario
        db.commit()
        return True
