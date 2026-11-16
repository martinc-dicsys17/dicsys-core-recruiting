/**
 * Tipos de la pantalla Editar Candidato. El cuerpo del PUT es el de CandidatoUpdate del backend
 * (backend/modules/recruiting/schemas.py), igual que lo armaba la ficha anterior (candidato_detalle.html).
 */

/** Estado del formulario (todo texto, como lo escribe la persona; los ids de provincia y ciudad, como valor del combo). */
export interface FormularioEdicion {
  nombre: string
  apellido: string
  email: string
  telefono: string
  provincia_id: string
  ciudad_id: string
  dni: string
  /** DD-MM-AAAA, tal cual se escribe. */
  fecha_nacimiento: string
  estado: string
  headline: string
  seniority: string
  modalidad: string
  /** Monto con separador de miles (es-AR), tal cual se escribe. */
  salario: string
  moneda: 'ARS' | 'USD'
  fuente: string
  linkedin_url: string
  disponibilidad: string
  observaciones: string
  skills: string[]
  habilidades: string[]
}

/** Cuerpo del PUT. Provincia y ciudad solo viajan si la persona las modificó. */
export interface ActualizacionCandidato {
  nombre: string
  apellido: string
  email: string
  telefono: string | null
  provincia_id?: number | null
  ciudad_id?: number | null
  dni: string | null
  /** Fecha ISO (AAAA-MM-DD). */
  fecha_nacimiento: string | null
  estado: string
  /** Vacío limpia el puesto (el backend lo guarda como NULL); null no lo modificaría. */
  headline: string
  seniority: string | null
  modalidad: string | null
  pretension_salarial: number | null
  moneda: string
  moneda_pretension: string
  fuente: string
  linkedin_url: string | null
  disponibilidad: string | null
  observaciones: string | null
  skills: string[]
  habilidades: string[]
}
