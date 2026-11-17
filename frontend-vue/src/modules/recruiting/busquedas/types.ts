/** Tipos del listado de Búsquedas (oportunidades): reflejan los esquemas del backend (OportunidadResponse y afines). */

export interface Busqueda {
  id: string
  id_busqueda: string | null
  cliente: string
  titulo: string
  estado: string
  recruiter_nombre: string | null
  lider_nombre: string | null
  fecha_asignacion: string | null
  dias_abierta: number
  candidatos_pipeline: number
  coordinando_entrevista: number
  entrevistados_rrhh: number
  presentacion_lider: number
  feedback_lider: number
  presentacion_cliente: number
  q_activos: number
  externo_id: string | null
  externo_nombre: string | null
  externo_email: string | null
}

export interface PaginaBusquedas {
  items: Busqueda[]
  total: number
  pagina: number
  por_pagina: number
  total_paginas: number
}

export interface PermisosBusquedas {
  puede_crear_busquedas: boolean
  puede_eliminar_busquedas: boolean
  puede_ver_lider_tipo_fecha_busqueda: boolean
  puede_ver_smart_matching: boolean
  puede_asignar_candidatos: boolean
  puede_asignar_reclutador: boolean
  puede_administrar_externos: boolean
  es_externo: boolean
}

export interface ExternoDisponible {
  id: string
  nombre: string
  email: string
}

export type TipoBusqueda = 'Efectiva' | 'Potencial' | 'Todas'

/** Filtros y paginación del listado: viven en la URL con los nombres de la pantalla anterior. */
export interface FiltrosBusquedas {
  busqueda: string
  /** `todos` o uno de ESTADOS. */
  estado: string
  tipo: TipoBusqueda
  pagina: number
  limite: number
}
