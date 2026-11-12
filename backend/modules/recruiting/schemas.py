"""Esquemas Pydantic del módulo Recruiting.

Por ahora los del Dashboard (GET /recruiting/dashboard) y los del Manager Dashboard. Siguen el contrato de la API del Core
(docs/Arquitectura-Backend.md): todo tipado, sin diccionarios sueltos.
"""

import uuid
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


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
