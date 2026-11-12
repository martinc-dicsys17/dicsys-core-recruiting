"""Esquemas Pydantic del módulo Recruiting.

Los del Dashboard (GET /recruiting/dashboard), el Manager Dashboard y Candidatos. Siguen el contrato de la API del Core
(docs/Arquitectura-Backend.md): todo tipado, sin diccionarios sueltos.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
