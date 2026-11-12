"""
Servicios para gestión de Empleados, Departamentos y Perfiles.
"""

import math
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, subqueryload

from backend.core.utils import utc_now
from backend.modules.nomina.models import Carrera, Categoria, Departamento, Empleado, Perfil
from backend.modules.usuarios import emails_corporativos


class CategoriaService:
    """Servicio para operaciones de Categorías de perfil."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Categoria:
        try:
            if usuario:
                datos["updated_by"] = usuario
            entidad = Categoria(empresa_id=empresa_id, **datos)
            db.add(entidad)
            db.commit()
            db.refresh(entidad)
            return entidad
        except IntegrityError:
            db.rollback()
            raise ValueError("Ya existe una categoría con ese nombre")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Categoria]:
        return (
            db.query(Categoria)
            .options(subqueryload(Categoria.perfiles))
            .filter(Categoria.id == uuid.UUID(id), Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def listar(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 100, filtros: Dict = None
    ) -> Dict:
        query = (
            db.query(Categoria)
            .options(subqueryload(Categoria.perfiles))
            .filter(Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id)
        )
        if filtros and "buscar" in filtros:
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(or_(Categoria.nombre.ilike(buscar), Categoria.descripcion.ilike(buscar)))
        if filtros and "departamento_id" in filtros and filtros["departamento_id"]:
            query = query.filter(Categoria.departamento_id == uuid.UUID(filtros["departamento_id"]))
        total = query.count()
        # Ordenamiento
        ordenar_por = filtros.get("ordenar_por", "nombre") if filtros else "nombre"
        ordenar_dir = filtros.get("ordenar_dir", "asc") if filtros else "asc"
        columnas_orden = {"nombre": Categoria.nombre, "created_at": Categoria.created_at}
        columna = columnas_orden.get(ordenar_por, Categoria.nombre)
        orden = columna.desc() if ordenar_dir == "desc" else columna.asc()
        items = query.order_by(orden).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def listar_todos(db: Session, empresa_id: uuid.UUID, departamento_id: str = None) -> List[Categoria]:
        """Lista todas las categorías activas para selects, opcionalmente filtradas por departamento."""
        query = db.query(Categoria).filter(Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id)
        if departamento_id:
            query = query.filter(Categoria.departamento_id == uuid.UUID(departamento_id))
        return query.order_by(Categoria.nombre).all()

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None
    ) -> Optional[Categoria]:
        entidad = (
            db.query(Categoria)
            .filter(Categoria.id == uuid.UUID(id), Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return None
        for campo, valor in datos.items():
            if hasattr(entidad, campo) and campo not in ("id", "empresa_id"):
                setattr(entidad, campo, valor)
        entidad.updated_at = utc_now()
        if usuario:
            entidad.updated_by = usuario
        db.commit()
        db.refresh(entidad)
        return entidad

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        entidad = (
            db.query(Categoria)
            .filter(Categoria.id == uuid.UUID(id), Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return False
        entidad.deleted_at = utc_now()
        db.commit()
        return True


class CarreraService:
    """Servicio para operaciones de Carreras."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Carrera:
        try:
            if usuario:
                datos["updated_by"] = usuario
            entidad = Carrera(empresa_id=empresa_id, **datos)
            db.add(entidad)
            db.commit()
            db.refresh(entidad)
            return entidad
        except IntegrityError:
            db.rollback()
            raise ValueError("Ya existe una carrera con ese nombre")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Carrera]:
        return (
            db.query(Carrera)
            .filter(Carrera.id == uuid.UUID(id), Carrera.deleted_at.is_(None), Carrera.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def listar(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 100, filtros: Dict = None
    ) -> Dict:
        query = db.query(Carrera).filter(Carrera.deleted_at.is_(None), Carrera.empresa_id == empresa_id)
        if filtros and "buscar" in filtros:
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(or_(Carrera.nombre.ilike(buscar), Carrera.descripcion.ilike(buscar)))
        total = query.count()
        items = query.order_by(Carrera.nombre).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def listar_todos(db: Session, empresa_id: uuid.UUID) -> List[Carrera]:
        """Lista todas las carreras activas para selects."""
        return (
            db.query(Carrera)
            .filter(Carrera.deleted_at.is_(None), Carrera.empresa_id == empresa_id)
            .order_by(Carrera.nombre)
            .all()
        )

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None) -> Optional[Carrera]:
        entidad = (
            db.query(Carrera)
            .filter(Carrera.id == uuid.UUID(id), Carrera.deleted_at.is_(None), Carrera.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return None
        for campo, valor in datos.items():
            if hasattr(entidad, campo) and campo not in ("id", "empresa_id"):
                setattr(entidad, campo, valor)
        entidad.updated_at = utc_now()
        if usuario:
            entidad.updated_by = usuario
        db.commit()
        db.refresh(entidad)
        return entidad

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        entidad = (
            db.query(Carrera)
            .filter(Carrera.id == uuid.UUID(id), Carrera.deleted_at.is_(None), Carrera.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return False
        entidad.deleted_at = utc_now()
        db.commit()
        return True


class ManagerInvalido(Exception):
    """El manager_id de un departamento no es un empleado de la empresa (422 en el router)."""


class DepartamentoService:
    """Servicio para operaciones de Departamentos."""

    @staticmethod
    def _validar_manager(db: Session, empresa_id: uuid.UUID, manager_id: Any) -> Optional[uuid.UUID]:
        """El manager tiene que ser un empleado de la empresa. Se valida antes de guardar: llegar a la FK daba 409
        «ya existe» en el alta y 500 en la edición (PG-19). Sin manager, None."""
        if manager_id in (None, ""):
            return None
        try:
            manager = uuid.UUID(str(manager_id))
        except ValueError:
            raise ManagerInvalido("El manager elegido no es un empleado válido")
        existe = (
            db.query(Empleado.id)
            .filter(Empleado.id == manager, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
            .first()
        )
        if not existe:
            raise ManagerInvalido("El manager elegido no es un empleado de la empresa")
        return manager

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Departamento:
        datos["manager_id"] = DepartamentoService._validar_manager(db, empresa_id, datos.get("manager_id"))
        if usuario:
            datos["updated_by"] = usuario
        entidad = Departamento(empresa_id=empresa_id, **datos)
        db.add(entidad)
        db.commit()
        db.refresh(entidad)
        return entidad

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Departamento]:
        return (
            db.query(Departamento)
            .filter(
                Departamento.id == uuid.UUID(id),
                Departamento.deleted_at.is_(None),
                Departamento.empresa_id == empresa_id,
            )
            .first()
        )

    @staticmethod
    def listar(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 100, filtros: Dict = None
    ) -> Dict:
        query = db.query(Departamento).filter(Departamento.deleted_at.is_(None), Departamento.empresa_id == empresa_id)
        if filtros and "buscar" in filtros:
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(Departamento.nombre.ilike(buscar))
        total = query.count()
        items = query.order_by(Departamento.nombre).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def listar_todos(db: Session, empresa_id: uuid.UUID) -> List[Departamento]:
        """Lista todos los departamentos activos para selects."""
        return (
            db.query(Departamento)
            .filter(Departamento.deleted_at.is_(None), Departamento.empresa_id == empresa_id)
            .order_by(Departamento.nombre)
            .all()
        )

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None
    ) -> Optional[Departamento]:
        entidad = (
            db.query(Departamento)
            .filter(
                Departamento.id == uuid.UUID(id),
                Departamento.deleted_at.is_(None),
                Departamento.empresa_id == empresa_id,
            )
            .first()
        )
        if not entidad:
            return None
        if "manager_id" in datos:
            datos["manager_id"] = DepartamentoService._validar_manager(db, empresa_id, datos["manager_id"])
        for campo, valor in datos.items():
            if hasattr(entidad, campo) and campo not in ("id", "empresa_id"):
                setattr(entidad, campo, valor)
        entidad.updated_at = utc_now()
        if usuario:
            entidad.updated_by = usuario
        db.commit()
        db.refresh(entidad)
        return entidad

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        entidad = (
            db.query(Departamento)
            .filter(
                Departamento.id == uuid.UUID(id),
                Departamento.deleted_at.is_(None),
                Departamento.empresa_id == empresa_id,
            )
            .first()
        )
        if not entidad:
            return False
        entidad.deleted_at = utc_now()
        db.commit()
        return True


class PerfilService:
    """Servicio para operaciones de Perfiles."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Perfil:
        try:
            if usuario:
                datos["updated_by"] = usuario
            entidad = Perfil(empresa_id=empresa_id, **datos)
            db.add(entidad)
            db.commit()
            db.refresh(entidad)
            return entidad
        except IntegrityError:
            db.rollback()
            raise ValueError("Ya existe un perfil con ese nombre")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Perfil]:
        return (
            db.query(Perfil)
            .filter(Perfil.id == uuid.UUID(id), Perfil.deleted_at.is_(None), Perfil.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def listar(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 100, filtros: Dict = None
    ) -> Dict:
        query = db.query(Perfil).filter(Perfil.deleted_at.is_(None), Perfil.empresa_id == empresa_id)
        if filtros and "buscar" in filtros:
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(Perfil.nombre.ilike(buscar))
        if filtros and "categoria_id" in filtros and filtros["categoria_id"]:
            query = query.filter(Perfil.categoria_id == uuid.UUID(filtros["categoria_id"]))
        if filtros and "departamento_id" in filtros and filtros["departamento_id"]:
            # Filtrar por departamento a través de la categoría
            from backend.modules.nomina.models import Categoria as Cat

            query = query.join(Cat, Perfil.categoria_id == Cat.id).filter(
                Cat.departamento_id == uuid.UUID(filtros["departamento_id"])
            )
        if filtros and "tipo" in filtros and filtros["tipo"]:
            query = query.filter(Perfil.tipo == filtros["tipo"])
        total = query.count()
        items = query.order_by(Perfil.nombre).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def listar_todos(db: Session, empresa_id: uuid.UUID, categoria_id: str = None) -> List[Perfil]:
        """Lista todos los perfiles activos para selects, opcionalmente filtrados por categoría."""
        query = db.query(Perfil).filter(Perfil.deleted_at.is_(None), Perfil.empresa_id == empresa_id)
        if categoria_id:
            query = query.filter(Perfil.categoria_id == uuid.UUID(categoria_id))
        return query.order_by(Perfil.nombre).all()

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None) -> Optional[Perfil]:
        entidad = (
            db.query(Perfil)
            .filter(Perfil.id == uuid.UUID(id), Perfil.deleted_at.is_(None), Perfil.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return None
        for campo, valor in datos.items():
            if hasattr(entidad, campo) and campo not in ("id", "empresa_id"):
                setattr(entidad, campo, valor)
        entidad.updated_at = utc_now()
        if usuario:
            entidad.updated_by = usuario
        db.commit()
        db.refresh(entidad)
        return entidad

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        entidad = (
            db.query(Perfil)
            .filter(Perfil.id == uuid.UUID(id), Perfil.deleted_at.is_(None), Perfil.empresa_id == empresa_id)
            .first()
        )
        if not entidad:
            return False
        entidad.deleted_at = utc_now()
        db.commit()
        return True


class EmpleadoService:
    """Servicio para operaciones de Empleados."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Empleado:
        """Crea un nuevo empleado. El email corporativo lo copia de la cuenta con su DNI, si la hay (F22)."""
        datos.pop("email_corporativo", None)

        # Validar código único (solo entre no eliminados de la misma empresa)
        if "codigo" in datos and datos["codigo"]:
            existente = (
                db.query(Empleado)
                .filter(
                    Empleado.codigo == datos["codigo"], Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el código '{datos['codigo']}'")

        # Validar CUIL único (solo entre no eliminados de la misma empresa)
        if "cuil" in datos and datos["cuil"]:
            existente = (
                db.query(Empleado)
                .filter(
                    Empleado.cuil == datos["cuil"], Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el CUIL {datos['cuil']}")

        # Validar DNI único (solo entre no eliminados de la misma empresa)
        if "dni" in datos and datos["dni"]:
            existente = (
                db.query(Empleado)
                .filter(Empleado.dni == datos["dni"], Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el DNI {datos['dni']}")

        # Si usar_direccion_laboral está ON, copiar dirección laboral a obsequios
        if datos.get("usar_direccion_laboral"):
            campos_dir = [
                "pais",
                "provincia",
                "localidad",
                "codigo_postal",
                "barrio",
                "calle",
                "numero",
                "piso",
                "departamento",
            ]
            for campo in campos_dir:
                datos[f"dir_obsequios_{campo}"] = datos.get(f"dir_laboral_{campo}")

        try:
            if usuario:
                datos["updated_by"] = usuario
            empleado = Empleado(empresa_id=empresa_id, **datos)
            emails_corporativos.copiar_desde_la_cuenta(db, empleado)
            db.add(empleado)
            db.commit()
            db.refresh(empleado)
            # Auto-suscribir al usuario con ese DNI a los grupos del departamento
            if empleado.dni and empleado.departamento_id:
                from backend.modules.permisos.services import GrupoService

                GrupoService.auto_suscribir_empleado(db, empleado.dni, str(empleado.departamento_id), empresa_id)
            return empleado
        except IntegrityError as e:
            db.rollback()
            error_str = str(e).lower()
            if "codigo" in error_str:
                raise ValueError(f"Ya existe un empleado con el código '{datos.get('codigo', '')}'")
            if "cuil" in error_str:
                raise ValueError(f"Ya existe un empleado con el CUIL {datos.get('cuil', '')}")
            if "dni" in error_str:
                raise ValueError(f"Ya existe un empleado con el DNI {datos.get('dni', '')}")
            raise ValueError("Error al guardar: verifique que los datos no estén duplicados")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str, incluir_eliminados: bool = False) -> Optional[Empleado]:
        """Obtiene un empleado por ID."""
        query = db.query(Empleado).filter(Empleado.id == uuid.UUID(id), Empleado.empresa_id == empresa_id)
        if not incluir_eliminados:
            query = query.filter(Empleado.deleted_at.is_(None))
        return query.first()

    @staticmethod
    def obtener_por_codigo(db: Session, empresa_id: uuid.UUID, codigo: str) -> Optional[Empleado]:
        """Obtiene un empleado por código."""
        return (
            db.query(Empleado)
            .filter(Empleado.codigo == codigo, Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def obtener_por_cuil(db: Session, empresa_id: uuid.UUID, cuil: int) -> Optional[Empleado]:
        """Obtiene un empleado por CUIL."""
        return (
            db.query(Empleado)
            .filter(Empleado.cuil == cuil, Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def obtener_por_dni(db: Session, empresa_id: uuid.UUID, dni: int) -> Optional[Empleado]:
        """Obtiene un empleado por DNI."""
        return (
            db.query(Empleado)
            .filter(Empleado.dni == dni, Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 50, filtros: Dict = None) -> Dict:
        """Lista empleados con paginación, filtros, agrupación y ordenamiento."""
        query = db.query(Empleado).filter(Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)

        if filtros:
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(
                    or_(
                        Empleado.codigo.ilike(buscar),
                        cast(Empleado.cuil, String).ilike(buscar),
                        Empleado.apellido.ilike(buscar),
                        Empleado.nombre.ilike(buscar),
                        Empleado.email_corporativo.ilike(buscar),
                    )
                )

            if "departamento_id" in filtros and filtros["departamento_id"]:
                if filtros["departamento_id"] == "null":
                    query = query.filter(Empleado.departamento_id.is_(None))
                else:
                    query = query.filter(Empleado.departamento_id == uuid.UUID(filtros["departamento_id"]))

            if "perfil_id" in filtros and filtros["perfil_id"]:
                if filtros["perfil_id"] == "null":
                    query = query.filter(Empleado.perfil_id.is_(None))
                else:
                    query = query.filter(Empleado.perfil_id == uuid.UUID(filtros["perfil_id"]))

            if "activo" in filtros and filtros["activo"] is not None:
                query = query.filter(Empleado.activo == filtros["activo"])

            if "seniority" in filtros and filtros["seniority"]:
                if filtros["seniority"] == "null":
                    query = query.filter(Empleado.seniority.is_(None))
                else:
                    query = query.filter(Empleado.seniority == filtros["seniority"])

            if "antiguedad_rango" in filtros and filtros["antiguedad_rango"]:
                from datetime import date

                from sqlalchemy import and_

                hoy = date.today()
                rango = filtros["antiguedad_rango"]
                if rango == "0-1":
                    fecha_desde = hoy.replace(year=hoy.year - 1)
                    query = query.filter(Empleado.fecha_alta >= fecha_desde)
                elif rango == "1-3":
                    fecha_hasta = hoy.replace(year=hoy.year - 1)
                    fecha_desde = hoy.replace(year=hoy.year - 3)
                    query = query.filter(and_(Empleado.fecha_alta < fecha_hasta, Empleado.fecha_alta >= fecha_desde))
                elif rango == "3-5":
                    fecha_hasta = hoy.replace(year=hoy.year - 3)
                    fecha_desde = hoy.replace(year=hoy.year - 5)
                    query = query.filter(and_(Empleado.fecha_alta < fecha_hasta, Empleado.fecha_alta >= fecha_desde))
                elif rango == "5-10":
                    fecha_hasta = hoy.replace(year=hoy.year - 5)
                    fecha_desde = hoy.replace(year=hoy.year - 10)
                    query = query.filter(and_(Empleado.fecha_alta < fecha_hasta, Empleado.fecha_alta >= fecha_desde))
                elif rango == "10+":
                    fecha_hasta = hoy.replace(year=hoy.year - 10)
                    query = query.filter(Empleado.fecha_alta < fecha_hasta)
                elif rango == "sin":
                    query = query.filter(Empleado.fecha_alta.is_(None))

        total = query.count()

        # Ordenamiento
        ordenar_por = filtros.get("ordenar_por", "apellido") if filtros else "apellido"
        ordenar_dir = filtros.get("ordenar_dir", "asc") if filtros else "asc"

        orden_map = {
            "cuil": Empleado.cuil,
            "apellido": Empleado.apellido,
            "departamento": Empleado.departamento_id,
            "perfil": Empleado.perfil_id,
            "seniority": Empleado.seniority,
            "antiguedad": Empleado.fecha_alta,
            "activo": Empleado.activo,
        }

        campo_orden = orden_map.get(ordenar_por, Empleado.apellido)
        if ordenar_dir == "desc":
            query = query.order_by(campo_orden.desc(), Empleado.nombre)
        else:
            query = query.order_by(campo_orden, Empleado.nombre)

        items = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        # Agrupación
        grupos = []
        if filtros and "agrupar_por" in filtros and filtros["agrupar_por"]:
            agrupar_por = filtros["agrupar_por"]
            query_todos = db.query(Empleado).filter(Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)

            # Aplicar mismos filtros para agrupación
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query_todos = query_todos.filter(
                    or_(
                        Empleado.codigo.ilike(buscar),
                        cast(Empleado.cuil, String).ilike(buscar),
                        Empleado.apellido.ilike(buscar),
                        Empleado.nombre.ilike(buscar),
                        Empleado.email_corporativo.ilike(buscar),
                    )
                )
            if "activo" in filtros and filtros["activo"] is not None:
                query_todos = query_todos.filter(Empleado.activo == filtros["activo"])

            todos = query_todos.all()

            if agrupar_por == "departamento":
                grupos_dict = {}
                for emp in todos:
                    key = emp.departamento_rel.nombre if emp.departamento_rel else "Sin Departamento"
                    grupos_dict[key] = grupos_dict.get(key, 0) + 1
                grupos = [{"nombre": k, "cantidad": v} for k, v in sorted(grupos_dict.items())]

            elif agrupar_por == "perfil":
                grupos_dict = {}
                for emp in todos:
                    key = emp.perfil_rel.nombre if emp.perfil_rel else "Sin Perfil"
                    grupos_dict[key] = grupos_dict.get(key, 0) + 1
                grupos = [{"nombre": k, "cantidad": v} for k, v in sorted(grupos_dict.items())]

            elif agrupar_por == "estado":
                activos = sum(1 for e in todos if e.activo)
                grupos = [
                    {"nombre": "Activos", "cantidad": activos},
                    {"nombre": "Inactivos", "cantidad": len(todos) - activos},
                ]

            elif agrupar_por == "seniority":
                grupos_dict = {}
                for emp in todos:
                    key = emp.seniority if emp.seniority else "Sin Seniority"
                    grupos_dict[key] = grupos_dict.get(key, 0) + 1
                grupos = [{"nombre": k, "cantidad": v} for k, v in sorted(grupos_dict.items())]

            elif agrupar_por == "antiguedad":
                from datetime import date

                hoy = date.today()
                rangos = {"0-1 años": 0, "1-3 años": 0, "3-5 años": 0, "5-10 años": 0, "10+ años": 0, "Sin fecha": 0}
                for emp in todos:
                    if emp.fecha_alta:
                        años = (hoy - emp.fecha_alta).days / 365.25
                        if años < 1:
                            rangos["0-1 años"] += 1
                        elif años < 3:
                            rangos["1-3 años"] += 1
                        elif años < 5:
                            rangos["3-5 años"] += 1
                        elif años < 10:
                            rangos["5-10 años"] += 1
                        else:
                            rangos["10+ años"] += 1
                    else:
                        rangos["Sin fecha"] += 1
                # Ordenar por rango lógico
                orden_rangos = ["0-1 años", "1-3 años", "3-5 años", "5-10 años", "10+ años", "Sin fecha"]
                grupos = [{"nombre": r, "cantidad": rangos[r]} for r in orden_rangos if rangos[r] > 0]

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
            "grupos": grupos,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[Empleado]:
        """Actualiza un empleado."""
        empleado = (
            db.query(Empleado)
            .filter(Empleado.id == uuid.UUID(id), Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
            .first()
        )

        if not empleado:
            return None

        # El email corporativo es copia del de la cuenta: no se edita en nómina (F22)
        datos.pop("email_corporativo", None)
        cambia_dni = "dni" in datos and datos["dni"] != empleado.dni

        # Validar código único (solo entre no eliminados de la misma empresa)
        if "codigo" in datos and datos["codigo"] and datos["codigo"] != empleado.codigo:
            existente = (
                db.query(Empleado)
                .filter(
                    Empleado.codigo == datos["codigo"],
                    Empleado.deleted_at.is_(None),
                    Empleado.empresa_id == empresa_id,
                    Empleado.id != empleado.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el código '{datos['codigo']}'")

        # Validar CUIL único (solo entre no eliminados de la misma empresa)
        if "cuil" in datos and datos["cuil"] and datos["cuil"] != empleado.cuil:
            existente = (
                db.query(Empleado)
                .filter(
                    Empleado.cuil == datos["cuil"],
                    Empleado.deleted_at.is_(None),
                    Empleado.empresa_id == empresa_id,
                    Empleado.id != empleado.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el CUIL {datos['cuil']}")

        # Validar DNI único (solo entre no eliminados de la misma empresa)
        if "dni" in datos and datos["dni"] and datos["dni"] != empleado.dni:
            existente = (
                db.query(Empleado)
                .filter(
                    Empleado.dni == datos["dni"],
                    Empleado.deleted_at.is_(None),
                    Empleado.empresa_id == empresa_id,
                    Empleado.id != empleado.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un empleado con el DNI {datos['dni']}")

        # Si usar_direccion_laboral está ON, copiar dirección laboral a obsequios
        usar_dir = datos.get("usar_direccion_laboral", empleado.usar_direccion_laboral)
        if usar_dir:
            campos_dir = [
                "pais",
                "provincia",
                "localidad",
                "codigo_postal",
                "barrio",
                "calle",
                "numero",
                "piso",
                "departamento",
            ]
            for campo in campos_dir:
                lab_key = f"dir_laboral_{campo}"
                obs_key = f"dir_obsequios_{campo}"
                # Usar el valor del request si viene, sino el que ya tiene el empleado
                valor = datos.get(lab_key, getattr(empleado, lab_key, None))
                datos[obs_key] = valor

        for campo, valor in datos.items():
            if hasattr(empleado, campo) and campo not in ("id", "empresa_id"):
                setattr(empleado, campo, valor)
        if cambia_dni:
            emails_corporativos.copiar_desde_la_cuenta(db, empleado)

        empleado.updated_at = utc_now()
        if usuario:
            empleado.updated_by = usuario

        try:
            db.commit()
            db.refresh(empleado)
            # Auto-suscribir si cambió el departamento o si tiene departamento asignado
            if empleado.dni and empleado.departamento_id:
                from backend.modules.permisos.services import GrupoService

                GrupoService.auto_suscribir_empleado(db, empleado.dni, str(empleado.departamento_id), empresa_id)
            return empleado
        except IntegrityError as e:
            db.rollback()
            error_str = str(e).lower()
            if "codigo" in error_str:
                raise ValueError(f"Ya existe un empleado con el código '{datos.get('codigo', '')}'")
            if "cuil" in error_str:
                raise ValueError(f"Ya existe un empleado con el CUIL {datos.get('cuil', '')}")
            if "dni" in error_str:
                raise ValueError(f"Ya existe un empleado con el DNI {datos.get('dni', '')}")
            raise ValueError("Error al guardar: verifique que los datos no estén duplicados")

    @staticmethod
    def dar_de_baja(
        db: Session, empresa_id: uuid.UUID, id: str, fecha_baja: str, motivo_baja: str, usuario: str = None
    ) -> Optional[Empleado]:
        """Da de baja a un empleado (cambia estado a inactivo con fecha y motivo)."""
        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.id == uuid.UUID(id),
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
                Empleado.empresa_id == empresa_id,
            )
            .first()
        )

        if not empleado:
            return None

        # Parsear fecha si viene como string
        if isinstance(fecha_baja, str):
            try:
                # Intentar formato yyyy-mm-dd
                fecha_baja = datetime.strptime(fecha_baja, "%Y-%m-%d").date()
            except Exception:
                try:
                    # Intentar formato dd/mm/yyyy
                    fecha_baja = datetime.strptime(fecha_baja, "%d/%m/%Y").date()
                except Exception:
                    fecha_baja = datetime.now().date()

        empleado.activo = False
        empleado.fecha_baja = fecha_baja
        empleado.motivo_baja = motivo_baja
        empleado.updated_at = utc_now()
        if usuario:
            empleado.updated_by = usuario
        db.commit()
        db.refresh(empleado)
        return empleado

    @staticmethod
    def reactivar(db: Session, empresa_id: uuid.UUID, id: str, usuario: str = None) -> Optional[Empleado]:
        """Reactiva un empleado dado de baja."""
        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.id == uuid.UUID(id),
                Empleado.deleted_at.is_(None),
                Empleado.activo == False,
                Empleado.empresa_id == empresa_id,
            )
            .first()
        )

        if not empleado:
            return None

        empleado.activo = True
        empleado.fecha_baja = None
        empleado.motivo_baja = None
        empleado.updated_at = utc_now()
        if usuario:
            empleado.updated_by = usuario
        db.commit()
        db.refresh(empleado)
        return empleado

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        """Soft delete de un empleado."""
        empleado = (
            db.query(Empleado)
            .filter(Empleado.id == uuid.UUID(id), Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id)
            .first()
        )

        if not empleado:
            return False

        empleado.deleted_at = utc_now()
        empleado.activo = False
        db.commit()
        return True

    @staticmethod
    def restaurar(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Empleado]:
        """Restaura un empleado eliminado."""
        empleado = (
            db.query(Empleado)
            .filter(Empleado.id == uuid.UUID(id), Empleado.deleted_at.isnot(None), Empleado.empresa_id == empresa_id)
            .first()
        )

        if not empleado:
            return None

        empleado.deleted_at = None
        empleado.activo = True
        empleado.updated_at = utc_now()
        db.commit()
        db.refresh(empleado)
        return empleado

    @staticmethod
    def listar_para_select(
        db: Session, empresa_id: uuid.UUID, buscar: str = None, seniority: str = None, perfil_tipo: str = None
    ) -> list:
        """Lista empleados activos para selects (manager, lider, hrbp)."""
        query = db.query(Empleado).filter(
            Empleado.deleted_at.is_(None), Empleado.activo == True, Empleado.empresa_id == empresa_id
        )
        if perfil_tipo:
            query = query.join(Perfil, Empleado.perfil_id == Perfil.id).filter(Perfil.tipo == perfil_tipo)
        if seniority:
            query = query.filter(Empleado.seniority == seniority)
        if buscar:
            buscar = f"%{buscar}%"
            query = query.filter(
                or_(Empleado.apellido.ilike(buscar), Empleado.nombre.ilike(buscar), Empleado.codigo.ilike(buscar))
            )
            # Con búsqueda, limitar a 50 resultados
            return query.order_by(Empleado.apellido, Empleado.nombre).limit(50).all()
        # Sin búsqueda, traer todos los empleados activos
        return query.order_by(Empleado.apellido, Empleado.nombre).all()

    @staticmethod
    def listar_hrbps(db: Session, empresa_id: uuid.UUID, buscar: str = None) -> list:
        """Lista empleados cuyo perfil tenga tipo HRBP."""
        query = (
            db.query(Empleado)
            .join(Perfil, Empleado.perfil_id == Perfil.id)
            .filter(
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
                Empleado.empresa_id == empresa_id,
                Perfil.deleted_at.is_(None),
                Perfil.tipo == "HRBP",
            )
        )
        if buscar:
            buscar = f"%{buscar}%"
            query = query.filter(
                or_(Empleado.apellido.ilike(buscar), Empleado.nombre.ilike(buscar), Empleado.codigo.ilike(buscar))
            )
        return query.order_by(Empleado.apellido, Empleado.nombre).limit(50).all()
