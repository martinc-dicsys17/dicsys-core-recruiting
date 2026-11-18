import type { AlcanceCandidatos, ColumnaGlobal, FilaResumen } from './types'

/**
 * Lo que la pantalla anterior mostraba en Pipeline (asignar_candidato_hub.html y pipeline.html): enlaces, filtro de
 * candidatos, colores de la vista global y formatos. Los enlaces usan las direcciones de siempre (sin el prefijo /v2):
 * Flask las redirige a la pantalla Vue y el parámetro «volver» solo admite rutas de Recruiting.
 */

export const RUTA_GESTION = '/recruiting/gestion-busquedas'
export const RUTA_BUSQUEDAS = '/recruiting/oportunidades'
export const RUTA_NUEVA_BUSQUEDA = '/recruiting/oportunidades/nueva'
export const ERROR_PIPELINE = 'No se pudo cargar el Pipeline. Probá de nuevo en unos minutos.'

type Query = Record<string, unknown>

/** Primer valor de un parámetro de la URL ('' si no viene). */
export function parametro(query: Query, nombre: string): string {
  const valor = query[nombre]
  const primero = Array.isArray(valor) ? valor[0] : valor
  return typeof primero === 'string' ? primero : ''
}

/** Filtro de candidatos de la URL: 'propios' o '' (todos). */
export const alcanceDesdeQuery = (query: Query): AlcanceCandidatos =>
  parametro(query, 'alcance_candidatos').trim().toLowerCase() === 'propios' ? 'propios' : ''

/** Vista de la pantalla Pipeline: 'global' (por defecto) o 'individual'. */
export function vistaDesdeQuery(query: Query): 'global' | 'individual' {
  return parametro(query, 'vista') === 'individual' ? 'individual' : 'global'
}

/**
 * Query del selector de Vista: conserva el filtro de candidatos tal como vino en la URL. Mismo orden que armaba
 * Flask (`vista` y después `alcance_candidatos`).
 */
export function queryDeVista(vista: 'global' | 'individual', query: Query): Record<string, string> {
  const q: Record<string, string> = {}
  if (vista === 'individual') q.vista = 'individual'
  const alcance = parametro(query, 'alcance_candidatos')
  if (alcance) q.alcance_candidatos = alcance
  return q
}

/** Query del filtro de candidatos: conserva el resto de los parámetros (vista, etapas, columna). */
export function queryDeAlcance(alcance: AlcanceCandidatos, query: Query): Record<string, string> {
  const q: Record<string, string> = {}
  for (const [clave, valor] of Object.entries(query)) {
    const v = Array.isArray(valor) ? valor[0] : valor
    if (clave !== 'alcance_candidatos' && typeof v === 'string') q[clave] = v
  }
  q.alcance_candidatos = alcance
  return q
}

const conAlcance = (alcance: AlcanceCandidatos, separador: '?' | '&') =>
  alcance ? `${separador}alcance_candidatos=${encodeURIComponent(alcance)}` : ''

/** Pipeline individual de una búsqueda (con el filtro de candidatos activo). */
export const urlPipeline = (id: string, alcance: AlcanceCandidatos): string =>
  `/recruiting/oportunidades/${id}/pipeline${conAlcance(alcance, '?')}`

/** Pipeline individual con las etapas reales de la columna de la vista global. */
export const urlColumna = (fila: Pick<FilaResumen, 'id'>, col: ColumnaGlobal, alcance: AlcanceCandidatos): string =>
  `/recruiting/oportunidades/${fila.id}/pipeline` +
  `?etapas=${encodeURIComponent((col.etapas || []).join(','))}` +
  `&columna=${encodeURIComponent(col.nombre)}` +
  conAlcance(alcance, '&')

/** «Volver» que se deja a las pantallas que se abren desde acá: la dirección de siempre con su query. */
export const volverA = (ruta: string, search: string): string => encodeURIComponent(ruta + search)

/** Query de la dirección actual sin `etapas` ni `columna` (al volver del detalle queda «Todas»). */
export function searchSinFiltroDeEtapa(search: string): string {
  const params = new URLSearchParams(search)
  params.delete('etapas')
  params.delete('columna')
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

// ---- Vista global ----

/** Paleta de encabezados por columna (misma familia de colores que las etapas del Pipeline individual). */
const ESTILOS_COLUMNA: Record<string, { head: string; cell: string }> = {
  screening: { head: 'bg-purple-50 text-purple-700', cell: 'bg-purple-50 text-purple-700 hover:bg-purple-100 border-purple-200' },
  submissions: { head: 'bg-amber-50 text-amber-700', cell: 'bg-amber-50 text-amber-700 hover:bg-amber-100 border-amber-200' },
  interview: { head: 'bg-indigo-50 text-indigo-700', cell: 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border-indigo-200' },
  offer: { head: 'bg-emerald-50 text-emerald-700', cell: 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border-emerald-200' },
  hire: { head: 'bg-green-100 text-green-800', cell: 'bg-green-100 text-green-800 hover:bg-green-200 border-green-300' },
}

export const estiloHead = (clave: string): string => ESTILOS_COLUMNA[clave]?.head ?? 'bg-dark-50 text-dark-600'
export const estiloCelda = (clave: string): string =>
  ESTILOS_COLUMNA[clave]?.cell ?? 'bg-dark-50 text-dark-700 hover:bg-dark-100 border-dark-200'

/** Resalta la etapa donde se concentra la mayor cantidad de candidatos de la búsqueda. */
export function esMaximo(fila: Pick<FilaResumen, 'columnas'>, clave: string): boolean {
  const valores = Object.values(fila.columnas || {})
  const max = valores.length ? Math.max(...valores) : 0
  return max > 0 && (fila.columnas[clave] || 0) === max
}

export function tituloColumna(col: ColumnaGlobal): string {
  if (!(col.etapas || []).length) return `${col.nombre} — ${col.nota || 'Sin etapas asociadas'}`
  return `${col.nombre} — incluye: ${col.etapas.join(', ')}`
}

/** Búsqueda por título o cliente (texto libre). */
export function filtrarFilas<T extends Pick<FilaResumen, 'titulo' | 'cliente'>>(filas: T[], texto: string): T[] {
  const q = (texto || '').trim().toLowerCase()
  if (!q) return filas
  return filas.filter((f) => [f.titulo, f.cliente].some((v) => (v || '').toLowerCase().includes(q)))
}

export function formatoMoneda(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString('es-AR', { maximumFractionDigits: 0 }) + ' ARS'
}

/** Iniciales del popup de la vista global (dos primeras palabras). */
export const inicialesPopup = (nombre: string | null | undefined): string =>
  (nombre || '?')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0] ?? '')
    .join('')
    .toUpperCase()

/** Iniciales de la tabla del Pipeline individual. */
export function iniciales(nombre: string | null | undefined): string {
  if (!nombre) return 'C'
  const partes = nombre.trim().split(' ')
  const [a, b] = partes
  if (partes.length >= 2 && a !== undefined && b !== undefined) return ((a[0] ?? '') + (b[0] ?? '')).toUpperCase()
  return nombre.substring(0, 2).toUpperCase()
}

/** Modalidad: se guarda sin tilde y se muestra con ella. */
export const etiquetaModalidad = (modalidad: string | null | undefined): string =>
  modalidad === 'Hibrido' ? 'Híbrido' : (modalidad ?? '')

/** ID visible de la tarjeta de selección: id_busqueda o los primeros 8 caracteres del id. */
export const idTarjeta = (op: { id_busqueda: string | null; id: string }): string =>
  `#${op.id_busqueda || (op.id || '').substring(0, 8)}`
