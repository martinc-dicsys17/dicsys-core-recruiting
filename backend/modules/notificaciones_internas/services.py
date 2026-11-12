"""Interfaz de envio y consulta para notificaciones internas."""

import uuid
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.empresa.models import core_usuario_empresa
from backend.modules.notificaciones_internas.models import NotificacionInterna
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.usuarios.models import Usuario


class NotificacionInternaService:
    """Centraliza destinatarios, persistencia y lectura de la bandeja interna."""

    @staticmethod
    def enviar(
        db: Session,
        empresa_id: uuid.UUID,
        *,
        titulo: str,
        mensaje: str,
        usuario_ids: Optional[Iterable[str]] = None,
        grupo_ids: Optional[Iterable[str]] = None,
        enlace: Optional[str] = None,
        tipo: str = "info",
        origen: Optional[str] = None,
    ) -> list[NotificacionInterna]:
        titulo = titulo.strip()
        mensaje = mensaje.strip()
        if not titulo or not mensaje:
            raise ValueError("El titulo y el mensaje son obligatorios")

        usuarios = NotificacionInternaService._destinatarios(db, empresa_id, usuario_ids or [], grupo_ids or [])
        if not usuarios:
            raise ValueError("No se encontraron destinatarios activos para la empresa")

        notificaciones = [
            NotificacionInterna(
                empresa_id=empresa_id,
                usuario_id=usuario.id,
                titulo=titulo,
                mensaje=mensaje,
                enlace=enlace,
                tipo=tipo,
                origen=origen,
            )
            for usuario in usuarios
        ]
        db.add_all(notificaciones)
        db.commit()
        for notificacion in notificaciones:
            db.refresh(notificacion)
        return notificaciones

    @staticmethod
    def listar_para_usuario(
        db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID, limite: int = 10
    ) -> list[NotificacionInterna]:
        return (
            db.query(NotificacionInterna)
            .filter(
                NotificacionInterna.empresa_id == empresa_id,
                NotificacionInterna.usuario_id == usuario_id,
                NotificacionInterna.deleted_at.is_(None),
            )
            .order_by(NotificacionInterna.created_at.desc())
            .limit(limite)
            .all()
        )

    @staticmethod
    def contar_no_leidas(db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID) -> int:
        return (
            db.query(NotificacionInterna)
            .filter(
                NotificacionInterna.empresa_id == empresa_id,
                NotificacionInterna.usuario_id == usuario_id,
                NotificacionInterna.deleted_at.is_(None),
                NotificacionInterna.leida_at.is_(None),
            )
            .count()
        )

    @staticmethod
    def historial_para_usuario(
        db: Session,
        empresa_id: uuid.UUID,
        usuario_id: uuid.UUID,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[NotificacionInterna], int]:
        query = db.query(NotificacionInterna).filter(
            NotificacionInterna.empresa_id == empresa_id,
            NotificacionInterna.usuario_id == usuario_id,
            NotificacionInterna.deleted_at.is_(None),
        )
        total = query.count()
        items = (
            query.order_by(NotificacionInterna.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )
        return items, total

    @staticmethod
    def historial_auditoria(
        db: Session,
        empresa_id: uuid.UUID,
        pagina: int,
        por_pagina: int,
        buscar: Optional[str] = None,
        origen: Optional[str] = None,
    ) -> tuple[list[tuple[NotificacionInterna, Usuario]], int]:
        query = (
            db.query(NotificacionInterna, Usuario)
            .join(
                Usuario,
                Usuario.id == NotificacionInterna.usuario_id,
            )
            .filter(NotificacionInterna.empresa_id == empresa_id)
        )
        if buscar:
            patron = f"%{buscar.strip()}%"
            query = query.filter(Usuario.email.ilike(patron) | NotificacionInterna.titulo.ilike(patron))
        if origen:
            query = query.filter(NotificacionInterna.origen == origen)
        total = query.count()
        items = (
            query.order_by(NotificacionInterna.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )
        return items, total

    @staticmethod
    def marcar_leida(
        db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID, notificacion_id: str
    ) -> NotificacionInterna:
        notificacion = (
            db.query(NotificacionInterna)
            .filter(
                NotificacionInterna.id == uuid.UUID(notificacion_id),
                NotificacionInterna.empresa_id == empresa_id,
                NotificacionInterna.usuario_id == usuario_id,
                NotificacionInterna.deleted_at.is_(None),
            )
            .first()
        )
        if not notificacion:
            raise ValueError("Notificacion no encontrada")
        if notificacion.leida_at is None:
            notificacion.leida_at = utc_now()
            db.commit()
            db.refresh(notificacion)
        return notificacion

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID, notificacion_id: str) -> None:
        notificacion = (
            db.query(NotificacionInterna)
            .filter(
                NotificacionInterna.id == uuid.UUID(notificacion_id),
                NotificacionInterna.empresa_id == empresa_id,
                NotificacionInterna.usuario_id == usuario_id,
                NotificacionInterna.deleted_at.is_(None),
            )
            .first()
        )
        if not notificacion:
            raise ValueError("Notificacion no encontrada")
        notificacion.deleted_at = utc_now()
        db.commit()

    @staticmethod
    def marcar_todas_leidas(db: Session, empresa_id: uuid.UUID, usuario_id: uuid.UUID) -> int:
        actualizadas = (
            db.query(NotificacionInterna)
            .filter(
                NotificacionInterna.empresa_id == empresa_id,
                NotificacionInterna.usuario_id == usuario_id,
                NotificacionInterna.deleted_at.is_(None),
                NotificacionInterna.leida_at.is_(None),
            )
            .update({"leida_at": utc_now()}, synchronize_session=False)
        )
        db.commit()
        return actualizadas

    @staticmethod
    def _destinatarios(
        db: Session,
        empresa_id: uuid.UUID,
        usuario_ids: Iterable[str],
        grupo_ids: Iterable[str],
    ) -> list[Usuario]:
        ids = set()
        for usuario_id in usuario_ids:
            ids.add(uuid.UUID(str(usuario_id)))

        grupos = [uuid.UUID(str(grupo_id)) for grupo_id in grupo_ids]
        if grupos:
            filas = db.execute(
                usuario_grupo.select()
                .join(
                    Grupo,
                    Grupo.id == usuario_grupo.c.grupo_id,
                )
                .where(
                    usuario_grupo.c.empresa_id == empresa_id,
                    usuario_grupo.c.grupo_id.in_(grupos),
                    Grupo.activo.is_(True),
                    Grupo.deleted_at.is_(None),
                )
            ).all()
            ids.update(fila.usuario_id for fila in filas)

        if not ids:
            return []

        return (
            db.query(Usuario)
            .join(
                core_usuario_empresa,
                core_usuario_empresa.c.usuario_id == Usuario.id,
            )
            .filter(
                Usuario.id.in_(ids),
                Usuario.activo.is_(True),
                Usuario.deleted_at.is_(None),
                core_usuario_empresa.c.empresa_id == empresa_id,
            )
            .all()
        )
