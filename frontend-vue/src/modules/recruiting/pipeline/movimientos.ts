import type { CambioEtapa, CandidatoPipeline } from './types'

/**
 * Reglas de los modales del Pipeline (Mover Etapa, Descartar y Reingresar), iguales a las de la pantalla anterior:
 * pretensión salarial, archivo adjunto, cuerpo que viaja al backend y cómo queda la fila después de guardar.
 */

export const MAX_COMENTARIO_ETAPA = 50
export const MAX_ADJUNTO_BYTES = 10 * 1024 * 1024
export const EXTENSIONES_ADJUNTO = ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.xlsx', '.xls', '.txt', '.zip', '.rar']
export const ACEPTA_ADJUNTO = EXTENSIONES_ADJUNTO.join(',')

/** Al escribir: deja solo dígitos y muestra formato moneda ARS (separador de miles, sin centavos). */
export function formatearPretension(texto: string): string {
  const digitos = (texto || '').replace(/\D/g, '').replace(/^0+(?=\d)/, '')
  return digitos ? '$ ' + Number(digitos).toLocaleString('es-AR', { maximumFractionDigits: 0 }) : ''
}

/** Entero mayor a cero; vacío o inválido devuelve el error (obligatoria de Entrevista RRHH a Entrevista Líder). */
export function validarPretension(texto: string): { valor: number | null; error: string } {
  const crudo = (texto || '').replace(/[$\s.]/g, '')
  if (!crudo) return { valor: null, error: 'La pretensión salarial es obligatoria.' }
  if (!/^\d+$/.test(crudo)) return { valor: null, error: 'Ingresá un monto entero válido, sin decimales ni valores negativos.' }
  const valor = Number(crudo)
  if (valor <= 0) return { valor: null, error: 'La pretensión salarial debe ser un importe mayor a cero.' }
  if (!Number.isSafeInteger(valor)) return { valor: null, error: 'El monto ingresado es demasiado grande.' }
  return { valor, error: '' }
}

/** Error del archivo adjunto de la etapa ('' si es válido): hasta 10 MB y solo los formatos admitidos. */
export function errorAdjunto(archivo: { name: string; size: number }): string {
  if (archivo.size > MAX_ADJUNTO_BYTES) return 'El archivo supera el límite de 10 MB.'
  const nombre = archivo.name.toLowerCase()
  if (!EXTENSIONES_ADJUNTO.some((ext) => nombre.endsWith(ext))) {
    return 'Tipo de archivo no permitido. Formatos: PDF, DOC, DOCX, PNG, JPG, XLSX, TXT, ZIP, RAR.'
  }
  return ''
}

export function tamanoAdjunto(bytes: number): string {
  return bytes < 1024 * 1024 ? (bytes / 1024).toFixed(1) + ' KB' : (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}

/** Id con el que se identifica al candidato en las rutas del pipeline. */
export const idCandidato = (c: Pick<CandidatoPipeline, 'candidato_id' | 'id'>): string => c.candidato_id || c.id

/** Cuerpo de «Confirmar Avance». */
export function cambioAvance(nuevaEtapa: string, estado: string, comentario: string, pretension: number | null): CambioEtapa {
  const cambio: CambioEtapa = {
    etapa_actual: nuevaEtapa,
    estado,
    feedback_etapa: comentario ? comentario.trim() : null,
  }
  if (pretension !== null) cambio.pretension_salarial_bruta_ars = pretension
  return cambio
}

/** Cuerpo de «Confirmar Descarte». */
export const cambioDescarte = (motivo: string, comentario: string): CambioEtapa => ({
  etapa_actual: 'Descartados',
  estado: 'Descartado',
  motivo_descarte: motivo.trim(),
  feedback_etapa: comentario ? comentario.trim() : null,
})

/** Cuerpo de «Confirmar Reingreso»: vuelve a Entrevista RRHH con el motivo como observación. */
export const cambioReingreso = (motivo: string): CambioEtapa => ({
  etapa_actual: 'Entrevista RRHH',
  estado: 'En proceso',
  feedback_etapa: motivo,
})

/** Formulario multipart (con archivo adjunto) con los mismos campos que el cuerpo JSON. */
export function formularioCambio(cambio: CambioEtapa, archivo: Blob): FormData {
  const formulario = new FormData()
  formulario.append('etapa_actual', cambio.etapa_actual)
  formulario.append('estado', cambio.estado)
  if (cambio.feedback_etapa) formulario.append('feedback_etapa', cambio.feedback_etapa)
  if (cambio.pretension_salarial_bruta_ars !== undefined) {
    formulario.append('pretension_salarial_bruta_ars', String(cambio.pretension_salarial_bruta_ars))
  }
  formulario.append('archivo', archivo)
  return formulario
}

/**
 * Cómo queda la fila del candidato después de guardar, sin volver a pedir la lista (como la pantalla anterior).
 * `visible` permite guardar en la fila un texto distinto del que viajó (el descarte guarda el motivo y el comentario
 * tal como se escribieron).
 */
export function aplicarCambio<T extends CandidatoPipeline>(
  candidatos: T[],
  candidatoId: string,
  cambio: CambioEtapa,
  visible: { motivo_descarte?: string; feedback_etapa?: string | null } = {},
): T[] {
  return candidatos.map((c) => {
    if (idCandidato(c) !== candidatoId) return c
    const nuevo: T = { ...c, etapa_actual: cambio.etapa_actual, estado: cambio.estado }
    nuevo.feedback_etapa = 'feedback_etapa' in visible ? (visible.feedback_etapa ?? null) : cambio.feedback_etapa
    if (cambio.pretension_salarial_bruta_ars !== undefined) {
      nuevo.pretension_salarial_bruta_ars = cambio.pretension_salarial_bruta_ars
    }
    if (cambio.etapa_actual === 'Descartados') nuevo.motivo_descarte = visible.motivo_descarte ?? cambio.motivo_descarte ?? null
    else delete nuevo.motivo_descarte
    return nuevo
  })
}
