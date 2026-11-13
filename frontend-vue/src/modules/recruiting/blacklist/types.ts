/**
 * Modelo PROVISORIO de la pantalla Blacklist (personas no entrevistables).
 * Todavia no existe tabla ni endpoint: los campos son una propuesta a confirmar
 * antes de definir el modelo real.
 */

export const MOTIVOS = {
  conducta: 'Conducta inapropiada',
  datos_falsos: 'Datos falsos en el CV',
  abandono_proceso: 'Abandono del proceso',
  incumplimiento: 'Incumplimiento de acuerdos',
  conflicto_interes: 'Conflicto de intereses',
  otro: 'Otro motivo',
} as const

export type MotivoBlacklist = keyof typeof MOTIVOS

export interface PersonaBlacklist {
  id: string
  nombre: string
  apellido: string
  documento: string
  email: string
  telefono: string
  motivo: MotivoBlacklist
  /** Descripción detallada escrita por el reclutador al incorporar a la persona. */
  observacion: string
  registradoPor: string
  /** Fecha ISO (AAAA-MM-DD). */
  fechaAlta: string
}
