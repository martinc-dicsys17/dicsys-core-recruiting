import type { AvanceLote, BusquedaElegible, ReporteLote, ResultadoArchivoLote } from './types'

/** Reglas de la carga de CV (individual y masiva) y del resumen del lote; las mismas de la pantalla anterior. */

export const MAX_CV_BYTES = 5 * 1024 * 1024
export const MAX_LOTE_BYTES = 500 * 1024 * 1024
export const MAX_CVS_INDIVIDUALES = 100

const EXTENSIONES_CV = ['pdf', 'doc', 'docx']
const EXTENSIONES_COMPRIMIDOS = ['zip', 'rar']

export function extension(nombre: string): string {
  const punto = nombre.lastIndexOf('.')
  return punto < 0 ? '' : nombre.slice(punto + 1).toLowerCase()
}

export const esComprimido = (archivo: { name: string }): boolean =>
  EXTENSIONES_COMPRIMIDOS.includes(extension(archivo.name))

/** Carga individual: mensaje de error del archivo, o null si se puede subir. */
export function errorArchivoIndividual(archivo: { name: string; size: number }): string | null {
  if (!EXTENSIONES_CV.includes(extension(archivo.name))) {
    return 'Formato no admitido. Seleccioná un archivo PDF, DOC o DOCX.'
  }
  if (archivo.size > MAX_CV_BYTES) return 'El archivo supera el tamaño máximo permitido de 5 MB.'
  return null
}

export const cantidadIndividuales = (archivos: { name: string }[]): number =>
  archivos.filter((a) => !esComprimido(a)).length

export interface ResultadoSeleccionMasiva<T extends { name: string; size: number }> {
  archivos: T[]
  /** Archivos rechazados por formato o tamaño (el resto de la selección se conserva). */
  errores: string
  /** Si se superan los 100 CVs individuales se rechaza toda la selección nueva y se conserva la anterior. */
  advertenciaLimite: string
}

/** Suma archivos a la selección de la carga masiva aplicando los límites de formato, tamaño total y cantidad. */
export function agregarArchivosMasivo<T extends { name: string; size: number }>(
  actuales: T[],
  nuevos: T[],
): ResultadoSeleccionMasiva<T> {
  const mensajes: string[] = []
  const aceptados: T[] = []
  let bytes = actuales.reduce((total, f) => total + f.size, 0)
  for (const archivo of nuevos) {
    if (![...EXTENSIONES_CV, ...EXTENSIONES_COMPRIMIDOS].includes(extension(archivo.name))) {
      mensajes.push(`Formato no admitido: "${archivo.name}". Solo se aceptan .PDF, .DOC, .DOCX, .ZIP y .RAR.`)
      continue
    }
    if (bytes + archivo.size > MAX_LOTE_BYTES) {
      mensajes.push(`La carga supera el tamaño máximo permitido de 500 MB. No se agregó "${archivo.name}".`)
      continue
    }
    bytes += archivo.size
    aceptados.push(archivo)
  }
  if (cantidadIndividuales(actuales) + cantidadIndividuales(aceptados) > MAX_CVS_INDIVIDUALES) {
    return {
      archivos: actuales,
      errores: '',
      advertenciaLimite:
        'No se pueden cargar más de 100 CVs individuales por operación. Seleccioná hasta 100 archivos o comprimilos en un archivo ZIP o RAR.',
    }
  }
  return { archivos: [...actuales, ...aceptados], errores: mensajes.join(' '), advertenciaLimite: '' }
}

export function porcentajeLote(procesados: number, total: number): number {
  if (!total) return 0
  return Math.min(100, Math.max(0, Math.floor((procesados / total) * 100)))
}

export function tituloProgreso(estado: string, cancelando: boolean): string {
  if (estado === 'cancelado') return 'Carga cancelada'
  if (cancelando) return 'Cancelando carga...'
  if (estado === 'finalizado') return 'Carga finalizada'
  return 'Procesando CVs...'
}

export function textoProgreso(estado: string, procesados: number, total: number): string {
  if (!total && estado !== 'cancelado') return 'Preparando archivos...'
  return `Procesados ${procesados} de ${total} CVs`
}

/** Mensaje al cancelar un lote: lo ya creado se conserva. */
export function mensajeCancelado(avance: Pick<AvanceLote, 'procesados' | 'total' | 'reporte'>): string {
  const creados = avance.reporte?.resumen?.creados ?? 0
  return `Carga cancelada. Se procesaron ${avance.procesados} de ${avance.total} CVs${
    creados ? ` (los ${creados} candidato(s) ya creados se conservan).` : '.'
  }`
}

const ETIQUETAS_RESULTADO: Record<string, string> = {
  creado: 'Creado correctamente',
  duplicado: 'CV duplicado',
  sin_email: 'Sin email',
  formato_tamano: 'Rechazado por formato o tamaño',
  error_lectura: 'Error de lectura o extracción',
  error_validacion: 'Error de validación',
  error_persistencia: 'Error de persistencia',
  error_otro: 'Error de procesamiento',
}

export const etiquetaResultado = (resultado: string): string => ETIQUETAS_RESULTADO[resultado] ?? 'Otro error'

export const detalleNoCreados = (reporte: ReporteLote | null | undefined): ResultadoArchivoLote[] =>
  (reporte?.resultados ?? []).filter((r) => r.resultado !== 'creado')

export interface CategoriaResumen {
  clave: string
  etiqueta: string
  ayuda?: string
  valor: number
  clase: string
}

/** Filas del resumen final: las cuatro principales siempre; los errores de procesamiento solo si hubo. */
export function categoriasResumen(reporte: ReporteLote | null | undefined): CategoriaResumen[] {
  const r = reporte?.resumen
  if (!r) return []
  const neutro = 'bg-dark-50 border-dark-200 text-dark-500'
  const error = 'bg-red-50 border-red-100 text-red-700'
  const filas: (CategoriaResumen & { siempre?: boolean })[] = [
    { clave: 'creados', etiqueta: 'Candidatos creados correctamente', valor: r.creados, clase: r.creados > 0 ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : neutro, siempre: true },
    { clave: 'duplicados', etiqueta: 'CV duplicados', ayuda: 'Incluye duplicados detectados por email o por nombre de archivo.', valor: r.duplicados_omitidos, clase: r.duplicados_omitidos > 0 ? 'bg-amber-50 border-amber-100 text-amber-800' : neutro, siempre: true },
    { clave: 'sin-email', etiqueta: 'CV sin email', valor: r.sin_email, clase: r.sin_email > 0 ? error : neutro, siempre: true },
    { clave: 'formato-tamano', etiqueta: 'CV rechazados por formato o tamaño', valor: r.rechazados_formato_tamano, clase: r.rechazados_formato_tamano > 0 ? error : neutro, siempre: true },
    { clave: 'errores-lectura', etiqueta: 'CV con error de lectura o extracción', valor: r.errores_lectura, clase: error },
    { clave: 'errores-validacion', etiqueta: 'CV con error de validación', valor: r.errores_validacion, clase: error },
    { clave: 'errores-persistencia', etiqueta: 'CV con error al guardar el candidato', valor: r.errores_persistencia, clase: error },
    { clave: 'errores-otros', etiqueta: 'CV con otros errores de procesamiento', valor: r.errores_otros, clase: error },
  ]
  return filas.filter((f) => f.siempre || f.valor > 0).map(({ siempre: _siempre, ...fila }) => fila)
}

/** Error del alta con CV cuyo email ya existe: se informa con el email, sin el texto técnico del backend. */
export function mensajeEmailExistente(mensaje: string, estado: number): string | null {
  if (estado !== 409 && !mensaje.includes('Ya existe un candidato registrado con este email')) return null
  const email = /([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)/.exec(mensaje)?.[1]
  return email
    ? `El candidato ya se encuentra registrado con el email ${email}.`
    : 'El candidato ya se encuentra registrado con este email.'
}

/** Detalle del Smart Matching de una búsqueda elegible (texto del tooltip del porcentaje). */
export function detalleMatch(b: BusquedaElegible): string {
  const requeridas = b.skills ?? []
  const coincidentes = b.skills_coincidentes ?? []
  const faltantes = requeridas.filter((s) => !coincidentes.some((c) => c.toLowerCase() === s.toLowerCase()))
  const matchSkills =
    typeof b.match_skills === 'number'
      ? b.match_skills
      : Math.round((coincidentes.length / (requeridas.length || 1)) * 100)
  const matchSeniority =
    typeof b.match_seniority === 'number' ? b.match_seniority : b.seniority_compatible ? 100 : 0
  const total = b.match_porcentaje || b.porcentaje_match || 0
  const formula =
    requeridas.length === 0
      ? `100% Seniority (${matchSeniority}%)`
      : `(70% Skills [${matchSkills}%]) + (30% Seniority [${matchSeniority}%])`
  const lista = (l: string[]) => l.join(', ') || 'Ninguna'
  const linea = '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
  return [
    'DETALLE SMART MATCHING',
    linea,
    `• Skills requeridas (${requeridas.length}): ${lista(requeridas)}`,
    `• Skills coincidentes (${coincidentes.length}): ${lista(coincidentes)}`,
    `• Skills faltantes (${faltantes.length}): ${lista(faltantes)}`,
    `• Factor Seniority: ${b.seniority || 'N/A'} (${b.seniority_compatible ? 'Compatible' : 'Parcial'} - ${matchSeniority}%)`,
    linea,
    `• Fórmula: ${formula}`,
    `• Resultado final: ${total}% match`,
  ].join('\n')
}
