/** Tipos de Pipeline (ítem «gestion_busquedas»). Reflejan los esquemas del backend (PipelineResumen, CandidatoEnBusqueda...). */

/** Filtro de candidatos del Pipeline («Todos» = '' o «Propios»). */
export type AlcanceCandidatos = '' | 'propios'

/** Columna de la vista global y las etapas reales que agrupa (`PipelineColumnaGlobal`). */
export interface ColumnaGlobal {
  clave: string
  nombre: string
  etapas: string[]
  nota: string | null
}

/** Fila de la vista global: candidatos por columna de una búsqueda (`PipelineResumenItem`). */
export interface FilaResumen {
  id: string
  id_busqueda: string | null
  titulo: string
  cliente: string | null
  estado: string
  recruiter_nombre: string | null
  es_externa: boolean
  total: number
  columnas: Record<string, number>
  sin_clasificar: number
}

export interface ResumenGlobal {
  columnas: ColumnaGlobal[]
  items: FilaResumen[]
}

/** Candidato de una columna de la vista global (detalle emergente, `PipelineColumnaCandidato`). */
export interface CandidatoColumna {
  candidato_id: string
  nombre: string | null
  pretension_salarial_bruta_ars: number | null
  rol_actual: string | null
  seniority: string | null
  reclutador: string | null
  presentado_por: string | null
  es_anonimo: boolean
  etapa_actual: string
}

/** Búsqueda Abierta para la selección del Pipeline individual (`OportunidadResponse`, solo lo que se muestra). */
export interface BusquedaAbierta {
  id: string
  id_busqueda: string | null
  titulo: string
  cliente: string | null
  estado: string
  recruiter_nombre: string | null
  reclutador?: string | null
  seniority: string | null
  modalidad: string | null
  vacantes: number | null
  externo_id: string | null
}

export interface PaginaBusquedas {
  items: BusquedaAbierta[]
}

/** La búsqueda del Pipeline individual (`OportunidadResponse`, solo lo que usa la pantalla). */
export interface BusquedaPipeline {
  id: string
  titulo: string | null
  cliente: string | null
  estado: string | null
  seniority: string | null
  modalidad: string | null
  vacantes: number | null
  externo_id: string | null
}

/** Candidato en el pipeline de la búsqueda (`CandidatoEnBusqueda`). */
export interface CandidatoPipeline {
  id: string
  gestion_id: string
  candidato_id: string
  oportunidad_id: string
  nombre: string
  email: string
  telefono: string | null
  seniority: string | null
  etapa: string
  etapa_actual: string
  estado: string
  motivo_descarte?: string | null
  feedback_etapa: string | null
  pretension_salarial_bruta_ars: number | null
  es_anonimo: boolean
  es_externo: boolean
  presentado_por: string | null
}

/** Acciones que el usuario ve en el Pipeline (`PermisosPipeline`). El backend las valida igual en cada endpoint. */
export interface PermisosPipeline {
  puede_mover_descartar: boolean
  puede_eliminar_candidatos: boolean
  puede_asignar_candidatos: boolean
  puede_crear_busquedas: boolean
  puede_eliminar_busquedas: boolean
  puede_ver_lider_tipo_fecha_busqueda: boolean
  puede_ver_smart_matching: boolean
  puede_cargar_cv_general: boolean
  puede_cargar_cv_en_busqueda: boolean
}

export interface MotivoDescarte {
  id: number
  motivo: string
}

/** Lo que viaja al mover de etapa, descartar o reingresar (mismo cuerpo que mandaba la pantalla anterior). */
export interface CambioEtapa {
  etapa_actual: string
  estado: string
  feedback_etapa: string | null
  motivo_descarte?: string
  pretension_salarial_bruta_ars?: number
}

/** Lo que confirma el modal «Mover Etapa». */
export interface DatosAvance {
  nuevaEtapa: string
  comentario: string
  pretension: number | null
  archivo: File | null
}

export type TipoToast = 'success' | 'warning'
