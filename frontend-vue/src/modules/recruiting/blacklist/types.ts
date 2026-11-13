/**
 * Modelo PROVISORIO de la pantalla Blacklist (personas no entrevistables).
 * El catálogo de motivos ya viene del backend; las personas todavía no tienen tabla ni endpoint:
 * sus campos son una propuesta a confirmar antes de definir el modelo real.
 */

/** Motivo del catálogo (GET /recruiting/blacklist/motivos). */
export interface MotivoBlacklist {
  id: number
  motivo: string
}

export interface PersonaBlacklist {
  id: string
  nombre: string
  apellido: string
  documento: string
  email: string
  telefono: string
  /** Texto del motivo, tal cual figura en el catálogo. */
  motivo: string
  /** Descripción detallada escrita por el reclutador al incorporar a la persona. */
  observacion: string
  registradoPor: string
  /** Fecha ISO (AAAA-MM-DD). */
  fechaAlta: string
}
