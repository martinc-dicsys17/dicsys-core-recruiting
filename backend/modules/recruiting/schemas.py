"""Esquemas Pydantic del módulo Recruiting.

Los del Dashboard (GET /recruiting/dashboard), el Manager Dashboard y Candidatos. Siguen el contrato de la API del Core
(docs/Arquitectura-Backend.md): todo tipado, sin diccionarios sueltos.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from backend.core.paginacion import Pagina


class RecruitingDashboardKpis(BaseModel):
    """Las cinco tarjetas de indicadores del Dashboard."""

    busquedas_activas: int = Field(0, description="Búsquedas activas en estado Abierta o Pre-ingreso")
    total_candidatos: int = Field(0, description="Candidatos activos del banco de talento")
    postulaciones_en_proceso: int = Field(0, description="Candidatos en estado 'En proceso' dentro de una búsqueda")
    skills_catalogo: int = Field(0, description="Skills activas del catálogo")
    habilidades_catalogo: int = Field(0, description="Habilidades activas del catálogo")


class RecruitingDashboardAviso(BaseModel):
    """Un aviso o novedad del panel 'Avisos & Novedades'."""

    id: str
    tipo: Literal["busqueda_sin_candidatos", "transicion", "candidato_nuevo"]
    titulo: str
    descripcion: str
    tiempo: Optional[str] = Field(None, description="Texto corto para mostrar: antigüedad o fecha y hora (UTC-3)")
    icono: str
    color: str
    enlace: str = Field(..., description="Pantalla de Recruiting a la que remite el aviso")
    created_at: Optional[datetime] = None


class RecruitingDashboardResumen(BaseModel):
    """El bloque 'Eficiencia y Dinámica de Procesos'."""

    tasa_candidatos_proceso: float = Field(0, description="Postulaciones en proceso sobre el total de candidatos, en %")
    busquedas_totales: int = Field(0, description="Búsquedas activas en cualquier estado")


class RecruitingDashboard(BaseModel):
    """Respuesta de GET /recruiting/dashboard."""

    kpis: RecruitingDashboardKpis
    avisos: List[RecruitingDashboardAviso] = Field(default_factory=list)
    resumen_operativo: RecruitingDashboardResumen


# ---------------------------------------------------------------------------
# Manager Dashboard (GET /recruiting/manager-dashboard): desempeño de usuarios EXTERNOS, solo administradores.
# Mismos campos que el módulo original; los diccionarios sueltos de allá (filtros, umbrales) son modelos tipados.
# ---------------------------------------------------------------------------


class ManagerDashboardFiltros(BaseModel):
    """Filtros y umbrales del Manager Dashboard. Los umbrales son configurables: el sistema no define objetivos."""

    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    tipo: Literal["todos", "freelance", "consultora"] = "todos"
    usuario_ids: List[uuid.UUID] = Field(default_factory=list)
    oportunidad_id: Optional[uuid.UUID] = None
    dias_estancado: int = Field(7, ge=1, le=365)
    umbral_volumen: int = Field(10, ge=1, le=100000)
    umbral_tasa_avance: float = Field(20.0, ge=0, le=100)
    umbral_actividad: int = Field(1, ge=1, le=100000)
    umbral_demora_dias: float = Field(3.0, ge=0, le=365)


class MDFiltrosAplicados(BaseModel):
    fecha_desde: Optional[date] = None
    fecha_hasta: Optional[date] = None
    tipo: str
    usuario_ids: List[uuid.UUID] = Field(default_factory=list)
    oportunidad_id: Optional[uuid.UUID] = None


class MDUmbrales(BaseModel):
    dias_estancado: int
    umbral_volumen: int
    umbral_tasa_avance: float
    umbral_actividad: int
    umbral_demora_dias: float


class MDEtapaCantidad(BaseModel):
    etapa: str
    cantidad: int
    porcentaje: Optional[float] = None


class MDMotivoDescarte(BaseModel):
    motivo: str
    cantidad: int


class MDPuntoEvolucion(BaseModel):
    periodo: str
    presentados: int
    avanzaron: int


class MDTiempoEstadistica(BaseModel):
    cantidad: int
    promedio_dias: Optional[float] = None
    mediana_dias: Optional[float] = None


class MDTransicionTiempo(MDTiempoEstadistica):
    desde: str
    hasta: str


class MDBusquedaResultado(BaseModel):
    oportunidad_id: uuid.UUID
    titulo: str
    codigo: Optional[str] = None
    cliente: Optional[str] = None
    presentados: int
    avanzaron: int
    entrevista: int
    finales: int
    contratados: int
    descartados: int


class MDResumen(BaseModel):
    """Indicadores de un conjunto de postulaciones (candidato + búsqueda). Las tasas usan postulaciones como base."""

    candidatos_unicos: int
    postulaciones: int
    avanzaron: int
    tasa_avance: Optional[float] = None
    entrevista: int
    tasa_entrevista: Optional[float] = None
    finales: int
    tasa_finales: Optional[float] = None
    contratados: int
    tasa_contratados: Optional[float] = None
    descartados: int
    tasa_descartados: Optional[float] = None
    revision: MDTiempoEstadistica
    estancados: int
    embudo: List[MDEtapaCantidad]
    motivos_descarte: List[MDMotivoDescarte]
    evolucion: List[MDPuntoEvolucion]


class MDExterno(MDResumen):
    usuario_id: uuid.UUID
    nombre: str
    email: Optional[str] = None
    tipo: str
    busquedas_asignadas: int
    cuadrante: Optional[str] = None
    por_busqueda: List[MDBusquedaResultado]


class MDEstancado(BaseModel):
    candidato_id: uuid.UUID
    candidato: str
    oportunidad_id: uuid.UUID
    busqueda: str
    usuario_id: uuid.UUID
    externo: str
    etapa_actual: str
    dias_sin_movimiento: int


class MDTiempos(BaseModel):
    revision: MDTiempoEstadistica
    revision_sin_fecha: int
    entre_etapas: List[MDTransicionTiempo]
    hasta_descarte: MDTiempoEstadistica
    hasta_oferta: MDTiempoEstadistica
    hasta_ingreso: MDTiempoEstadistica
    estancados: List[MDEstancado]
    atribucion: str


class MDAlerta(BaseModel):
    tipo: str
    severidad: Literal["alta", "media", "baja"]
    usuario_id: uuid.UUID
    externo: str
    mensaje: str
    seccion: str


class MDOpcionUsuario(BaseModel):
    id: uuid.UUID
    nombre: str
    tipo: str


class MDOpcionBusqueda(BaseModel):
    id: uuid.UUID
    titulo: str
    cliente: Optional[str] = None


class MDNoDisponible(BaseModel):
    indicador: str
    motivo: str


class ManagerDashboard(BaseModel):
    """Respuesta de GET /recruiting/manager-dashboard."""

    filtros: MDFiltrosAplicados
    umbrales: MDUmbrales
    granularidad_evolucion: Literal["dia", "semana"]
    criterios: List[str]
    resumen: MDResumen
    externos: List[MDExterno]
    tiempos: MDTiempos
    alertas: List[MDAlerta]
    opciones_usuarios: List[MDOpcionUsuario]
    opciones_busquedas: List[MDOpcionBusqueda]
    no_disponible: List[MDNoDisponible]


# ---------------------------------------------------------------------------
# Candidatos
# ---------------------------------------------------------------------------


def _fecha_flexible(valor):
    """Fecha de nacimiento tolerante, como la cargan el formulario y la extracción de CV: acepta AAAA-MM-DD, DD/MM/AAAA,
    DD-MM-AAAA y ISO con hora; un valor vacío o que no se reconoce queda en None (no se rechaza la ficha por eso)."""
    if isinstance(valor, datetime):
        return valor.date()
    if valor is None or isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto or texto.lower() in {"-", "--", "—", "null", "none", "undefined"}:
        return None
    if "T" in texto or " " in texto:
        texto = texto.split("T")[0].split(" ")[0].strip()
    dia_primero = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", texto)
    anio_primero = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", texto)
    try:
        if dia_primero:
            d, m, a = dia_primero.groups()
            return date(int(a), int(m), int(d))
        if anio_primero:
            a, m, d = anio_primero.groups()
            return date(int(a), int(m), int(d))
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _telefono_limpio(valor: Optional[str]) -> Optional[str]:
    limpio = str(valor).strip() if valor else ""
    return limpio or None


class CandidatoBase(BaseModel):
    """Campos que comparten el alta y la edición de un candidato."""

    telefono: Optional[str] = Field(None, max_length=50)
    ubicacion: Optional[str] = Field(None, max_length=255)
    provincia_id: Optional[int] = Field(None, ge=1, description="Provincia del catálogo de Parámetros")
    ciudad_id: Optional[int] = Field(None, ge=1, description="Ciudad del catálogo; debe ser de la provincia elegida")
    dni: Optional[str] = Field(None, max_length=50)
    fecha_nacimiento: Optional[date] = None
    linkedin_url: Optional[str] = Field(None, max_length=500)
    cv_url: Optional[str] = Field(None, max_length=500)
    headline: Optional[str] = Field(None, max_length=255, description="Perfil de puesto del candidato")
    seniority: Optional[str] = Field(None, max_length=50)
    modalidad: Optional[str] = Field(None, max_length=50)
    pretension_salarial: Optional[Decimal] = Field(None, ge=0)
    moneda: Optional[str] = Field(None, max_length=10)
    moneda_pretension: Optional[str] = Field(None, max_length=10)

    @field_validator("fecha_nacimiento", mode="before")
    @classmethod
    def _validar_fecha_nacimiento(cls, valor):
        return _fecha_flexible(valor)

    @field_validator("telefono")
    @classmethod
    def _validar_telefono(cls, valor: Optional[str]) -> Optional[str]:
        return _telefono_limpio(valor)


class CandidatoCreate(CandidatoBase):
    """Alta de un candidato."""

    nombre: str = Field(..., min_length=1, max_length=100)
    apellido: Optional[str] = Field("", max_length=100)
    email: EmailStr
    skills: Optional[List[str]] = Field(default_factory=list)
    habilidades: Optional[List[str]] = Field(default_factory=list)
    moneda: Optional[str] = Field("ARS", max_length=10)
    estado: Optional[str] = Field("Activo", max_length=50)
    fuente: Optional[str] = Field("Portal Propio", max_length=100)


class CandidatoUpdate(CandidatoBase):
    """Edición de un candidato: solo se modifican los campos que llegan."""

    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    skills: Optional[List[str]] = None
    habilidades: Optional[List[str]] = None
    estado: Optional[str] = Field(None, max_length=50)
    fuente: Optional[str] = Field(None, max_length=100)


class CandidatoResponse(BaseModel):
    """Un candidato del Banco de Talentos."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    codigo: Optional[str] = None
    empresa_id: str
    nombre: str
    apellido: str
    email: str
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    provincia_id: Optional[int] = None
    ciudad_id: Optional[int] = None
    dni: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    linkedin_url: Optional[str] = None
    cv_url: Optional[str] = None
    headline: Optional[str] = None
    seniority: Optional[str] = None
    modalidad: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    habilidades: List[str] = Field(default_factory=list)
    pretension_salarial: Optional[float] = None
    moneda: Optional[str] = "ARS"
    moneda_pretension: Optional[str] = "ARS"
    estado: str
    activo: bool = True
    fuente: Optional[str] = "Portal Propio"
    creador_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tiene_pipeline: bool = False

    @classmethod
    def from_model(cls, obj) -> "CandidatoResponse":
        moneda = getattr(obj, "moneda", None) or getattr(obj, "moneda_pretension", None) or "ARS"
        habilidades = getattr(obj, "habilidades", None)
        return cls(
            id=str(obj.id),
            codigo=obj.codigo,
            empresa_id=str(obj.empresa_id),
            nombre=obj.nombre,
            apellido=obj.apellido or "",
            email=obj.email,
            telefono=obj.telefono,
            ubicacion=obj.ubicacion,
            provincia_id=obj.provincia_id,
            ciudad_id=obj.ciudad_id,
            dni=obj.dni,
            fecha_nacimiento=obj.fecha_nacimiento,
            linkedin_url=obj.linkedin_url,
            cv_url=obj.cv_url,
            headline=obj.headline,
            seniority=obj.seniority,
            modalidad=obj.modalidad,
            skills=obj.skills if isinstance(obj.skills, list) else [],
            habilidades=habilidades if isinstance(habilidades, list) else [],
            pretension_salarial=float(obj.pretension_salarial) if obj.pretension_salarial is not None else None,
            moneda=moneda,
            moneda_pretension=moneda,
            estado=obj.estado,
            activo=bool(obj.activo) and obj.deleted_at is None,
            fuente=obj.fuente,
            creador_id=str(obj.creador_id) if obj.creador_id else None,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class CandidatoPagina(Pagina[CandidatoResponse]):
    """Página del listado de candidatos."""


class CandidatoEliminado(BaseModel):
    ok: bool = True
    mensaje: str


class CargaCVResponse(BaseModel):
    """Candidato creado o actualizado desde un CV."""

    ok: bool = True
    candidato: CandidatoResponse


class ComparacionCV(BaseModel):
    """Datos de un CV, como se muestran en el modal que compara el actual con el nuevo."""

    nombre: Optional[str] = None
    apellido: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    dni: Optional[str] = None
    headline: Optional[str] = None
    seniority: Optional[str] = None
    modalidad: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    archivo: Optional[str] = None
    cv_url: Optional[str] = None


class CargaCVDuplicadoResponse(BaseModel):
    """409 de la carga individual: ya existe un candidato con ese email y el CV es distinto. No se guardó nada: el
    usuario compara ambos y elige si actualiza la ficha."""

    ok: bool = False
    requiere_comparacion: bool = True
    error: str
    actual: ComparacionCV
    nuevo: ComparacionCV


class CargaMasivaResumen(BaseModel):
    """Conteo por categoría de un lote: cada archivo suma en una sola."""

    lote_id: str
    total_archivos: int = 0
    creados: int = 0
    duplicados_omitidos: int = 0
    sin_email: int = 0
    rechazados_formato_tamano: int = 0
    errores_lectura: int = 0
    errores_validacion: int = 0
    errores_persistencia: int = 0
    errores_otros: int = 0


class CargaMasivaArchivo(BaseModel):
    """Resultado de un archivo del lote."""

    archivo: str
    resultado: str
    mensaje: str
    email: Optional[str] = None
    candidato_id: Optional[str] = None


class CargaMasivaReporte(BaseModel):
    ok: bool = True
    lote_id: str
    resumen: CargaMasivaResumen
    resultados: List[CargaMasivaArchivo] = Field(default_factory=list)


class CargaMasivaFallido(BaseModel):
    archivo: str
    motivo: str


class CargaMasivaResponse(BaseModel):
    """Resultado de la carga masiva sincrónica. Siempre 200: un problema del lote (formato, límite, error interno) llega
    con `ok` en False y el motivo en `errores`, nunca como 500. Los campos repetidos son los que ya consumía el
    módulo original."""

    ok: bool
    lote_id: Optional[str] = None
    resumen: Optional[CargaMasivaResumen] = None
    resultados: List[CargaMasivaArchivo] = Field(default_factory=list)
    procesados: int = 0
    creados: int = 0
    total_encontrados: int = 0
    errores: List[CargaMasivaFallido] = Field(default_factory=list)
    total_archivos_encontrados: int = 0
    procesados_exitosamente: int = 0
    fallidos: List[CargaMasivaFallido] = Field(default_factory=list)
    candidatos_creados: List[CandidatoResponse] = Field(default_factory=list)


class LoteCargaMasivaResponse(BaseModel):
    """Avance de una carga masiva en segundo plano; `reporte` llega solo cuando terminó (o se canceló)."""

    lote_id: str
    estado: str = Field(description="preparando, procesando, finalizado, cancelado o error")
    procesados: int = 0
    total: int = 0
    reporte: Optional[CargaMasivaReporte] = None
    error: Optional[str] = None


class SkillCatalogoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    categoria: Optional[str] = None
    sinonimos: List[str] = Field(default_factory=list)
    activo: bool = True

    @field_validator("id", mode="before")
    @classmethod
    def _id_texto(cls, valor):
        return str(valor) if isinstance(valor, uuid.UUID) else valor

    @field_validator("sinonimos", mode="before")
    @classmethod
    def _sin_nulos(cls, valor):
        return [] if valor is None else valor


class NivelSeniorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str


class ProvinciaResponse(BaseModel):
    provincia_id: int
    nombre: str
    cantidad_ciudades: int = 0


class CiudadResponse(BaseModel):
    ciudad_id: int
    nombre: str
    provincia_id: int
    provincia_nombre: Optional[str] = None


class PermisosCandidatos(BaseModel):
    """Acciones de Candidatos que la interfaz muestra u oculta; el backend las valida igual en cada endpoint."""

    puede_eliminar_candidatos: bool
    puede_cargar_cv_general: bool
    puede_carga_masiva: bool
    puede_asignar_candidatos: bool


# ---------------------------------------------------------------------------
# Búsquedas (oportunidades): recruiting_oportunidades
# ---------------------------------------------------------------------------


def lista_de_textos(valor) -> List[str]:
    """Skills y habilidades se guardan como JSON: siempre una lista de textos sin vacíos."""
    if isinstance(valor, str):
        valor = valor.split(",")
    if not isinstance(valor, list):
        return []
    return [texto for texto in (str(v).strip() for v in valor) if texto]


def _tipo_de_busqueda(valor: Optional[str]) -> Optional[str]:
    """Potencial o Efectiva, sin distinguir mayúsculas; vacío = sin valor (el servicio pone el predeterminado)."""
    texto = (valor or "").strip()
    if not texto:
        return None
    if texto.casefold() in ("potencial", "efectiva"):
        return texto.capitalize()
    raise ValueError("El tipo de búsqueda debe ser «Potencial» o «Efectiva»")


class OportunidadCreate(BaseModel):
    """Alta de una búsqueda. La fecha de creación y la de asignación las fija siempre el backend."""

    id_busqueda: Optional[str] = Field(None, max_length=50)
    cliente: str = Field(..., min_length=2, max_length=150)
    titulo: str = Field(..., min_length=2, max_length=200)
    estado: str = Field("Abierta", max_length=50)
    recruiter_nombre: Optional[str] = Field(None, max_length=150)
    lider_nombre: Optional[str] = Field(None, max_length=150)
    area: Optional[str] = Field("Operaciones / IT", max_length=150)
    puesto: Optional[str] = Field(None, max_length=150, description="Perfil de puesto del catálogo")
    seniority: Optional[str] = Field("Senior", max_length=50)
    modalidad: Optional[str] = Field("Remoto", max_length=50)
    vacantes: Optional[int] = Field(1, ge=1)
    rango: Optional[str] = Field(None, max_length=100)
    prioridad: Optional[str] = Field("Alta", max_length=50)
    tipo: Optional[str] = Field("Efectiva", max_length=50, description="Potencial o Efectiva")
    skills: List[str] = Field(default_factory=list)
    habilidades: List[str] = Field(default_factory=list)
    skills_deseadas: List[str] = Field(default_factory=list)
    descripcion: Optional[str] = Field(None, max_length=10000)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v):
        return _tipo_de_busqueda(v)

    @field_validator("skills", "habilidades", "skills_deseadas", mode="before")
    @classmethod
    def validar_lista(cls, v):
        return lista_de_textos(v)


class OportunidadUpdate(BaseModel):
    """Edición parcial de una búsqueda: solo cambia lo que viene. La fecha de creación nunca se modifica."""

    id_busqueda: Optional[str] = Field(None, max_length=50)
    cliente: Optional[str] = Field(None, min_length=2, max_length=150)
    titulo: Optional[str] = Field(None, min_length=2, max_length=200)
    estado: Optional[str] = Field(None, max_length=50)
    recruiter_nombre: Optional[str] = Field(None, max_length=150)
    lider_nombre: Optional[str] = Field(None, max_length=150)
    area: Optional[str] = Field(None, max_length=150)
    puesto: Optional[str] = Field(None, max_length=150)
    seniority: Optional[str] = Field(None, max_length=50)
    modalidad: Optional[str] = Field(None, max_length=50)
    vacantes: Optional[int] = Field(None, ge=1)
    rango: Optional[str] = Field(None, max_length=100)
    prioridad: Optional[str] = Field(None, max_length=50)
    tipo: Optional[str] = Field(None, max_length=50)
    skills: Optional[List[str]] = None
    habilidades: Optional[List[str]] = None
    skills_deseadas: Optional[List[str]] = None
    descripcion: Optional[str] = Field(None, max_length=10000)

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v):
        return _tipo_de_busqueda(v)

    @field_validator("skills", "habilidades", "skills_deseadas", mode="before")
    @classmethod
    def validar_lista(cls, v):
        return None if v is None else lista_de_textos(v)


class OportunidadResponse(BaseModel):
    """Una búsqueda con sus contadores del Pipeline y el usuario externo asignado."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    empresa_id: str
    id_busqueda: str
    cliente: str
    titulo: str
    estado: str
    recruiter_nombre: Optional[str] = None
    lider_nombre: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None
    fecha_creacion: Optional[date] = None
    dias_abierta: int = 0
    dias_reclutador: Optional[int] = None
    area: Optional[str] = None
    puesto: Optional[str] = None
    seniority: Optional[str] = None
    modalidad: Optional[str] = None
    vacantes: int = 1
    rango: Optional[str] = None
    prioridad: Optional[str] = None
    tipo: str = "Efectiva"
    skills: List[str] = Field(default_factory=list)
    habilidades: List[str] = Field(default_factory=list)
    skills_deseadas: List[str] = Field(default_factory=list)
    descripcion: Optional[str] = None
    candidatos_pipeline: int = 0
    coordinando_entrevista: int = 0
    entrevistados_rrhh: int = 0
    presentacion_lider: int = 0
    feedback_lider: int = 0
    presentacion_cliente: int = 0
    q_activos: int = 0
    creador_id: Optional[str] = None
    recruiter_id: Optional[str] = None
    lider_id: Optional[str] = None
    externo_id: Optional[str] = None
    externo_nombre: Optional[str] = None
    externo_email: Optional[str] = None
    activo: bool = True
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, obj) -> "OportunidadResponse":
        def id_texto(valor):
            return str(valor) if valor else None

        externo = obj.externo_rel if obj.externo_id else None
        return cls(
            id=str(obj.id),
            empresa_id=str(obj.empresa_id),
            id_busqueda=obj.id_busqueda or str(obj.id)[:8],
            cliente=obj.cliente,
            titulo=obj.titulo,
            estado=obj.estado,
            recruiter_nombre=obj.recruiter_nombre,
            lider_nombre=obj.lider_nombre,
            fecha_asignacion=obj.fecha_asignacion,
            fecha_creacion=obj.fecha_creacion,
            dias_abierta=obj.dias_abierta,
            dias_reclutador=obj.dias_reclutador,
            area=obj.area,
            puesto=obj.puesto,
            seniority=obj.seniority,
            modalidad=obj.modalidad,
            vacantes=int(obj.vacantes or 1),
            rango=obj.rango,
            prioridad=obj.prioridad,
            tipo=obj.tipo or "Efectiva",
            skills=lista_de_textos(obj.skills),
            habilidades=lista_de_textos(obj.habilidades),
            skills_deseadas=lista_de_textos(obj.skills_deseadas),
            descripcion=obj.descripcion,
            candidatos_pipeline=int(obj.candidatos_pipeline or 0),
            coordinando_entrevista=int(obj.coordinando_entrevista or 0),
            entrevistados_rrhh=int(obj.entrevistados_rrhh or 0),
            presentacion_lider=int(obj.presentacion_lider or 0),
            feedback_lider=int(obj.feedback_lider or 0),
            presentacion_cliente=int(obj.presentacion_cliente or 0),
            q_activos=int(obj.q_activos or 0),
            creador_id=id_texto(obj.creador_id),
            recruiter_id=id_texto(obj.recruiter_id),
            lider_id=id_texto(obj.lider_id),
            externo_id=id_texto(obj.externo_id),
            externo_nombre=" ".join(filter(None, [externo.nombre, externo.apellido])) if externo else None,
            externo_email=externo.email if externo else None,
            activo=obj.activo,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class OportunidadPagina(Pagina[OportunidadResponse]):
    """Página del listado de búsquedas."""


class AsignarReclutadorRequest(BaseModel):
    """Reclutador responsable de una búsqueda: un nombre activo del catálogo de Reclutadores."""

    recruiter_nombre: str = Field(..., min_length=1, max_length=150)


class AsignarExternoRequest(BaseModel):
    """Usuario externo (grupo EXTERNOS) que se asigna a una búsqueda."""

    externo_id: uuid.UUID


class ExternoDisponibleResponse(BaseModel):
    id: str
    nombre: str
    email: str


class PersonaCatalogoResponse(BaseModel):
    """Un líder o un reclutador del catálogo de Recruiting (para los combos del formulario)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    nombre: str
    activo: bool = True

    @field_validator("id", mode="before")
    @classmethod
    def id_a_texto(cls, v):
        return str(v)


class PermisosBusquedas(BaseModel):
    """Acciones de Búsquedas que la interfaz muestra u oculta; el backend las valida igual en cada endpoint."""

    puede_crear_busquedas: bool
    puede_eliminar_busquedas: bool
    puede_ver_lider_tipo_fecha_busqueda: bool
    puede_ver_smart_matching: bool
    puede_asignar_candidatos: bool
    puede_asignar_reclutador: bool
    puede_administrar_externos: bool
    es_externo: bool


class ConfigSmartMatching(BaseModel):
    """Umbral mínimo de coincidencia de Smart Matching de la empresa (por defecto 50)."""

    match_minimo_porcentaje: int


class CandidatoEnBusqueda(BaseModel):
    """Un candidato en el pipeline de una búsqueda (recruiting_gestionBusqueda + recruiting_candidatos). Para un
    usuario del grupo EXTERNOS los candidatos que no presentó salen anónimos (OcultadorCandidatosEnBusqueda)."""

    id: str
    gestion_id: str
    candidato_id: str
    oportunidad_id: str
    codigo: Optional[str] = None
    nombre: str
    nombre_pila: Optional[str] = None
    apellido: str
    email: str
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    headline: Optional[str] = None
    seniority: Optional[str] = None
    etapa: str
    etapa_actual: str
    estado: str
    motivo_descarte: Optional[str] = None
    feedback_etapa: Optional[str] = None
    pretension_salarial_bruta_ars: Optional[int] = None
    fecha_cambio_etapa: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    cv_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    es_anonimo: bool = False
    es_externo: bool = False
    presentado_por: Optional[str] = None


class CandidatoCompatible(BaseModel):
    """Candidato sugerido por Smart Matching para una búsqueda, con su porcentaje de coincidencia."""

    id: str
    codigo: Optional[str] = None
    nombre: str
    apellido: str
    nombre_completo: str
    email: str
    headline: Optional[str] = None
    seniority: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    habilidades: List[str] = Field(default_factory=list)
    skills_coincidentes: List[str] = Field(default_factory=list)
    habilidades_coincidentes: List[str] = Field(default_factory=list)
    porcentaje_match: int = 0
    match_porcentaje: int = 0
    ya_asignado: bool = False


class AsignarCandidatoRequest(BaseModel):
    """Candidato que se suma a una búsqueda, con la etapa y el estado iniciales."""

    candidato_id: uuid.UUID
    etapa: Optional[str] = Field("Coordinando entrevista", max_length=50)
    estado: Optional[str] = Field("En proceso", max_length=50)
    observaciones: Optional[str] = Field(None, max_length=1000)


class AsignacionCandidatoResponse(BaseModel):
    """La postulación creada al sumar un candidato a una búsqueda."""

    id: str
    candidato_id: str
    solicitud_id: Optional[str] = None
    etapa: Optional[str] = None
    estado: str
    fecha_asignacion: Optional[datetime] = None


class DesvinculacionCandidatoResponse(BaseModel):
    ok: bool = True
    mensaje: str
    candidato_id: str
    oportunidad_id: str


# ---------------------------------------------------------------------------
# Pipeline (ítem «gestion_busquedas»)
# ---------------------------------------------------------------------------


class PermisosPipeline(BaseModel):
    """Acciones del Pipeline y de las pantallas vecinas que la interfaz muestra u oculta (False para el grupo EXTERNOS,
    salvo cargar CV en una búsqueda). El backend las valida igual en cada endpoint."""

    puede_mover_descartar: bool
    puede_eliminar_candidatos: bool
    puede_asignar_candidatos: bool
    puede_crear_busquedas: bool
    puede_eliminar_busquedas: bool
    puede_ver_lider_tipo_fecha_busqueda: bool
    puede_ver_smart_matching: bool
    puede_cargar_cv_general: bool
    puede_cargar_cv_en_busqueda: bool


class ContadoresEtapas(BaseModel):
    """Candidatos vigentes de una búsqueda por etapa del pipeline. `total` no incluye a los descartados."""

    total: int
    por_etapa: dict[str, int]


class PipelineColumnaGlobal(BaseModel):
    """Columna de la vista global del Pipeline y las etapas reales que agrupa."""

    clave: str
    nombre: str
    etapas: List[str]
    nota: Optional[str] = None


class PipelineResumenItem(BaseModel):
    """Fila de la vista global: candidatos por columna de una búsqueda."""

    id: str
    id_busqueda: Optional[str] = None
    titulo: str
    cliente: Optional[str] = None
    estado: str
    recruiter_nombre: Optional[str] = None
    es_externa: bool = False
    total: int = 0
    columnas: dict[str, int] = Field(default_factory=dict)
    sin_clasificar: int = 0


class PipelineResumen(BaseModel):
    columnas: List[PipelineColumnaGlobal]
    items: List[PipelineResumenItem]


class PipelineColumnaCandidato(BaseModel):
    """Candidato de una búsqueda dentro de una columna de la vista global (detalle emergente)."""

    candidato_id: str
    nombre: Optional[str] = None
    pretension_salarial_bruta_ars: Optional[int] = None
    rol_actual: Optional[str] = None
    seniority: Optional[str] = None
    reclutador: Optional[str] = None
    presentado_por: Optional[str] = None
    es_anonimo: bool = False
    etapa_actual: str


class PipelineDeCandidato(BaseModel):
    """Un pipeline (uno por búsqueda) en el que participa un candidato."""

    gestion_id: str
    oportunidad_id: str
    titulo: str
    cliente: Optional[str] = None
    etapa_actual: str
    estado: str
    pretension_salarial_bruta_ars: Optional[int] = None
    presentado_por: Optional[str] = None


class CambiarEtapaRequest(BaseModel):
    """Mover de etapa, descartar o reingresar a un candidato en el pipeline de una búsqueda."""

    etapa_actual: str = Field(..., min_length=2, max_length=100, description="Etapa destino")
    estado: Optional[str] = Field(None, max_length=50)
    motivo_descarte: Optional[str] = Field(None, description="Obligatorio al descartar")
    feedback_etapa: Optional[str] = Field(None, description="Observación del movimiento")
    pretension_salarial_bruta_ars: Optional[int] = Field(
        None, ge=0, description="Entero en ARS; solo aplica de Entrevista RRHH a Entrevista Líder Dicsys"
    )

    @model_validator(mode="after")
    def validar_largo_feedback_etapa(self):
        """La observación al mover de etapa admite hasta 50 caracteres (el descarte tiene su propio comentario)."""
        feedback = (self.feedback_etapa or "").strip()
        if len(feedback) > 50 and (self.etapa_actual or "").strip().lower() != "descartados":
            raise ValueError("La observación admite un máximo de 50 caracteres.")
        return self

    @field_validator("pretension_salarial_bruta_ars", mode="before")
    @classmethod
    def validar_pretension_entera(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if isinstance(v, bool):
            raise ValueError("La pretensión salarial debe ser un monto entero válido")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isascii() and v.strip().isdigit():
            return int(v.strip())
        if isinstance(v, float) and v.is_integer():
            return int(v)
        raise ValueError("La pretensión salarial debe ser un monto entero válido, sin decimales ni valores negativos")


class CambiarEtapaResponse(BaseModel):
    ok: bool = True
    id: str
    etapa_actual: str
    estado: str
    motivo_descarte: Optional[str] = None
    feedback_etapa: Optional[str] = None
    pretension_salarial_bruta_ars: Optional[int] = None


class EtapaArchivoResponse(BaseModel):
    """Archivo adjunto de una etapa del pipeline."""

    id: str
    busqueda_id: str
    candidato_id: str
    etapa_id: str
    estado: Optional[str] = None
    nombre_archivo: str
    tipo_archivo: str
    tamano: int
    created_at: datetime
    created_by: Optional[str] = None
    download_url: str


class HistorialPipelineItem(BaseModel):
    """Un movimiento del candidato en el pipeline de una búsqueda."""

    id: str
    etapa_anterior: Optional[str] = None
    etapa_nueva: str
    estado_nuevo: Optional[str] = None
    descripcion: Optional[str] = None
    motivo_descarte: Optional[str] = None
    usuario: Optional[str] = None
    created_at: Optional[datetime] = None
    pretension_salarial_bruta_ars: Optional[int] = None


class MotivoDescarteResponse(BaseModel):
    id: int
    motivo: str


class MotivoBlacklistResponse(BaseModel):
    """Motivo de Blacklist del catálogo."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    motivo: str


class PostulacionResponse(BaseModel):
    """Participación de un candidato en una búsqueda."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    empresa_id: str
    candidato_id: str
    solicitud_id: Optional[str] = None
    solicitud_titulo: Optional[str] = None
    solicitud_cliente: Optional[str] = None
    estado: str
    etapa: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None
    fecha_etapa: Optional[datetime] = None
    fecha_rechazo: Optional[datetime] = None
    motivo_rechazo: Optional[str] = None
    observaciones: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    @field_validator("id", "empresa_id", "candidato_id", "solicitud_id", mode="before")
    @classmethod
    def uuid_a_texto(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class RechazoPostulacionRequest(BaseModel):
    motivo_rechazo: str = Field(..., min_length=2, max_length=150)
    observaciones: Optional[str] = Field(None, max_length=1000)


class TransicionEstadoResponse(BaseModel):
    """Un cambio de estado de una postulación del candidato (auditoría)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    candidato_id: str
    postulacion_id: Optional[str] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: str
    motivo_rechazo: Optional[str] = None
    observaciones: Optional[str] = None
    usuario: Optional[str] = None
    created_at: datetime

    @field_validator("id", "candidato_id", "postulacion_id", mode="before")
    @classmethod
    def uuid_a_texto(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v


class BusquedaElegible(BaseModel):
    """Búsqueda Abierta a la que un candidato puede asignarse (coincidencia de skills y seniority)."""

    id: str
    id_busqueda: Optional[str] = None
    titulo: str
    cliente: Optional[str] = None
    seniority: Optional[str] = None
    modalidad: Optional[str] = None
    estado: str = "Abierta"
    skills: List[str] = Field(default_factory=list)
    skills_coincidentes: List[str] = Field(default_factory=list)
    porcentaje_match: int
    match_porcentaje: int
    match_skills: int = 0
    match_seniority: int = 0
    seniority_compatible: bool = True


class AltaEnBusquedaResponse(BaseModel):
    """Candidato dado de alta (o ya registrado) desde la búsqueda asignada de un usuario EXTERNOS y su asociación. El
    código HTTP dice qué pasó: 201 alta, 200 CV idéntico ya registrado (se asoció la ficha existente) y 202 CV distinto
    derivado a Recruiting para su revisión."""

    ok: bool = True
    candidato: CandidatoResponse
    asignacion_id: str
    mensaje: Optional[str] = None


class CasoDuplicado(BaseModel):
    """Un CV distinto cargado con el email de un candidato existente, a la espera de la revisión de Recruiting."""

    id: str
    fecha: datetime
    oportunidad_id: str
    busqueda: Optional[str] = None
    candidato_id: str
    candidato: Optional[str] = None
    email: Optional[str] = None
    presentado_por: Optional[str] = None
    estado: str
    resolucion: Optional[str] = None


class CasoDuplicadoLista(BaseModel):
    items: List[CasoDuplicado]
    total: int


class CasoDuplicadoDetalle(CasoDuplicado):
    """El caso con los datos del CV actual y del nuevo para compararlos."""

    actual: ComparacionCV
    nuevo: ComparacionCV


class ResolverCasoDuplicadoRequest(BaseModel):
    """Conservar el CV actual o actualizar la ficha con el nuevo."""

    accion: Literal["conservar", "actualizar"]


class ResolucionCasoDuplicado(BaseModel):
    ok: bool = True
    resolucion: str
    candidato_id: str


# ---------------------------------------------------------------------------
# Parámetros (ítem «parametros»)
# ---------------------------------------------------------------------------


class ConfigSmartMatchingUpdate(BaseModel):
    """Porcentaje mínimo de coincidencia de skills para que un candidato califique en Smart Matching."""

    match_minimo_porcentaje: int = Field(..., ge=1, le=100)


def _texto_sin_espacios_dobles(valor: Optional[str]) -> Optional[str]:
    if valor is None:
        return None
    limpio = " ".join(valor.split())
    if not limpio:
        raise ValueError("El nombre no puede estar vacío")
    return limpio


def _lista_de_sinonimos(valor):
    """Los sinónimos llegan como lista o como texto separado por comas."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return [s.strip() for s in valor.split(",") if s.strip()]
    if isinstance(valor, list):
        return [str(s).strip() for s in valor if str(s).strip()]
    return []


class DetalleCatalogoCreate(BaseModel):
    """Alta de una skill o una habilidad del catálogo."""

    nombre: str = Field(..., min_length=1, max_length=100)
    categoria: Optional[str] = Field(None, max_length=100)
    sinonimos: List[str] = Field(default_factory=list)
    activo: bool = True

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))
    limpiar_sinonimos = field_validator("sinonimos", mode="before")(lambda cls, v: _lista_de_sinonimos(v) or [])


class DetalleCatalogoUpdate(BaseModel):
    """Edición, activación o desactivación de una skill o una habilidad."""

    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    categoria: Optional[str] = Field(None, max_length=100)
    sinonimos: Optional[List[str]] = None
    activo: Optional[bool] = None

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))
    limpiar_sinonimos = field_validator("sinonimos", mode="before")(lambda cls, v: _lista_de_sinonimos(v))


class NombreCatalogoCreate(BaseModel):
    """Alta de un líder, un reclutador o un perfil profesional."""

    nombre: str = Field(..., min_length=1, max_length=150)
    activo: bool = True

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class NombreCatalogoUpdate(BaseModel):
    """Edición, activación o desactivación de un líder, un reclutador o un perfil profesional."""

    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    activo: Optional[bool] = None

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class PerfilPuestoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    activo: bool = True


class ProvinciaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class ProvinciaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class CiudadCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    provincia_id: int = Field(..., ge=1)

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class CiudadUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=150)
    provincia_id: Optional[int] = Field(None, ge=1)

    limpiar_nombre = field_validator("nombre")(lambda cls, v: _texto_sin_espacios_dobles(v))


class MensajeResponse(BaseModel):
    message: str


class ArchivoCVResponse(BaseModel):
    """Un CV archivado en una de las carpetas de CV (solo lectura)."""

    nombre: str
    tamano_bytes: int
    tamano: str
    modificado: datetime
    motivo_error: Optional[str] = Field(None, description="Resumen para la columna; solo en cv_errores")
    motivo_detalle: Optional[str] = Field(None, description="Explicación completa para el tooltip; solo en cv_errores")


class CarpetaCVResumen(BaseModel):
    """Cantidad de archivos y espacio ocupado de una carpeta de CV archivados."""

    carpeta: str
    cantidad_archivos: int
    tamano_total_bytes: int
    tamano_total: str


class CarpetaCVDetalle(CarpetaCVResumen):
    """Una carpeta y su listado de archivos, más recientes primero. `cantidad_archivos` es el total de la carpeta; con
    paginación, `archivos` trae solo la página pedida y `total_filtrado` cuenta los que cumplen la búsqueda."""

    archivos: List[ArchivoCVResponse]
    pagina: Optional[int] = None
    por_pagina: Optional[int] = None
    total_paginas: Optional[int] = None
    total_filtrado: Optional[int] = None


class LimpiarBDRequest(BaseModel):
    """Confirmación explícita de la limpieza de datos de Recruiting."""

    confirmar: bool = False


class LimpiarBDResponse(BaseModel):
    """Lo eliminado: registros por tabla y archivos físicos por origen."""

    registros: dict[str, int]
    archivos: dict[str, int]
    total_registros: int
    total_archivos: int


class HistorialCargaCVItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fecha_operacion: datetime
    usuario_nombre: str
    tipo_carga: str
    total_archivos: int
    candidatos_creados: int
    duplicados: int
    sin_email: int
    rechazados: int
    resultado: str


class HistorialCargaCVPagina(Pagina[HistorialCargaCVItem]):
    """Página del historial de cargas de CV."""


class HistorialCargaCVArchivoItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden: int
    nombre_archivo: str
    resultado: str
    motivo: Optional[str] = None


class HistorialCargaCVDetalle(BaseModel):
    operacion: HistorialCargaCVItem
    archivos: List[HistorialCargaCVArchivoItem]
