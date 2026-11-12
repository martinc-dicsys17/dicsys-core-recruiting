"""
Modelos de Proveedores (Administración): registro de proveedores y herramientas
y su evaluación por campañas (F18).

Las clases no se llaman «Proveedor» a secas porque Innovación ya tiene un
modelo con ese nombre (catálogo de licencias) y SQLAlchemy resuelve las
relaciones por nombre de clase.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

TIPOS_PROVEEDOR = ("proveedor", "herramienta", "sin_clasificar")
OPCIONES_ACUERDO = ("Si", "No")  # Sí exige el adjunto; No, la política/NDA en texto
# «Tipo de IVA»: las responsabilidades AFIP de Clientes, con «Proveedor del Exterior» (D-92)
RESPONSABILIDADES_IVA = (
    "Responsable Inscripto",
    "Sujeto Exento",
    "Consumidor Final",
    "Responsable Monotributo",
    "Proveedor del Exterior",
    "Sujeto No Categorizado",
)
# Respuestas de la evaluación (las de la planilla RC 02-02, sin el checklist de seguridad)
OPCIONES_INCIDENTES = ("Si", "No", "N/A")
OPCIONES_MAL_MANEJO = ("Si", "No")
# Evidencia de cada pregunta: se muestra y es obligatoria solo con «Si»
EVIDENCIA_DE = {"incidentes": "evidencia_incidentes", "mal_manejo": "evidencia_mal_manejo"}
EVIDENCIAS = tuple(EVIDENCIA_DE.values())


def _en(columna: str, valores) -> str:
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


class _Auditable:
    """Columnas de auditoría y baja lógica del repo."""

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True, default=None)


# ─── Registro ───────────────────────────────────────────────────────────────────


class RegistroProveedor(_Auditable, Base):
    """Proveedor o herramienta del registro (ISO A.5.19–A.5.22)."""

    __tablename__ = "proveedores_proveedores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(200), nullable=False)  # nombre de fantasía o herramienta
    razon_social = Column(String(200), nullable=True)
    # Datos fiscales (D-92), opcionales: los proveedores del exterior no tienen CUIT
    cuit = Column(String(13), nullable=True)  # XX-XXXXXXXX-X
    responsabilidad_afip = Column(String(50), nullable=True)  # «tipo de IVA»
    nro_ingresos_brutos = Column(String(50), nullable=True)
    tipo = Column(String(20), nullable=False, default="sin_clasificar")
    # «Usuario referente»: un empleado de la nómina. NULL = sin definir.
    referente_empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)
    servicio_provisto = Column(Text, nullable=True)
    tipo_informacion = Column(Text, nullable=True)
    email = Column(String(255), nullable=True)
    # Solo dígitos con código de país (5493511234567): el front arma el link a WhatsApp Web
    telefono_whatsapp = Column(String(20), nullable=True)
    pagina_web = Column(String(500), nullable=True)
    # Obligatorio al guardar desde el form y al importar; NULL solo en registros viejos sin completar
    acuerdo_servicio = Column(String(5), nullable=True)
    politica_nda = Column(Text, nullable=True)  # texto o enlace
    politica_nda_archivo = Column(String(500), nullable=True)  # clave en el storage privado
    politica_nda_archivo_nombre = Column(String(255), nullable=True)
    observaciones = Column(Text, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)  # baja: sale de las próximas evaluaciones

    referente_rel = relationship("Empleado", foreign_keys=[referente_empleado_id])
    oficinas = relationship(
        "ProveedorOficina",
        primaryjoin="and_(ProveedorOficina.proveedor_id == RegistroProveedor.id, "
        "ProveedorOficina.deleted_at.is_(None))",
        order_by="ProveedorOficina.created_at",
        viewonly=True,
    )
    contactos = relationship(
        "ProveedorContacto",
        primaryjoin="and_(ProveedorContacto.proveedor_id == RegistroProveedor.id, "
        "ProveedorContacto.deleted_at.is_(None))",
        order_by="ProveedorContacto.created_at",
        viewonly=True,
    )
    documentos = relationship(
        "ProveedorDocumento",
        primaryjoin="and_(ProveedorDocumento.proveedor_id == RegistroProveedor.id, "
        "ProveedorDocumento.deleted_at.is_(None))",
        order_by="ProveedorDocumento.created_at.desc()",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint(_en("tipo", TIPOS_PROVEEDOR), name="ck_proveedores_tipo"),
        CheckConstraint(_en("acuerdo_servicio", OPCIONES_ACUERDO), name="ck_proveedores_acuerdo"),
        CheckConstraint(_en("responsabilidad_afip", RESPONSABILIDADES_IVA), name="ck_proveedores_iva"),
        # Red de seguridad: la comparación sin acentos la hace la app
        Index(
            "uq_proveedores_empresa_nombre",
            "empresa_id",
            func.lower(func.btrim(text("nombre"))),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_proveedores_referente", "referente_empleado_id"),
    )


class ProveedorOficina(_Auditable, Base):
    """Oficina del proveedor: un domicilio por oficina (campos de customer_cliente_domicilios)."""

    __tablename__ = "proveedores_oficinas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_proveedores.id"), nullable=False)
    nombre_oficina = Column(String(100), nullable=True)
    calle = Column(String(200), nullable=False)
    numero = Column(String(20), nullable=True)
    piso = Column(String(20), nullable=True)
    departamento = Column(String(20), nullable=True)
    localidad = Column(String(100), nullable=False)
    provincia = Column(String(100), nullable=True)  # opcional: hay proveedores del exterior
    pais = Column(String(100), nullable=False, default="Argentina")
    codigo_postal = Column(String(10), nullable=True)
    es_legal = Column(Boolean, nullable=False, default=False)  # domicilio legal

    proveedor = relationship("RegistroProveedor", foreign_keys=[proveedor_id])

    __table_args__ = (
        Index("ix_proveedores_oficinas_proveedor", "proveedor_id"),
        Index(
            "uq_proveedores_oficina_legal",
            "proveedor_id",
            unique=True,
            postgresql_where=text("es_legal AND deleted_at IS NULL"),
        ),
    )


class ProveedorContacto(_Auditable, Base):
    """Contacto del proveedor."""

    __tablename__ = "proveedores_contactos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_proveedores.id"), nullable=False)
    oficina_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_oficinas.id"), nullable=True)
    nombre = Column(String(150), nullable=False)
    apellido = Column(String(100), nullable=True)
    cargo = Column(String(150), nullable=True)
    telefono = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    es_principal = Column(Boolean, nullable=False, default=False)
    notas = Column(String(500), nullable=True)

    proveedor = relationship("RegistroProveedor", foreign_keys=[proveedor_id])
    oficina = relationship("ProveedorOficina", foreign_keys=[oficina_id])

    __table_args__ = (
        Index("ix_proveedores_contactos_proveedor", "proveedor_id"),
        Index(
            "uq_proveedores_contacto_principal",
            "proveedor_id",
            unique=True,
            postgresql_where=text("es_principal AND deleted_at IS NULL"),
        ),
    )


class ProveedorDocumento(_Auditable, Base):
    """
    Documento del proveedor (pestaña Documentos). En el bucket va con un UUID:
    {empresa_id}/proveedores/{proveedor_id}/{uuid}{ext}; en pantalla y al descargar,
    con el nombre original. La miniatura es un PNG al lado: {uuid}-miniatura.png.
    """

    __tablename__ = "proveedores_documentos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_proveedores.id"), nullable=False)
    nombre = Column(String(255), nullable=False)  # el original
    clave = Column(String(500), nullable=False)  # en el storage
    tipo_mime = Column(String(100), nullable=False)
    tamano = Column(Integer, nullable=False)  # bytes
    miniatura_clave = Column(String(500), nullable=True)  # NULL = sin miniatura: se muestra el ícono del tipo

    proveedor = relationship("RegistroProveedor", foreign_keys=[proveedor_id])

    __table_args__ = (Index("ix_proveedores_documentos_proveedor", "proveedor_id"),)


# ─── Evaluación ─────────────────────────────────────────────────────────────────

# Checks de la auto-generación (también los usa la migración)
CHECK_AUTO_RANGOS = (
    "auto_inicio_dia BETWEEN 1 AND 31 AND auto_fin_dia BETWEEN 1 AND 31 "
    "AND auto_inicio_mes BETWEEN 1 AND 12 AND auto_fin_mes BETWEEN 1 AND 12"
)
CHECK_AUTO_COMPLETA = (
    "NOT auto_generar OR (auto_inicio_dia IS NOT NULL AND auto_inicio_mes IS NOT NULL "
    "AND auto_fin_dia IS NOT NULL AND auto_fin_mes IS NOT NULL)"
)


class ProveedoresConfiguracion(Base):
    """Configuración global del submódulo de evaluaciones: una fila por empresa (D-64)."""

    __tablename__ = "proveedores_configuracion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False, unique=True)
    sheet_url = Column(String(500), nullable=True)
    sheet_hoja = Column(String(100), nullable=False, default="Listado Proveedores")
    # Avisos (D-66): todo arranca apagado
    recordar_cada_dias = Column(SmallInteger, nullable=True)  # NULL = sin recordatorio periódico
    aviso_apertura = Column(Boolean, nullable=False, default=False)
    aviso_previo_cierre = Column(Boolean, nullable=False, default=False)
    hora_envio = Column(Time, nullable=False, server_default=text("'09:00'"))  # hora Argentina
    canal_email = Column(Boolean, nullable=False, default=False)  # al email_corporativo del referente
    email_cc = Column(Text, nullable=True)  # direcciones separadas por coma
    canal_webex_personal = Column(Boolean, nullable=False, default=False)
    canal_webex_canal = Column(Boolean, nullable=False, default=False)
    webex_room_id = Column(String(255), nullable=True)
    # Auto-generación anual (pestaña propia), apagada de entrada. El período es el año en curso;
    # inicio y fin, día y mes sin año. auto_ultimo_periodo: el año que la tarea ya resolvió
    # (creó la evaluación o la salteó), para que lo haga una sola vez por año.
    auto_generar = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    auto_inicio_dia = Column(SmallInteger, nullable=True)
    auto_inicio_mes = Column(SmallInteger, nullable=True)
    auto_fin_dia = Column(SmallInteger, nullable=True)
    auto_fin_mes = Column(SmallInteger, nullable=True)
    auto_ultimo_periodo = Column(String(20), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (
        CheckConstraint("recordar_cada_dias IN (1, 2)", name="ck_proveedores_config_recordar"),
        CheckConstraint("NOT canal_webex_canal OR webex_room_id IS NOT NULL", name="ck_proveedores_config_room"),
        CheckConstraint(CHECK_AUTO_RANGOS, name="ck_proveedores_config_auto_rangos"),
        CheckConstraint(CHECK_AUTO_COMPLETA, name="ck_proveedores_config_auto"),
    )


class EvaluacionProveedores(_Auditable, Base):
    """
    Campaña de evaluación (D-65). «Activa» no se guarda: es la vigente
    (reemplazada_at NULL) mientras hoy <= fecha_cierre (D-74); se evalúa si
    además hoy >= fecha_apertura. «Hoy» en hora Argentina.
    """

    __tablename__ = "proveedores_evaluaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    periodo = Column(String(20), nullable=False)  # '2026'
    fecha_apertura = Column(Date, nullable=False)
    fecha_cierre = Column(Date, nullable=False)  # ampliable mientras sea la vigente
    reemplazada_at = Column(DateTime, nullable=True)  # se completa al crear la siguiente

    __table_args__ = (
        CheckConstraint("fecha_cierre >= fecha_apertura", name="ck_proveedores_evaluacion_fechas"),
        Index(
            "uq_proveedores_evaluacion_vigente",
            "empresa_id",
            unique=True,
            postgresql_where=text("reemplazada_at IS NULL AND deleted_at IS NULL"),
        ),
        Index(
            "uq_proveedores_evaluacion_periodo",
            "empresa_id",
            "periodo",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


# Expresión de con_hallazgo: la usa también la migración que sacó el checklist
HALLAZGO = "COALESCE(incidentes = 'Si', FALSE) OR COALESCE(mal_manejo = 'Si', FALSE)"


class EvaluacionItem(_Auditable, Base):
    """Un proveedor dentro de una evaluación, con su evaluador fijo y sus respuestas."""

    __tablename__ = "proveedores_evaluacion_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_evaluaciones.id"), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_proveedores.id"), nullable=False)
    # Solo él evalúa (D-72); NULL = sin definir
    evaluador_empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)
    incidentes = Column(String(5), nullable=True)
    mal_manejo = Column(String(5), nullable=True)
    # Evidencia de cada respuesta (links o texto): obligatoria con «Si», vacía si no
    evidencia_incidentes = Column(Text, nullable=True)
    evidencia_mal_manejo = Column(Text, nullable=True)
    con_hallazgo = Column(Boolean, Computed(HALLAZGO, persisted=True))
    evaluado_at = Column(DateTime, nullable=True)  # NULL = pendiente
    evaluado_por = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)

    evaluacion = relationship("EvaluacionProveedores", foreign_keys=[evaluacion_id])
    proveedor = relationship("RegistroProveedor", foreign_keys=[proveedor_id])
    evaluador = relationship("Empleado", foreign_keys=[evaluador_empleado_id])

    __table_args__ = (
        CheckConstraint(_en("incidentes", OPCIONES_INCIDENTES), name="ck_proveedores_item_incidentes"),
        CheckConstraint(_en("mal_manejo", OPCIONES_MAL_MANEJO), name="ck_proveedores_item_mal_manejo"),
        Index(
            "uq_proveedores_item_evaluacion_proveedor",
            "evaluacion_id",
            "proveedor_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_proveedores_item_evaluador", "evaluacion_id", "evaluador_empleado_id"),
    )


# ─── Vista previa de la importación (temporal) ─────────────────────────────────
# Se borra al confirmar o cancelar; las abandonadas se limpian en la importación
# siguiente. UNLOGGED: no pasa por el WAL; si Postgres se cae, se vacía.


class ImportacionProveedores(Base):
    __tablename__ = "proveedores_importaciones"
    __table_args__ = {"prefixes": ["UNLOGGED"]}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_evaluaciones.id"), nullable=False)
    creada_at = Column(DateTime, nullable=False, default=utc_now)
    creada_por = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)

    filas = relationship(
        "ImportacionFila",
        back_populates="importacion",
        order_by="ImportacionFila.fila_sheet",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ImportacionFila(Base):
    __tablename__ = "proveedores_importacion_filas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    importacion_id = Column(
        UUID(as_uuid=True), ForeignKey("proveedores_importaciones.id", ondelete="CASCADE"), nullable=False
    )
    fila_sheet = Column(Integer, nullable=False)
    nombre = Column(String(200), nullable=False)
    referente_sheet = Column(String(200), nullable=True)  # para mostrar por qué quedó sin definir
    accion = Column(String(20), nullable=False)
    proveedor_id = Column(UUID(as_uuid=True), nullable=True)  # el existente; NULL en altas
    referente_anterior_id = Column(UUID(as_uuid=True), nullable=True)
    referente_nuevo_id = Column(UUID(as_uuid=True), nullable=True)  # NULL = sin coincidencia en nómina
    servicio_provisto = Column(Text, nullable=True)  # datos del Sheet, para las altas
    tipo_informacion = Column(Text, nullable=True)
    acuerdo_servicio = Column(String(5), nullable=True)
    politica_nda = Column(Text, nullable=True)
    confirmar = Column(Boolean, nullable=False, default=True)  # el check de los cambios de referente (D-73)
    motivo = Column(Text, nullable=True)  # por qué se rechaza un alta (le faltan datos obligatorios)

    importacion = relationship("ImportacionProveedores", back_populates="filas")

    __table_args__ = (
        CheckConstraint(
            "accion IN ('alta', 'sin_cambios', 'cambio_referente', 'rechazada')",
            name="ck_proveedores_importacion_accion",
        ),
        Index("ix_proveedores_importacion_filas", "importacion_id"),
        {"prefixes": ["UNLOGGED"]},
    )


# ─── Auditoría y avisos ─────────────────────────────────────────────────────────

ENTIDADES_AUDITORIA = ("proveedor", "contacto", "oficina", "documento", "configuracion", "evaluacion", "item", "aviso")


class ProveedoresAuditoria(Base):
    """Auditoría append-only del módulo (D-67): la app no actualiza ni borra filas."""

    __tablename__ = "proveedores_auditoria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    fecha_hora = Column(DateTime, nullable=False, default=utc_now)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)  # NULL = job
    usuario_email = Column(String(255), nullable=True)
    ip = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    entidad = Column(String(20), nullable=False)
    entidad_id = Column(UUID(as_uuid=True), nullable=False)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_evaluaciones.id"), nullable=True)
    accion = Column(String(30), nullable=False)
    antes = Column(JSONB, nullable=True)
    despues = Column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(_en("entidad", ENTIDADES_AUDITORIA), name="ck_proveedores_auditoria_entidad"),
        Index("ix_proveedores_auditoria_entidad", "entidad", "entidad_id", "fecha_hora"),
        Index("ix_proveedores_auditoria_evaluacion", "evaluacion_id", "fecha_hora"),
    )


MOTIVOS_AVISO = ("apertura", "recordatorio", "previo_cierre", "manual")
CANALES_AVISO = ("email", "webex_personal", "webex_canal")


class ProveedoresAviso(Base):
    """Un envío de aviso por canal. El job no repite el mismo aviso en el día."""

    __tablename__ = "proveedores_avisos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    evaluacion_id = Column(UUID(as_uuid=True), ForeignKey("proveedores_evaluaciones.id"), nullable=False)
    fecha_hora = Column(DateTime, nullable=False, default=utc_now)
    fecha_local = Column(Date, nullable=False)  # día en hora Argentina
    motivo = Column(String(15), nullable=False)
    canal = Column(String(15), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)  # NULL en canal
    destino = Column(String(255), nullable=False)  # email o room de Webex
    cc = Column(Text, nullable=True)
    pendientes = Column(Integer, nullable=False)
    enviado = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)
    enviado_por = Column(UUID(as_uuid=True), ForeignKey("core_usuarios.id"), nullable=True)  # NULL = job

    __table_args__ = (
        CheckConstraint(_en("motivo", MOTIVOS_AVISO), name="ck_proveedores_aviso_motivo"),
        CheckConstraint(_en("canal", CANALES_AVISO), name="ck_proveedores_aviso_canal"),
        Index(
            "uq_proveedores_aviso_diario",
            "evaluacion_id",
            "motivo",
            "canal",
            func.coalesce(text("empleado_id"), text("'00000000-0000-0000-0000-000000000000'::uuid")),
            "fecha_local",
            unique=True,
            postgresql_where=text("enviado AND motivo <> 'manual'"),
        ),
    )
