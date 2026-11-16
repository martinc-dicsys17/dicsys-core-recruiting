/**
 * Tipos de la pantalla Nuevo Candidato. Reflejan los schemas reales del backend
 * (backend/modules/recruiting/schemas.py): ProvinciaResponse, CiudadResponse, SkillCatalogoResponse,
 * NivelSeniorityResponse, CandidatoCreate y CandidatoResponse.
 */

export interface Provincia {
  provincia_id: number
  nombre: string
  cantidad_ciudades: number
}

export interface Ciudad {
  ciudad_id: number
  nombre: string
  provincia_id: number
}

/** Item de los catálogos de skills, habilidades y niveles de seniority (solo se usa el nombre). */
export interface ItemCatalogo {
  nombre: string
}

/** Cuerpo del alta: forma exacta de CandidatoCreate. */
export interface CandidatoCreate {
  nombre: string
  apellido: string
  email: string
  telefono: string | null
  provincia_id: number | null
  ciudad_id: number | null
  dni: string | null
  /** Fecha ISO (AAAA-MM-DD). */
  fecha_nacimiento: string | null
  linkedin_url: string | null
  headline: string | null
  seniority: string | null
  modalidad: string | null
  skills: string[]
  habilidades: string[]
  pretension_salarial: null
  moneda_pretension: string
  estado: string
  fuente: string
}

/** Lo que la pantalla necesita del candidato creado. */
export interface CandidatoCreado {
  id: string
}

/** Estado del formulario (todo texto, como lo escribe la persona). */
export interface FormularioCandidato {
  nombre: string
  apellido: string
  email: string
  telefono: string
  provincia_id: number | null
  ciudad_id: number | null
  linkedin: string
  dni: string
  /** DD-MM-AAAA, tal cual se escribe. */
  fecha_nacimiento: string
  /** null cuando se limpia el combo (PrimeVue Select). */
  puesto: string | null
  seniority: string
  modalidad: string
  skills: string[]
  habilidades: string[]
}
