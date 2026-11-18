import type { CandidatoPipeline } from './types'

/**
 * Reglas del embudo del Pipeline de una búsqueda, iguales a las de la pantalla anterior (pipeline.html): nombres de
 * etapa, flujo secuencial con sus saltos permitidos, conteos, filtro por etapa y colores de cada etapa. El backend
 * valida el flujo de verdad; esto solo orienta la interfaz.
 */

/** Flujo estrictamente secuencial y lineal. */
export const ETAPAS_EMBUDO = [
  'Candidato',
  'Screening',
  'Entrevista RRHH',
  'Entrevista Líder Dicsys',
  'Validación Administración',
  'Entrevista Cliente',
  'Oferta',
  'Examen Médico Preocupacional',
  'Ingreso',
] as const

/** Etapas de la barra de filtros (el embudo más Descartados). */
export const ETAPAS_TODAS = [...ETAPAS_EMBUDO, 'Descartados'] as const

/** Saltos permitidos además de la etapa siguiente. */
const SALTOS_PERMITIDOS: Record<string, string[]> = {
  'Entrevista Líder Dicsys': ['Entrevista Cliente'],
  'Validación Administración': ['Oferta'],
  'Entrevista Cliente': ['Examen Médico Preocupacional'],
}

// Se reemplaza solo la primera vocal acentuada de cada tipo, como la pantalla anterior.
const sinTildes = (u: string): string =>
  u.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')

/** Nombre visible de la etapa a partir de lo que guarda el backend (incluye los nombres históricos). */
export function normalizarEtapaNombre(etapa: string | null | undefined): string {
  if (!etapa) return 'Candidato'
  const s = etapa.trim()
  const u = sinTildes(s.toUpperCase())
  if (u === 'DESCARTADO' || u === 'DESCARTADOS') return 'Descartados'
  if (u === 'CANDIDATO' || u === 'POSTULADO' || u === 'COORDINANDO ENTREVISTA') return 'Candidato'
  if (u === 'SCREENING') return 'Screening'
  if (u.includes('RRHH')) return 'Entrevista RRHH'
  if (u.includes('LIDER') || u.includes('TECNICA')) return 'Entrevista Líder Dicsys'
  if (u.includes('ADMINISTRAC')) return 'Validación Administración'
  if (u.includes('EXAMEN') || u.includes('PREOCUPACIONAL')) return 'Examen Médico Preocupacional'
  if (u.includes('CLIENTE')) return 'Entrevista Cliente'
  if (u.includes('OFERTA')) return 'Oferta'
  if (u.includes('INGRESO')) return 'Ingreso'
  return s
}

/** Etiqueta del filtro de etapa (la de Líder Dicsys va abreviada). */
export const etiquetaEtapa = (etapa: string): string =>
  etapa === 'Entrevista Líder Dicsys' ? 'Entrevista Líder' : etapa

export function obtenerSiguienteEtapa(etapaActual: string | null | undefined): string | null {
  const idx = (ETAPAS_EMBUDO as readonly string[]).indexOf(normalizarEtapaNombre(etapaActual))
  return idx >= 0 && idx < ETAPAS_EMBUDO.length - 1 ? (ETAPAS_EMBUDO[idx + 1] ?? null) : null
}

/** Destinos de «Mover Etapa»: la siguiente etapa y los saltos permitidos desde la actual. */
export function destinosPermitidos(etapaActual: string | null | undefined): string[] {
  const norm = normalizarEtapaNombre(etapaActual)
  const siguiente = obtenerSiguienteEtapa(norm)
  if (!siguiente) return []
  return [siguiente, ...(SALTOS_PERMITIDOS[norm] ?? [])]
}

const esDescartado = (c: Pick<CandidatoPipeline, 'etapa_actual' | 'estado'>): boolean => {
  const etapa = normalizarEtapaNombre(c.etapa_actual || '').toLowerCase()
  return etapa === 'descartados' || etapa === 'descartado' || (c.estado || '').toLowerCase() === 'descartado'
}

/** Candidatos que coinciden con la etapa del filtro («Todas», una etapa o «Descartados»). */
export function filtrarPorEtapa<T extends Pick<CandidatoPipeline, 'etapa_actual' | 'estado'>>(
  candidatos: T[],
  etapaFiltro: string,
): T[] {
  if (etapaFiltro === 'Todas') return candidatos
  const filtro = etapaFiltro.trim().toLowerCase()
  if (filtro === 'descartados' || filtro === 'descartado') return candidatos.filter(esDescartado)
  return candidatos.filter((c) => normalizarEtapaNombre(c.etapa_actual || '').toLowerCase() === filtro)
}

export const conteoEtapa = (candidatos: Pick<CandidatoPipeline, 'etapa_actual' | 'estado'>[], etapa: string): number =>
  filtrarPorEtapa(candidatos, etapa).length

/** «Total en proceso»: los que no están descartados (ni por estado ni por etapa). */
export const totalEnProceso = (candidatos: Pick<CandidatoPipeline, 'etapa_actual' | 'estado'>[]): number =>
  candidatos.filter((c) => ![c.estado, c.etapa_actual].some((v) => v === 'Descartado' || v === 'Descartados')).length

/** Qué acciones muestra la fila: activo en el embudo, Ingreso confirmado o descartado. */
export function casoDeFila(c: Pick<CandidatoPipeline, 'etapa_actual' | 'estado'>): 'activo' | 'ingreso' | 'descartado' {
  const etapa = normalizarEtapaNombre(c.etapa_actual)
  const descartado = (c.estado || '').toLowerCase() === 'descartado'
  if (etapa === 'Descartados' || descartado) return 'descartado'
  return etapa === 'Ingreso' ? 'ingreso' : 'activo'
}

/** Estado que se guarda al avanzar: Ingreso confirma el ingreso; el resto queda En proceso. */
export const estadoAlAvanzar = (nuevaEtapa: string): string =>
  nuevaEtapa === 'Ingreso' ? 'Ingreso confirmado' : 'En proceso'

/** La pretensión salarial se pide solo de Entrevista RRHH a Entrevista Líder Dicsys. */
export const pideTransicionPretension = (etapaActual: string | null | undefined, nuevaEtapa: string): boolean =>
  normalizarEtapaNombre(etapaActual) === 'Entrevista RRHH' && nuevaEtapa === 'Entrevista Líder Dicsys'

// ---- Colores de cada etapa (mismas clases que la pantalla anterior) ----

export interface EstiloEtapa {
  badge: string
  dot: string
  tabActive: string
  tabInactive: string
  badgeCountActive: string
  badgeCountInactive: string
}

// Las sombras `shadow-sm` de Tailwind 3 (la pantalla anterior) equivalen a `shadow-xs` en Tailwind 4.
const ESTILO_DESCARTADO: EstiloEtapa = {
  badge: 'bg-rose-50 text-rose-700 border-rose-200',
  dot: 'bg-rose-500',
  tabActive: 'bg-rose-500 text-white border-rose-600 shadow-xs',
  tabInactive: 'bg-rose-50/70 hover:bg-rose-100/80 text-rose-700 border-rose-200/80',
  badgeCountActive: 'bg-white/25 text-white',
  badgeCountInactive: 'bg-rose-200/70 text-rose-800',
}

// Clases escritas completas: Tailwind solo genera las que encuentra literales en el código.
const ESTILOS: Record<string, EstiloEtapa> = {
  Todas: {
    badge: 'bg-slate-100 text-slate-700 border-slate-300',
    dot: 'bg-slate-500',
    tabActive: 'bg-slate-800 text-white border-slate-900 shadow-xs',
    tabInactive: 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200',
    badgeCountActive: 'bg-white/20 text-white',
    badgeCountInactive: 'bg-slate-200 text-slate-700',
  },
  Candidato: {
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
    dot: 'bg-blue-500',
    tabActive: 'bg-blue-600 text-white border-blue-700 shadow-xs',
    tabInactive: 'bg-blue-50/70 hover:bg-blue-100/80 text-blue-700 border-blue-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-blue-200/70 text-blue-800',
  },
  Screening: {
    badge: 'bg-purple-50 text-purple-700 border-purple-200',
    dot: 'bg-purple-500',
    tabActive: 'bg-purple-600 text-white border-purple-700 shadow-xs',
    tabInactive: 'bg-purple-50/70 hover:bg-purple-100/80 text-purple-700 border-purple-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-purple-200/70 text-purple-800',
  },
  'Entrevista RRHH': {
    badge: 'bg-cyan-50 text-cyan-700 border-cyan-200',
    dot: 'bg-cyan-500',
    tabActive: 'bg-cyan-600 text-white border-cyan-700 shadow-xs',
    tabInactive: 'bg-cyan-50/70 hover:bg-cyan-100/80 text-cyan-700 border-cyan-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-cyan-200/70 text-cyan-800',
  },
  'Entrevista Líder Dicsys': {
    badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    dot: 'bg-indigo-500',
    tabActive: 'bg-indigo-600 text-white border-indigo-700 shadow-xs',
    tabInactive: 'bg-indigo-50/70 hover:bg-indigo-100/80 text-indigo-700 border-indigo-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-indigo-200/70 text-indigo-800',
  },
  'Validación Administración': {
    badge: 'bg-orange-50 text-orange-700 border-orange-200',
    dot: 'bg-orange-500',
    tabActive: 'bg-orange-600 text-white border-orange-700 shadow-xs',
    tabInactive: 'bg-orange-50/70 hover:bg-orange-100/80 text-orange-700 border-orange-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-orange-200/70 text-orange-800',
  },
  'Entrevista Cliente': {
    badge: 'bg-amber-50 text-amber-700 border-amber-200',
    dot: 'bg-amber-500',
    tabActive: 'bg-amber-600 text-white border-amber-700 shadow-xs',
    tabInactive: 'bg-amber-50/70 hover:bg-amber-100/80 text-amber-700 border-amber-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-amber-200/70 text-amber-800',
  },
  Oferta: {
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dot: 'bg-emerald-500',
    tabActive: 'bg-emerald-600 text-white border-emerald-700 shadow-xs',
    tabInactive: 'bg-emerald-50/70 hover:bg-emerald-100/80 text-emerald-700 border-emerald-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-emerald-200/70 text-emerald-800',
  },
  'Examen Médico Preocupacional': {
    badge: 'bg-teal-50 text-teal-700 border-teal-200',
    dot: 'bg-teal-500',
    tabActive: 'bg-teal-600 text-white border-teal-700 shadow-xs',
    tabInactive: 'bg-teal-50/70 hover:bg-teal-100/80 text-teal-700 border-teal-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-teal-200/70 text-teal-800',
  },
  Ingreso: {
    badge: 'bg-green-100 text-green-800 border-green-300',
    dot: 'bg-green-600',
    tabActive: 'bg-green-700 text-white border-green-800 shadow-xs',
    tabInactive: 'bg-green-100/70 hover:bg-green-200/80 text-green-800 border-green-300/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-green-200 text-green-900',
  },
  Descartados: {
    badge: 'bg-rose-50 text-rose-700 border-rose-200',
    dot: 'bg-rose-500',
    tabActive: 'bg-rose-600 text-white border-rose-700 shadow-xs',
    tabInactive: 'bg-rose-50/70 hover:bg-rose-100/80 text-rose-700 border-rose-200/80',
    badgeCountActive: 'bg-white/25 text-white',
    badgeCountInactive: 'bg-rose-200/70 text-rose-800',
  },
}

/** Colores de la etapa: descartado por estado o etapa; si no, por el nombre de la etapa (Screening por defecto). */
export function estiloEtapa(etapa: string | null | undefined, estado?: string | null): EstiloEtapa {
  if (estado === 'Descartado' || etapa === 'Descartado' || etapa === 'Descartados') return ESTILO_DESCARTADO
  const nombre = normalizarEtapaNombre(etapa || 'Screening')
  return ESTILOS[nombre] ?? (ESTILOS.Screening as EstiloEtapa)
}
