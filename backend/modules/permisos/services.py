"""
Servicios para permisos y grupos.
"""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.permisos.models import Grupo, PermisoModulo, usuario_grupo
from backend.modules.usuarios.models import Usuario


class GrupoService:
    @staticmethod
    def listar_grupos(db: Session, solo_activos: bool = False) -> List[Grupo]:
        query = db.query(Grupo).filter(Grupo.deleted_at.is_(None))
        if solo_activos:
            query = query.filter(Grupo.activo == True)
        return query.order_by(Grupo.nombre).all()

    @staticmethod
    def obtener_grupo(db: Session, grupo_id: str, incluir_eliminados: bool = False) -> Optional[Grupo]:
        try:
            query = db.query(Grupo).filter(Grupo.id == uuid.UUID(grupo_id))
            if not incluir_eliminados:
                query = query.filter(Grupo.deleted_at.is_(None))
            return query.first()
        except ValueError:
            return None

    @staticmethod
    def crear_grupo(db: Session, datos: Dict[str, Any]) -> Grupo:
        # Validar unicidad de nombre entre registros no eliminados
        existente_activo = (
            db.query(Grupo).filter(Grupo.nombre == datos.get("nombre"), Grupo.deleted_at.is_(None)).first()
        )
        if existente_activo:
            raise ValueError(f"Ya existe un grupo con el nombre '{datos.get('nombre')}'")

        # Si existe un grupo soft-deleted con el mismo nombre, eliminarlo definitivamente
        # para evitar conflicto con el constraint unique de la DB
        existente_eliminado = (
            db.query(Grupo).filter(Grupo.nombre == datos.get("nombre"), Grupo.deleted_at.isnot(None)).first()
        )
        if existente_eliminado:
            db.delete(existente_eliminado)
            db.flush()  # Forzar el DELETE antes del INSERT

        try:
            grupo = Grupo(**datos)
            db.add(grupo)
            db.commit()
            db.refresh(grupo)
            return grupo
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe un grupo con el nombre '{datos.get('nombre')}'")

    @staticmethod
    def actualizar_grupo(db: Session, grupo_id: str, datos: Dict[str, Any]) -> Optional[Grupo]:
        grupo = GrupoService.obtener_grupo(db, grupo_id)
        if not grupo:
            return None

        # Validar unicidad de nombre entre registros no eliminados (excluyendo el actual)
        if "nombre" in datos and datos["nombre"] != grupo.nombre:
            existente = (
                db.query(Grupo)
                .filter(Grupo.nombre == datos["nombre"], Grupo.deleted_at.is_(None), Grupo.id != grupo.id)
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un grupo con el nombre '{datos['nombre']}'")

        try:
            for campo, valor in datos.items():
                if hasattr(grupo, campo):
                    setattr(grupo, campo, valor)
            db.commit()
            db.refresh(grupo)
            return grupo
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Ya existe un grupo con el nombre '{datos.get('nombre', '')}'")

    @staticmethod
    def eliminar_grupo(db: Session, grupo_id: str) -> bool:
        grupo = GrupoService.obtener_grupo(db, grupo_id)
        if not grupo:
            return False
        grupo.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def restaurar_grupo(db: Session, grupo_id: str) -> Optional[Grupo]:
        """Restaura un grupo eliminado."""
        try:
            grupo = db.query(Grupo).filter(Grupo.id == uuid.UUID(grupo_id), Grupo.deleted_at.isnot(None)).first()
            if not grupo:
                return None

            grupo.deleted_at = None
            grupo.updated_at = utc_now()
            db.commit()
            db.refresh(grupo)
            return grupo
        except Exception:
            db.rollback()
            return None

    @staticmethod
    def asignar_permisos(db: Session, grupo_id: str, permisos: List[Dict]) -> Grupo:
        grupo = GrupoService.obtener_grupo(db, grupo_id)
        if not grupo:
            raise ValueError("Grupo no encontrado")

        db.query(PermisoModulo).filter(PermisoModulo.grupo_id == grupo.id).delete()

        for p in permisos:
            permiso = PermisoModulo(grupo_id=grupo.id, modulo=p["modulo"], tiene_acceso=p["tiene_acceso"])
            db.add(permiso)

        db.commit()
        db.refresh(grupo)
        return grupo

    @staticmethod
    def obtener_usuarios_grupo(db: Session, grupo_id: str, empresa_id: uuid.UUID) -> List[Usuario]:
        """Obtiene los usuarios de un grupo para una empresa específica."""
        grupo = GrupoService.obtener_grupo(db, grupo_id)
        if not grupo:
            return []

        return (
            db.query(Usuario)
            .join(usuario_grupo, Usuario.id == usuario_grupo.c.usuario_id)
            .filter(usuario_grupo.c.grupo_id == grupo.id, usuario_grupo.c.empresa_id == empresa_id)
            .all()
        )

    @staticmethod
    def asignar_usuarios(db: Session, grupo_id: str, usuario_ids: List[str], empresa_id: uuid.UUID) -> Grupo:
        """Asigna usuarios a un grupo para una empresa específica."""
        grupo = GrupoService.obtener_grupo(db, grupo_id)
        if not grupo:
            raise ValueError("Grupo no encontrado")

        # Borrar asignaciones existentes de este grupo+empresa
        db.execute(
            usuario_grupo.delete().where(usuario_grupo.c.grupo_id == grupo.id, usuario_grupo.c.empresa_id == empresa_id)
        )

        # Insertar nuevas asignaciones
        for uid in usuario_ids:
            try:
                usuario = db.query(Usuario).filter(Usuario.id == uuid.UUID(uid)).first()
                if usuario:
                    db.execute(
                        usuario_grupo.insert().values(
                            usuario_id=usuario.id, grupo_id=grupo.id, empresa_id=empresa_id, created_at=utc_now()
                        )
                    )
            except ValueError:
                continue

        db.commit()
        db.refresh(grupo)
        return grupo

    @staticmethod
    def obtener_grupos_departamento(db: Session, departamento_id: str, empresa_id: uuid.UUID) -> List[Grupo]:
        """Devuelve los grupos vinculados a un departamento para una empresa."""
        from backend.modules.permisos.models import grupo_departamento

        try:
            dep_uuid = uuid.UUID(departamento_id)
        except ValueError:
            return []
        return (
            db.query(Grupo)
            .join(grupo_departamento, Grupo.id == grupo_departamento.c.grupo_id)
            .filter(
                grupo_departamento.c.departamento_id == dep_uuid,
                grupo_departamento.c.empresa_id == empresa_id,
                Grupo.deleted_at.is_(None),
                Grupo.activo == True,
            )
            .all()
        )

    @staticmethod
    def asignar_grupos_departamento(
        db: Session, departamento_id: str, grupo_ids: List[str], empresa_id: uuid.UUID
    ) -> None:
        """Reemplaza los grupos vinculados a un departamento para una empresa."""
        from backend.modules.permisos.models import grupo_departamento

        try:
            dep_uuid = uuid.UUID(departamento_id)
        except ValueError:
            raise ValueError("ID de departamento inválido")

        # Borrar vinculaciones existentes para este departamento+empresa
        db.execute(
            grupo_departamento.delete().where(
                grupo_departamento.c.departamento_id == dep_uuid, grupo_departamento.c.empresa_id == empresa_id
            )
        )
        # Insertar nuevas
        for gid in grupo_ids:
            try:
                db.execute(
                    grupo_departamento.insert().values(
                        grupo_id=uuid.UUID(gid), departamento_id=dep_uuid, empresa_id=empresa_id, created_at=utc_now()
                    )
                )
            except ValueError:
                continue
        db.commit()

    @staticmethod
    def auto_suscribir_empleado(db: Session, dni: int, departamento_id: str, empresa_id: uuid.UUID) -> None:
        """
        Cuando un empleado es creado/actualizado con un departamento,
        busca el usuario con ese DNI y lo suscribe a los grupos vinculados al departamento.
        Solo agrega grupos nuevos, no elimina los existentes.
        """
        if not dni or not departamento_id:
            return

        from backend.modules.usuarios.models import Usuario

        usuario = db.query(Usuario).filter(Usuario.dni == dni, Usuario.deleted_at.is_(None)).first()
        if not usuario:
            return

        grupos = GrupoService.obtener_grupos_departamento(db, departamento_id, empresa_id)
        if not grupos:
            return

        for grupo in grupos:
            # Verificar si ya está suscrito
            ya_existe = db.execute(
                usuario_grupo.select().where(
                    usuario_grupo.c.usuario_id == usuario.id,
                    usuario_grupo.c.grupo_id == grupo.id,
                    usuario_grupo.c.empresa_id == empresa_id,
                )
            ).first()
            if not ya_existe:
                db.execute(
                    usuario_grupo.insert().values(
                        usuario_id=usuario.id, grupo_id=grupo.id, empresa_id=empresa_id, created_at=utc_now()
                    )
                )
        db.commit()

    @staticmethod
    def obtener_permisos_usuario(db: Session, usuario_id: str, empresa_id: uuid.UUID) -> Dict[str, bool]:
        """Obtiene los permisos consolidados de un usuario para una empresa específica."""
        try:
            usuario = db.query(Usuario).filter(Usuario.id == uuid.UUID(usuario_id)).first()
            if not usuario:
                return {}

            grupos = (
                db.query(Grupo)
                .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
                .filter(
                    usuario_grupo.c.usuario_id == usuario.id,
                    usuario_grupo.c.empresa_id == empresa_id,
                    Grupo.activo == True,
                    Grupo.deleted_at.is_(None),
                )
                .all()
            )

            permisos = {}
            for grupo in grupos:
                for permiso in grupo.permisos:
                    if permiso.deleted_at is not None:
                        continue
                    if permiso.tiene_acceso:
                        permisos[permiso.modulo] = True
                    elif permiso.modulo not in permisos:
                        permisos[permiso.modulo] = False

            return permisos
        except ValueError:
            return {}
