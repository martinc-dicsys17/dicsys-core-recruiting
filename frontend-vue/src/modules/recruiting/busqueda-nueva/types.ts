/** Formulario de la búsqueda nueva (mismos campos que la pantalla anterior; `hm` es el líder). */
export interface FormularioBusqueda {
  titulo: string
  tipo: string
  puesto: string
  cliente: string
  hm: string
  reclutador: string
  vacantes: number | string
  prioridad: string
  seniority: string
  modalidad: string
  rango: string
  descripcion: string
  skills: string[]
  habilidades: string[]
  skills_deseadas: string[]
}

/** Cuerpo de OportunidadCreate (POST /api/v1/recruiting/oportunidades). */
export interface BusquedaCreate {
  titulo: string
  cliente: string
  estado: string
  puesto?: string
  seniority?: string
  modalidad?: string
  rango?: string
  prioridad?: string
  tipo?: string
  lider_nombre: string | null
  recruiter_nombre: string | null
  vacantes: number
  skills: string[]
  habilidades: string[]
  skills_deseadas: string[]
  descripcion: string | null
}

export interface BusquedaCreada {
  id: string
  titulo: string
}

/** Elemento de un catálogo por nombre (skills, habilidades, líderes, reclutadores). */
export interface ItemCatalogo {
  id?: string | number
  nombre: string
  activo?: boolean
}

/** Solo lo que esta pantalla usa de GET /oportunidades/permisos. */
export interface PermisosBusquedas {
  puede_crear_busquedas: boolean
}
