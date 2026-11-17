/** Tipos de la ficha de una Búsqueda (oportunidad). Reflejan los esquemas del backend (`OportunidadResponse`, etc.). */

export interface Oportunidad {
  id: string
  id_busqueda: string
  cliente: string
  titulo: string
  estado: string
  recruiter_nombre: string | null
  lider_nombre: string | null
  fecha_asignacion: string | null
  fecha_creacion: string | null
  dias_abierta: number
  area: string | null
  puesto: string | null
  seniority: string | null
  modalidad: string | null
  vacantes: number
  rango: string | null
  prioridad: string | null
  tipo: string
  skills: string[]
  habilidades: string[]
  skills_deseadas: string[]
  descripcion: string | null
  q_activos: number
  externo_id: string | null
  externo_nombre: string | null
  externo_email: string | null
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

/** Candidato en el pipeline de la búsqueda (`CandidatoEnBusqueda`). */
export interface CandidatoAsignado {
  id: string
  candidato_id: string
  nombre: string
  nombre_pila: string | null
  apellido: string
  email: string
  telefono: string | null
  headline: string | null
  seniority: string | null
  etapa: string
  etapa_actual: string
  es_anonimo: boolean
}

/** Candidato sugerido por Smart Matching (`CandidatoCompatible`). */
export interface CandidatoSugerido {
  id: string
  nombre: string
  apellido: string
  nombre_completo: string
  email: string
  headline: string | null
  seniority: string | null
  skills_coincidentes: string[]
  habilidades_coincidentes: string[]
  porcentaje_match: number
  match_porcentaje: number
}

export interface ExternoDisponible {
  id: string
  nombre: string
  email: string
}

/** Valores del formulario de edición (solo Descripción y Skills deseadas se guardan; el resto se muestra bloqueado). */
export interface FormularioBusqueda {
  titulo: string
  puesto: string
  cliente: string
  area: string
  seniority: string
  modalidad: string
  vacantes: number
  rango: string
  recruiter_nombre: string
  lider_nombre: string
  estado: string
  prioridad: string
  tipo: string
  skills: string[]
  habilidades: string[]
  skills_deseadas: string[]
  descripcion: string
}

/** Desglose del cálculo de Smart Matching que muestra el modal. */
export interface DesgloseMatch {
  nombre: string
  senRequerido: string
  senCandidato: string
  senCoincide: boolean
  aporteSkills: number
  aporteSeniority: number
  porcentaje: number
  totReq: number
  totCoinc: number
  reqSkills: string[]
  coincSkills: string[]
  faltSkills: string[]
  reqHabs: string[]
  coincHabs: string[]
  faltHabs: string[]
  aplicaHabs: boolean
}

export type TipoAviso = 'success' | 'error'
