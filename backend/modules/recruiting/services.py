"""Servicios del módulo Recruiting.

Por ahora: el alcance de visibilidad de un usuario (qué búsquedas y qué candidatos ve) y el Dashboard. Las reglas
salen del módulo original (modulo-recluiter, backend/modules/recruiting/services.py: DashboardService,
aplicar_filtro_ownership_solicitudes, aplicar_filtro_ownership_candidatos y usuario_es_grupo_externos).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.recruiting.models import (
    Candidato,
    GestionBusqueda,
    Postulacion,
    RecruitingHabilidad,
    RecruitingSkill,
    Solicitud,
    TransicionEstado,
)
from backend.modules.recruiting.schemas import (
    RecruitingDashboard,
    RecruitingDashboardAviso,
    RecruitingDashboardKpis,
    RecruitingDashboardResumen,
)
from backend.modules.usuarios.models import Usuario

# Argentina no tiene horario de verano: UTC-3 fijo, como en el resto del Core
ZONA_ARGENTINA = timezone(timedelta(hours=-3))

ESTADOS_BUSQUEDA_ACTIVA = ("Abierta", "Pre-ingreso")
ESTADO_BUSQUEDA_ABIERTA = "Abierta"
ESTADO_EN_PROCESO = "En proceso"

# Grupos de permisos que definen la visibilidad, por nombre (como en el módulo original)
GRUPO_EXTERNOS = "EXTERNOS"
PARTES_NOMBRE_GRUPO_RECRUITING = ("recruit", "reclut", "recluit")


def es_grupo_externos(nombres) -> bool:
    """True si los nombres de grupo del usuario lo hacen EXTERNOS: tiene el grupo EXTERNOS y ninguno de Recruiting."""
    return GRUPO_EXTERNOS in {n.strip().upper() for n in nombres} and not incluye_grupo_recruiting(nombres)


def incluye_grupo_recruiting(nombres) -> bool:
    """True si algún nombre de grupo es de Recruiting ("recruit", "reclut" o "recluit", sin distinguir mayúsculas)."""
    return any(parte in n.strip().lower() for n in nombres for parte in PARTES_NOMBRE_GRUPO_RECRUITING)


MAX_AVISOS = 8
MAX_TRANSICIONES = 5
MAX_CANDIDATOS_NUEVOS = 3


@dataclass(frozen=True)
class AlcanceRecruiting:
    """Qué búsquedas y qué candidatos de la empresa activa ve un usuario.

    - Admin: todo.
    - Grupo de Recruiting (nombre con "recruit", "reclut" o "recluit"): todas las búsquedas y todos los candidatos.
    - Grupo EXTERNOS (sin grupo de Recruiting): solo las búsquedas que tiene asignadas (externo_id) y los candidatos
      que cargó él.
    - Cualquier otro usuario con acceso al módulo: todas las búsquedas y solo los candidatos que cargó él.
    """

    usuario_id: uuid.UUID
    es_admin: bool
    es_externo: bool
    ve_todos_los_candidatos: bool

    @classmethod
    def de(cls, db: Session, usuario: Usuario, empresa_id: uuid.UUID) -> "AlcanceRecruiting":
        if usuario.rol == "admin":
            return cls(usuario_id=usuario.id, es_admin=True, es_externo=False, ve_todos_los_candidatos=True)
        nombres = db.scalars(
            select(Grupo.nombre)
            .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
            .where(
                usuario_grupo.c.usuario_id == usuario.id,
                usuario_grupo.c.empresa_id == empresa_id,
                Grupo.activo.is_(True),
                Grupo.deleted_at.is_(None),
            )
        ).all()
        return cls(
            usuario_id=usuario.id,
            es_admin=False,
            es_externo=es_grupo_externos(nombres),
            ve_todos_los_candidatos=incluye_grupo_recruiting(nombres),
        )

    def filtro_busquedas(self) -> list:
        """Condiciones extra sobre Solicitud: el externo ve solo las búsquedas que tiene asignadas."""
        return [Solicitud.externo_id == self.usuario_id] if self.es_externo else []

    def filtro_candidatos(self) -> list:
        """Condiciones extra sobre Candidato: quien no ve todos ve solo los que cargó."""
        return [] if self.ve_todos_los_candidatos else [Candidato.creador_id == self.usuario_id]


def _hora_local(momento: datetime | None) -> str | None:
    """Fecha y hora corta (dd/mm hh:mm) en hora argentina; en la base las fechas son UTC sin zona."""
    if momento is None:
        return None
    return momento.replace(tzinfo=timezone.utc).astimezone(ZONA_ARGENTINA).strftime("%d/%m %H:%M")


class DashboardService:
    """Indicadores, avisos y resumen operativo del Dashboard de Recruiting, acotados a lo que ve el usuario."""

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, usuario: Usuario) -> RecruitingDashboard:
        alcance = AlcanceRecruiting.de(db, usuario, empresa_id)
        busquedas_visibles = [
            Solicitud.empresa_id == empresa_id,
            Solicitud.activo.is_(True),
            *alcance.filtro_busquedas(),
        ]
        candidatos_visibles = [
            Candidato.empresa_id == empresa_id,
            Candidato.activo.is_(True),
            *alcance.filtro_candidatos(),
        ]

        busquedas_totales, busquedas_activas = db.execute(
            select(func.count(), func.count().filter(Solicitud.estado.in_(ESTADOS_BUSQUEDA_ACTIVA))).where(
                *busquedas_visibles
            )
        ).one()
        total_candidatos = db.scalar(select(func.count()).select_from(Candidato).where(*candidatos_visibles))
        postulaciones_en_proceso = DashboardService._en_proceso(db, empresa_id, alcance)
        skills_catalogo, habilidades_catalogo = db.execute(
            select(
                select(func.count())
                .select_from(RecruitingSkill)
                .where(RecruitingSkill.activo.is_(True))
                .scalar_subquery(),
                select(func.count())
                .select_from(RecruitingHabilidad)
                .where(RecruitingHabilidad.activo.is_(True))
                .scalar_subquery(),
            )
        ).one()

        avisos = [
            *DashboardService._busquedas_sin_postulantes(db, busquedas_visibles),
            *DashboardService._transiciones_recientes(db, empresa_id, alcance),
            *DashboardService._candidatos_nuevos(db, candidatos_visibles),
        ]
        avisos.sort(key=lambda aviso: aviso.created_at or datetime.min, reverse=True)

        return RecruitingDashboard(
            kpis=RecruitingDashboardKpis(
                busquedas_activas=busquedas_activas,
                total_candidatos=total_candidatos,
                postulaciones_en_proceso=postulaciones_en_proceso,
                skills_catalogo=skills_catalogo,
                habilidades_catalogo=habilidades_catalogo,
            ),
            avisos=avisos[:MAX_AVISOS],
            resumen_operativo=RecruitingDashboardResumen(
                tasa_candidatos_proceso=round(postulaciones_en_proceso / total_candidatos * 100, 1)
                if total_candidatos > 0
                else 0,
                busquedas_totales=busquedas_totales,
            ),
        )

    @staticmethod
    def _en_proceso(db: Session, empresa_id: uuid.UUID, alcance: AlcanceRecruiting) -> int:
        """Candidatos 'En proceso' en el pipeline (GestionBusqueda). Sin ninguno, cuenta las postulaciones del modelo
        anterior (Postulacion), como el módulo original."""
        en_pipeline = db.scalar(
            select(func.count())
            .select_from(GestionBusqueda)
            .join(Candidato, GestionBusqueda.candidato_id == Candidato.id)
            .where(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
                GestionBusqueda.estado == ESTADO_EN_PROCESO,
                *alcance.filtro_candidatos(),
            )
        )
        if en_pipeline:
            return en_pipeline
        return db.scalar(
            select(func.count())
            .select_from(Postulacion)
            .join(Candidato, Postulacion.candidato_id == Candidato.id)
            .where(
                Postulacion.empresa_id == empresa_id,
                Postulacion.activo.is_(True),
                Postulacion.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
                Postulacion.estado == ESTADO_EN_PROCESO,
                *alcance.filtro_candidatos(),
            )
        )

    @staticmethod
    def _busquedas_sin_postulantes(db: Session, busquedas_visibles: list) -> list[RecruitingDashboardAviso]:
        """Búsquedas abiertas sin ningún candidato activo, ni en el pipeline ni en postulaciones. Una sola consulta
        (el original contaba candidatos búsqueda por búsqueda); alcanza con las más recientes, porque el panel muestra
        como mucho MAX_AVISOS avisos ordenados por fecha."""
        busquedas = db.scalars(
            select(Solicitud)
            .where(
                *busquedas_visibles,
                Solicitud.estado == ESTADO_BUSQUEDA_ABIERTA,
                ~exists().where(GestionBusqueda.oportunidad_id == Solicitud.id, GestionBusqueda.activo.is_(True)),
                ~exists().where(Postulacion.solicitud_id == Solicitud.id, Postulacion.activo.is_(True)),
            )
            .order_by(Solicitud.created_at.desc())
            .limit(MAX_AVISOS)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=f"sin_cands_{busqueda.id}",
                tipo="busqueda_sin_candidatos",
                titulo=f"Búsqueda sin postulantes: {busqueda.titulo}",
                descripcion=(
                    f"La búsqueda para {busqueda.cliente or 'Cliente Confidencial'} no tiene candidatos asignados "
                    "en el embudo."
                ),
                tiempo=f"{busqueda.dias_abierta} días abierta",
                icono="alert-triangle",
                color="amber",
                enlace=f"/recruiting/oportunidades/{busqueda.id}",
                created_at=busqueda.created_at,
            )
            for busqueda in busquedas
        ]

    @staticmethod
    def _transiciones_recientes(
        db: Session, empresa_id: uuid.UUID, alcance: AlcanceRecruiting
    ) -> list[RecruitingDashboardAviso]:
        """Los últimos cambios de estado de candidatos que el usuario ve, con el nombre en la misma consulta."""
        filas = db.execute(
            select(TransicionEstado, Candidato.nombre, Candidato.apellido)
            .join(Candidato, TransicionEstado.candidato_id == Candidato.id)
            .where(TransicionEstado.empresa_id == empresa_id, *alcance.filtro_candidatos())
            .order_by(TransicionEstado.created_at.desc())
            .limit(MAX_TRANSICIONES)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=str(transicion.id),
                tipo="transicion",
                titulo=f"Cambio de etapa: {nombre} {apellido}",
                descripcion=f"Pasó a '{transicion.estado_nuevo}'"
                + (f" ({transicion.motivo_rechazo})" if transicion.motivo_rechazo else ""),
                tiempo=_hora_local(transicion.created_at),
                icono="arrow-right-circle",
                color="primary",
                enlace=f"/recruiting/candidatos/{transicion.candidato_id}",
                created_at=transicion.created_at,
            )
            for transicion, nombre, apellido in filas
        ]

    @staticmethod
    def _candidatos_nuevos(db: Session, candidatos_visibles: list) -> list[RecruitingDashboardAviso]:
        """Los últimos candidatos registrados que el usuario ve."""
        candidatos = db.scalars(
            select(Candidato)
            .where(*candidatos_visibles)
            .order_by(Candidato.created_at.desc())
            .limit(MAX_CANDIDATOS_NUEVOS)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=str(candidato.id),
                tipo="candidato_nuevo",
                titulo=f"Nuevo candidato: {candidato.nombre} {candidato.apellido}",
                descripcion=(
                    f"{candidato.headline or 'Perfil General'} · {candidato.seniority or 'Seniority no especificado'}"
                ),
                tiempo=_hora_local(candidato.created_at),
                icono="user-plus",
                color="emerald",
                enlace=f"/recruiting/candidatos/{candidato.id}",
                created_at=candidato.created_at,
            )
            for candidato in candidatos
        ]
