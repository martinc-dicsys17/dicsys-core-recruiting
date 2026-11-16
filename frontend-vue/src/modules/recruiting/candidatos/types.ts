/**
 * Tipos de la grilla de Candidatos. Reflejan los schemas reales del backend
 * (backend/modules/recruiting/schemas.py): CandidatoResponse, CandidatoPagina y los permisos del listado.
 */

export interface CandidatoListado {
  id: string
  codigo?: string | null
  nombre: string
  apellido: string
  email: string
  telefono?: string | null
  ubicacion?: string | null
  cv_url?: string | null
  headline?: string | null
  skills: string[]
  fuente?: string | null
  estado: string
  activo: boolean
  tiene_pipeline: boolean
}

export interface PaginaCandidatos {
  items: CandidatoListado[]
  total: number
  pagina: number
  por_pagina: number
  total_paginas: number
}

/** Acciones que el backend le habilita al usuario en el listado (GET /recruiting/candidatos/permisos). */
export interface PermisosCandidatos {
  puede_eliminar_candidatos: boolean
  puede_cargar_cv_general: boolean
  puede_carga_masiva: boolean
  puede_asignar_candidatos: boolean
}

/** Filtros y paginación del listado; viajan en la URL con los mismos nombres que la pantalla anterior. */
export interface FiltrosListado {
  busqueda: string
  seniority: string
  ubicacion: string
  puesto: string
  categoria: string
  skill: string
  /** Sin selector en pantalla, pero la URL los puede traer (enlaces de otras pantallas): se reenvían al backend. */
  estado: string
  fuente: string
  pagina: number
  limite: number
}

export interface OpcionesFiltros {
  provincias: string[]
  categorias: string[]
  skillsPorCategoria: Record<string, string[]>
  perfiles: string[]
  niveles: string[]
}

/** Búsqueda abierta compatible con el candidato (GET /recruiting/candidatos/{id}/busquedas-elegibles). */
export interface BusquedaElegible {
  id: string
  titulo?: string | null
  cliente?: string | null
  seniority?: string | null
  modalidad?: string | null
  id_busqueda?: string | number | null
  match_porcentaje?: number | null
  porcentaje_match?: number | null
  match_skills?: number | null
  match_seniority?: number | null
  seniority_compatible?: boolean
  skills?: string[]
  skills_coincidentes?: string[]
}

/** Datos de un CV en la comparación (ComparacionCV). */
export interface DatosCv {
  nombre?: string | null
  apellido?: string | null
  email?: string | null
  cv_url?: string | null
  archivo?: string | null
}

export interface ComparacionCv {
  actual: DatosCv
  nuevo: DatosCv
}

/** Resultado de subir un CV: creado/actualizado, o ya existe con otro CV y hay que comparar. */
export type ResultadoCargaCv = { tipo: 'ok' } | { tipo: 'comparar'; comparacion: ComparacionCv }

export interface ResumenLote {
  total_archivos: number
  creados: number
  duplicados_omitidos: number
  sin_email: number
  rechazados_formato_tamano: number
  errores_lectura: number
  errores_validacion: number
  errores_persistencia: number
  errores_otros: number
}

export interface ResultadoArchivoLote {
  archivo: string
  resultado: string
  mensaje: string
}

export interface ReporteLote {
  resumen: ResumenLote
  resultados: ResultadoArchivoLote[]
}

export type EstadoLote = 'preparando' | 'procesando' | 'finalizado' | 'cancelado' | 'error'

export interface AvanceLote {
  estado: EstadoLote
  procesados: number
  total: number
  reporte?: ReporteLote | null
  error?: string | null
}
