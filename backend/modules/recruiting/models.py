"""
Modelos SQLAlchemy para el módulo de Recruiting.

Tabla:
- recruiting_candidatos: Banco de talento y candidatos registrados.
Totalmente aislado de tablas de empleados o personas del core.

Traídos de la instalación de Recruiting (modulo-recluiter, backend/modules/recruiting/models.py). Además de lo que
declaraban sus modelos, acá están los índices, el CHECK y el default de servidor que en esa instalación agregaban sus
migraciones ad hoc (backend/modules/recruiting/migrations), así el esquema que crea la revisión 0006 es el mismo que el
de su base y `alembic check` no ve diferencias. Cada uno lleva el nombre de la migración que lo creaba.
"""
import uuid
from datetime import date
from typing import Optional
from sqlalchemy import Column, String, Text, DateTime, Date, Numeric, Boolean, Integer, BigInteger, ForeignKey, Index, UniqueConstraint, CheckConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from backend.database import Base
from backend.core.utils import utc_now
from backend.modules.empresa.models import Empresa
from backend.modules.usuarios.models import Usuario


class Candidato(Base):
    """
    Modelo de Candidato para el Banco de Talentos de Recruiting.
    """
    __tablename__ = "recruiting_candidatos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    codigo = Column(String(50), nullable=True, index=True)

    # Datos Personales y de Contacto
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    telefono = Column(String(50), nullable=True)
    ubicacion = Column(String(255), nullable=True)
    # Provincia y ciudad del catálogo de Parámetros; "ubicacion" conserva el texto "Ciudad, Provincia" para compatibilidad
    provincia_id = Column(Integer, ForeignKey("recruiting_provincias.provincia_id"), nullable=True, index=True)
    ciudad_id = Column(Integer, ForeignKey("recruiting_ciudades.ciudad_id"), nullable=True, index=True)
    dni = Column(String(50), nullable=True, index=True)
    fecha_nacimiento = Column(Date, nullable=True)

    # Enlaces y Archivos
    linkedin_url = Column(String(500), nullable=True)
    cv_url = Column(String(500), nullable=True)

    # Perfil Profesional
    headline = Column(String(255), nullable=True)
    seniority = Column(String(50), nullable=True)
    modalidad = Column(String(50), nullable=True)
    skills = Column(JSONB, nullable=True, default=list)
    habilidades = Column(JSONB, nullable=True, default=list)
    pretension_salarial = Column(Numeric(14, 2), nullable=True)
    moneda_pretension = Column(String(10), nullable=True, default="ARS")

    # Estado y Origen
    # Estados válidos: Activo, Rechazado, Baja del proceso, Sin respuesta
    estado = Column(String(50), nullable=False, default="Activo")
    fuente = Column(String(100), nullable=True, default="Portal Propio")

    # Ownership / Alcance de visibilidad
    creador_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True, index=True)

    # Auditoría y Soft Delete
    activo = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relación con empresa tenant y creador
    empresa_rel = relationship("Empresa", foreign_keys=[empresa_id], lazy="noload")
    creador_rel = relationship("Usuario", foreign_keys=[creador_id], lazy="noload")

    __table_args__ = (
        Index("idx_recruiting_candidatos_empresa_email", "empresa_id", "email"),
        Index("idx_recruiting_candidatos_estado", "estado"),
        Index("idx_recruiting_candidatos_creador_id", "creador_id"),
    )


def fecha_hoy() -> date:
    """Fecha actual (UTC) con la que se calculan los días de las búsquedas; los tests la reemplazan para simular el paso del tiempo."""
    return utc_now().date()


class Solicitud(Base):
    """
    Modelo de Solicitud / Oportunidad / Búsqueda para Recruiting.
    Refleja la matriz operativa de Dicsys.
    """
    __tablename__ = "recruiting_oportunidades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    id_busqueda = Column(String(50), nullable=True, index=True)  # Código legible: OP-2041, BUSQ-101, etc.
    
    cliente = Column(String(150), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    
    # Estados válidos: 'Abierta', 'Pre-ingreso', 'Suspendida', 'Ganada', 'Cancelada'
    estado = Column(String(50), nullable=False, default="Abierta", index=True)
    
    recruiter_nombre = Column(String(150), nullable=True)
    lider_nombre = Column(String(150), nullable=True)
    # Fecha y hora (UTC naive) en que se asignó o reasignó el reclutador; distinta de fecha_creacion
    fecha_asignacion = Column(DateTime, nullable=True)
    # Fecha de alta de la búsqueda: se asigna al crear y es de solo lectura (no se expone en los esquemas de entrada)
    fecha_creacion = Column(Date, nullable=False, default=date.today, server_default=func.current_date())

    # Atributos operativos de la búsqueda
    puesto = Column(String(150), nullable=True)  # Perfil / Puesto estandarizado (ej: Desarrollador .NET / C#)
    area = Column(String(150), nullable=True, default="Operaciones / IT")
    seniority = Column(String(50), nullable=True, default="Senior")
    modalidad = Column(String(50), nullable=True, default="Remoto")
    vacantes = Column(Numeric(10, 0), nullable=False, default=1)
    rango = Column(String(100), nullable=True)
    prioridad = Column(String(50), nullable=True, default="Alta")
    # Tipo de oportunidad: 'Potencial' o 'Efectiva' (default 'Efectiva')
    tipo = Column(String(50), nullable=False, default="Efectiva")
    skills = Column(JSONB, nullable=True, default=list)
    habilidades = Column(JSONB, nullable=True, default=list)
    skills_deseadas = Column(JSONB, nullable=True, default=list, server_default=text("'[]'::jsonb"))  # oportunidades_skills_deseadas
    descripcion = Column(Text, nullable=True)  # Descripcion de la posicion (opcional)
    
    # Métricas agregadas de Pipeline
    candidatos_pipeline = Column(Numeric(10, 0), nullable=False, default=0)
    coordinando_entrevista = Column(Numeric(10, 0), nullable=False, default=0)
    entrevistados_rrhh = Column(Numeric(10, 0), nullable=False, default=0)
    presentacion_lider = Column(Numeric(10, 0), nullable=False, default=0)
    feedback_lider = Column(Numeric(10, 0), nullable=False, default=0)
    presentacion_cliente = Column(Numeric(10, 0), nullable=False, default=0)
    q_activos = Column(Numeric(10, 0), nullable=False, default=0)

    # Ownership / Alcance de visibilidad
    creador_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True, index=True)
    recruiter_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True, index=True)
    lider_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True, index=True)
    # Usuario del grupo EXTERNOS asignado opcionalmente a la busqueda (maximo uno)
    externo_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True, index=True)

    # Auditoría y Soft Delete
    activo = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones con usuarios
    creador_rel = relationship("Usuario", foreign_keys=[creador_id], lazy="noload")
    recruiter_rel = relationship("Usuario", foreign_keys=[recruiter_id], lazy="noload")
    lider_rel = relationship("Usuario", foreign_keys=[lider_id], lazy="noload")
    externo_rel = relationship("Usuario", foreign_keys=[externo_id], lazy="select")

    __table_args__ = (
        # ownership_visibilidad
        Index("idx_recruiting_oportunidades_creador_id", "creador_id"),
        Index("idx_recruiting_oportunidades_recruiter_id", "recruiter_id"),
        Index("idx_recruiting_oportunidades_lider_id", "lider_id"),
    )

    def _fecha_corte(self):
        """Hasta cuándo se cuentan los días: hoy si la búsqueda sigue abierta; si está Ganada/Cancelada, hasta su último cambio."""
        if self.estado in ("Ganada", "Cancelada"):
            return self.updated_at.date() if self.updated_at else fecha_hoy()
        return fecha_hoy()

    @property
    def dias_abierta(self) -> int:
        """Antigüedad de la búsqueda: días desde su fecha de creación original. No depende de las reasignaciones."""
        if not self.fecha_creacion:
            return 0
        return max(0, (self._fecha_corte() - self.fecha_creacion).days)

    @property
    def dias_reclutador(self) -> Optional[int]:
        """Días con el reclutador actual: desde fecha_asignacion (se reinicia al cambiar de reclutador). None si no hay fecha."""
        if not self.fecha_asignacion:
            return None
        return max(0, (self._fecha_corte() - self.fecha_asignacion.date()).days)


# Alias semántico para consistencia
Oportunidad = Solicitud


class Postulacion(Base):
    """
    Participación o postulación de un candidato en una búsqueda/solicitud específica.
    Permite independizar el perfil global del candidato de su participación puntual.
    """
    __tablename__ = "recruiting_postulaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    candidato_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)
    solicitud_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_oportunidades.id"), nullable=True, index=True)

    # Datos desnormalizados de conveniencia / visualización
    solicitud_titulo = Column(String(200), nullable=True)
    solicitud_cliente = Column(String(150), nullable=True)

    # Estado de la postulación: 'En proceso', 'Entrevista RRHH', 'Presentación Líder', 'Presentación Cliente', 'Rechazado', 'Contratado'
    estado = Column(String(50), nullable=False, default="En proceso")
    etapa = Column(String(50), nullable=True, default="Coordinando entrevista")

    # Datos de fechas del proceso
    fecha_asignacion = Column(DateTime, nullable=True, default=utc_now)
    fecha_etapa = Column(DateTime, nullable=True, default=utc_now)
    fecha_rechazo = Column(DateTime, nullable=True)

    # Datos de rechazo
    motivo_rechazo = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)

    # Auditoría
    activo = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    candidato = relationship("Candidato", foreign_keys=[candidato_id], lazy="joined")
    solicitud = relationship("Solicitud", foreign_keys=[solicitud_id], lazy="joined")

    __table_args__ = (
        Index("idx_recruiting_postulaciones_solicitud_etapa_estado", "solicitud_id", "etapa", "estado"),
        # candidatos_solicitudes_m2m: una sola postulación viva por candidato y búsqueda
        Index(
            "uq_recruiting_postulacion_activa", "solicitud_id", "candidato_id",
            unique=True, postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class TransicionEstado(Base):
    """
    Trazabilidad y auditoría de cambios de estado y transiciones (historial de movimientos).
    """
    __tablename__ = "recruiting_transiciones_estado"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    candidato_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)
    postulacion_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_postulaciones.id"), nullable=True, index=True)

    estado_anterior = Column(String(50), nullable=True)
    estado_nuevo = Column(String(50), nullable=False)
    motivo_rechazo = Column(String(150), nullable=True)
    observaciones = Column(Text, nullable=True)

    usuario = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class GestionBusqueda(Base):
    """
    Modelo de Gestión de Búsqueda / Pipeline para Recruiting.
    Vincula un candidato a una oportunidad/búsqueda con su etapa, estado y trazabilidad.
    """
    __tablename__ = "recruiting_gestionBusqueda"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    oportunidad_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_oportunidades.id"), nullable=False, index=True)
    candidato_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)

    # Etapa actual: Postulado, Screening, Entrevista RRHH, Entrevista Técnica, Entrevista Cliente, Oferta, Ingreso, Descartados
    etapa_actual = Column(String(100), nullable=False, default="Postulado")

    # Estado: En proceso, Avanzó, Descartado
    estado = Column(String(50), nullable=False, default="En proceso")

    # Motivo y feedback
    motivo_descarte = Column(Text, nullable=True)
    feedback_etapa = Column(Text, nullable=True)

    # Pretensión salarial bruta (ARS, entero): se informa al pasar de Entrevista RRHH a Entrevista Líder Dicsys
    pretension_salarial_bruta_ars = Column(BigInteger, nullable=True)

    # Fecha de última transición
    fecha_cambio_etapa = Column(DateTime, nullable=True, default=utc_now)

    # Auditoría y Soft Delete
    activo = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    candidato = relationship("Candidato", foreign_keys=[candidato_id], lazy="joined")
    oportunidad = relationship("Solicitud", foreign_keys=[oportunidad_id], lazy="joined")

    __table_args__ = (
        UniqueConstraint("candidato_id", "oportunidad_id", name="uq_recruiting_gestion_busqueda_candidato_oportunidad"),
        Index("idx_recruiting_gestion_busqueda_etapa_estado", "oportunidad_id", "etapa_actual", "estado"),
        # gestion_busqueda
        Index("idx_recruiting_gestion_busqueda_empresa_id", "empresa_id"),
        Index("idx_recruiting_gestion_busqueda_oportunidad_id", "oportunidad_id"),
        Index("idx_recruiting_gestion_busqueda_candidato_id", "candidato_id"),
        Index("idx_recruiting_gestion_busqueda_deleted_at", "deleted_at"),
        # gestion_busqueda_pretension_salarial
        CheckConstraint(
            "pretension_salarial_bruta_ars IS NULL OR pretension_salarial_bruta_ars >= 0",
            name="ck_recruiting_gestion_busqueda_pretension_no_negativa",
        ),
    )


class HistorialPipeline(Base):
    """
    Historial inmutable de cambios de etapa en el pipeline de recruiting.
    Cada vez que se mueve un candidato de etapa se inserta un nuevo registro.
    """
    __tablename__ = "recruiting_historial_pipeline"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id     = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    oportunidad_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_oportunidades.id"), nullable=False, index=True)
    candidato_id   = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)

    etapa_anterior = Column(String(100), nullable=True)
    etapa_nueva    = Column(String(100), nullable=False)
    estado_nuevo   = Column(String(50), nullable=True)
    descripcion    = Column(Text, nullable=True)   # nota/feedback que ingresó el recruiter
    motivo_descarte= Column(Text, nullable=True)

    usuario        = Column(String(255), nullable=True)
    created_at     = Column(DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_recruiting_historial_pipeline_candidato_op", "oportunidad_id", "candidato_id"),
    )


class RecrutingConfig(Base):
    """
    Configuración parametrizable del módulo de Recruiting por empresa.
    Almacena valores como el umbral mínimo de Smart Matching.
    Un único registro por empresa_id (upsert).
    """
    __tablename__ = "recruiting_config"

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id             = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, unique=True, index=True)

    # Smart Matching: porcentaje mínimo para que un candidato califique (1–100)
    match_minimo_porcentaje = Column(Integer, nullable=False, default=50)

    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class RecruitingSkill(Base):
    """
    Catálogo de Tecnologías y Habilidades para Recruiting.
    Permite reconocimiento dinámico y escalable en el parsing de CVs y Smart Matching.
    """
    __tablename__ = "recruiting_skills"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False, unique=True, index=True)
    categoria = Column(String(100), nullable=True)
    sinonimos = Column(JSONB, nullable=True, default=list)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class RecruitingEtapa(Base):
    """
    Catálogo de Etapas del Workflow de Recruiting.
    """
    __tablename__ = "recruiting_etapas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)


class RecruitingMotivoDescarte(Base):
    """
    Catálogo general de Motivos de Descarte de candidatos en Recruiting.
    """
    __tablename__ = "recruiting_motivos_descarte"

    id = Column(Integer, primary_key=True, autoincrement=True)
    motivo = Column(String(150), nullable=False, unique=True)


class RecruitingMotivoBlacklist(Base):
    """
    Catálogo global de motivos por los que una persona entra en la Blacklist de Recruiting.
    """
    __tablename__ = "recruiting_motivos_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    motivo = Column(String(150), nullable=False, unique=True)


class RecruitingMotivoDescarteEtapa(Base):
    """
    Relación entre un motivo de descarte y las etapas del workflow en las que está disponible.
    El campo orden conserva el orden de presentación del motivo dentro de cada etapa.
    """
    __tablename__ = "recruiting_motivos_descarte_etapas"

    motivo_id = Column(Integer, ForeignKey("recruiting_motivos_descarte.id"), primary_key=True)
    etapa_id = Column(Integer, ForeignKey("recruiting_etapas.id"), primary_key=True)
    orden = Column(Integer, nullable=False)


class Provincia(Base):
    """
    Catálogo de Provincias para la ubicación en Recruiting.
    """
    __tablename__ = "recruiting_provincias"

    provincia_id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(100), nullable=False, unique=True)


class Ciudad(Base):
    """
    Catálogo de Ciudades/Localidades de cada provincia para la ubicación en Recruiting.
    """
    __tablename__ = "recruiting_ciudades"
    __table_args__ = (
        UniqueConstraint("provincia_id", "nombre", name="uq_recruiting_ciudades_provincia_nombre"),
    )

    ciudad_id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False)
    provincia_id = Column(Integer, ForeignKey("recruiting_provincias.provincia_id"), nullable=False)


class RecruitingNivelSeniority(Base):
    """
    Catálogo de Niveles de Seniority para candidatos de Recruiting.
    """
    __tablename__ = "recruiting_niveles_seniority"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(50), nullable=False, unique=True)


class RecruitingPerfilPuesto(Base):
    """
    Catálogo de Perfiles de puesto de Recruiting (migración perfiles_puesto_catalogo).
    """
    __tablename__ = "recruiting_perfiles_puesto"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(150), nullable=False, unique=True)
    activo = Column(Boolean, nullable=False, default=True)


class RecruitingHabilidad(Base):
    """
    Catálogo de Habilidades, Roles y Competencias Profesionales para Recruiting.
    Independiente del catálogo técnico de Skills/Tecnologías.
    """
    __tablename__ = "recruiting_habilidades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False, unique=True, index=True)
    categoria = Column(String(100), nullable=True)
    sinonimos = Column(JSONB, nullable=True, default=list)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class RecruitingLider(Base):
    """
    Catálogo de Líderes / Hiring Managers que alimenta el combo de Nueva oportunidad.
    Las búsquedas guardan el nombre (lider_nombre), por lo que renombrar un registro no altera búsquedas ya creadas.
    """
    __tablename__ = "recruiting_lideres"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(150), nullable=False, unique=True, index=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class RecruitingReclutador(Base):
    """
    Catálogo de Reclutadores responsables que alimenta el combo de Nueva oportunidad.
    Las búsquedas guardan el nombre (recruiter_nombre).
    """
    __tablename__ = "recruiting_reclutadores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(150), nullable=False, unique=True, index=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)


class EtapaArchivo(Base):
    """
    Archivos adjuntos vinculados a una búsqueda, candidato y etapa/estado del pipeline.
    """
    __tablename__ = "recruiting_etapa_archivos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    busqueda_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_oportunidades.id"), nullable=False, index=True)
    candidato_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)

    etapa_id = Column(String(100), nullable=False)
    estado = Column(String(50), nullable=True)

    nombre_archivo = Column(String(255), nullable=False)
    tipo_archivo = Column(String(100), nullable=False)
    tamano = Column(Integer, nullable=False)
    ruta_archivo = Column(String(500), nullable=False)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)

    candidato = relationship("Candidato", foreign_keys=[candidato_id], lazy="joined")
    oportunidad = relationship("Solicitud", foreign_keys=[busqueda_id], lazy="joined")

    __table_args__ = (
        # etapa_archivos
        Index("idx_recruiting_etapa_archivos_empresa_id", "empresa_id"),
        Index("idx_recruiting_etapa_archivos_busqueda_candidato", "busqueda_id", "candidato_id"),
        Index("idx_recruiting_etapa_archivos_etapa", "busqueda_id", "candidato_id", "etapa_id"),
    )


class CandidatoDuplicado(Base):
    """
    Caso pendiente de revision: un usuario externo cargo, desde una busqueda asignada, un CV con email ya existente y archivo distinto.
    El candidato ya fue asociado a la busqueda; el CV nuevo queda en storage temporal hasta que un Recruiter conserve o actualice.
    """
    __tablename__ = "recruiting_candidatos_duplicados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, index=True)
    candidato_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_candidatos.id"), nullable=False, index=True)
    oportunidad_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_oportunidades.id"), nullable=False, index=True)
    presentado_por_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)
    cv_identico = Column(Boolean, nullable=False, default=False)
    archivo_temp_key = Column(String(500), nullable=True)
    nombre_archivo = Column(String(255), nullable=True)
    datos_nuevo = Column(JSONB, nullable=True)
    estado = Column(String(20), nullable=False, default="pendiente", index=True)
    resolucion = Column(String(20), nullable=True)
    resuelto_por_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)
    resuelto_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)

    candidato = relationship("Candidato", foreign_keys=[candidato_id], lazy="joined")
    oportunidad = relationship("Solicitud", foreign_keys=[oportunidad_id], lazy="joined")
    presentado_por = relationship("Usuario", foreign_keys=[presentado_por_id], lazy="joined")


class HistorialCargaCV(Base):
    """Auditoria persistente de una operacion de carga de CV (individual o masiva). Solo estructura: aun no se registra desde el proceso de carga."""
    __tablename__ = "recruiting_historial_cargas_cv"
    __table_args__ = (
        CheckConstraint("tipo_carga IN ('individual', 'masiva')", name="ck_recruiting_historial_cargas_cv_tipo_carga"),
        CheckConstraint("resultado IN ('completada', 'parcial', 'fallida', 'cancelada')", name="ck_recruiting_historial_cargas_cv_resultado"),
        CheckConstraint(
            "total_archivos >= 0 AND candidatos_creados >= 0 AND duplicados >= 0 AND sin_email >= 0 AND rechazados >= 0",
            name="ck_recruiting_historial_cargas_cv_cantidades_no_negativas",
        ),
        Index("idx_recruiting_historial_cargas_cv_empresa_id", "empresa_id"),
        Index("idx_recruiting_historial_cargas_cv_usuario_id", "usuario_id"),
        Index("idx_recruiting_historial_cargas_cv_fecha_operacion", "fecha_operacion"),
        Index("idx_recruiting_historial_cargas_cv_empresa_fecha", "empresa_id", "fecha_operacion"),
        Index("uq_recruiting_historial_cargas_cv_operacion_id", "operacion_id", unique=True, postgresql_where=text("operacion_id IS NOT NULL")),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)
    usuario_nombre = Column(String(255), nullable=False)
    fecha_operacion = Column(DateTime, nullable=False, default=utc_now)
    tipo_carga = Column(String(20), nullable=False)
    nombre_archivo = Column(String(255), nullable=True)
    total_archivos = Column(Integer, nullable=False, default=0)
    candidatos_creados = Column(Integer, nullable=False, default=0)
    duplicados = Column(Integer, nullable=False, default=0)
    sin_email = Column(Integer, nullable=False, default=0)
    rechazados = Column(Integer, nullable=False, default=0)
    resultado = Column(String(20), nullable=False)
    # Identifica la operacion (una sola fila por operacion aunque se intente registrar dos veces)
    operacion_id = Column(UUID(as_uuid=True), nullable=True)


class HistorialCargaCVArchivo(Base):
    """Resultado de cada archivo de una operacion de carga de CV. Solo metadatos de auditoria: sin contenido del CV ni datos personales extraidos."""
    __tablename__ = "recruiting_historial_cargas_cv_archivos"
    __table_args__ = (
        CheckConstraint("resultado IN ('creado', 'duplicado', 'sin_email', 'rechazado')", name="ck_recruiting_historial_cargas_cv_archivos_resultado"),
        Index("idx_recruiting_historial_cargas_cv_archivos_historial_id", "historial_id"),
        Index("idx_recruiting_historial_cargas_cv_archivos_empresa_id", "empresa_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    historial_id = Column(UUID(as_uuid=True), ForeignKey("recruiting_historial_cargas_cv.id"), nullable=False)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    orden = Column(Integer, nullable=False, default=0)
    nombre_archivo = Column(String(255), nullable=False)
    resultado = Column(String(20), nullable=False)
    motivo = Column(String(500), nullable=True)


# lideres_reclutadores_catalogo y perfiles_puesto_catalogo_v2: nombres únicos sin distinguir mayúsculas
Index("uq_recruiting_lideres_nombre_lower", func.lower(RecruitingLider.nombre), unique=True)
Index("uq_recruiting_reclutadores_nombre_lower", func.lower(RecruitingReclutador.nombre), unique=True)
Index("uq_recruiting_perfiles_puesto_nombre_lower", func.lower(RecruitingPerfilPuesto.nombre), unique=True)
