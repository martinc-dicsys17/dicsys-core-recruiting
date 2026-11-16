/**
 * Tipos de la ficha del candidato. Reflejan CandidatoResponse (backend/modules/recruiting/schemas.py). La ficha
 * anterior también mostraba «disponibilidad» y «observaciones», que el backend no devuelve: se muestran con sus
 * valores por defecto, como antes.
 */
export interface CandidatoDetalle {
  id: string
  nombre: string
  apellido?: string | null
  email?: string | null
  telefono?: string | null
  ubicacion?: string | null
  provincia_id?: number | null
  ciudad_id?: number | null
  dni?: string | null
  /** AAAA-MM-DD */
  fecha_nacimiento?: string | null
  linkedin_url?: string | null
  cv_url?: string | null
  headline?: string | null
  seniority?: string | null
  modalidad?: string | null
  skills?: string[] | null
  habilidades?: string[] | null
  pretension_salarial?: number | string | null
  moneda?: string | null
  moneda_pretension?: string | null
  estado?: string | null
  fuente?: string | null
  disponibilidad?: string | null
  observaciones?: string | null
}
