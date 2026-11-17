import type { Busqueda } from './types'

/** Colores del badge de estado (mismos que la pantalla anterior). */
const CLASES_ESTADO: Record<string, string> = {
  Abierta: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  'Pre-ingreso': 'bg-sky-50 text-sky-700 border-sky-200',
  Suspendida: 'bg-amber-50 text-amber-700 border-amber-200',
  Ganada: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  Cancelada: 'bg-red-50 text-red-700 border-red-200',
}
export const claseEstado = (estado: string): string => CLASES_ESTADO[estado] ?? ''

/** ID visible: solo los dígitos de id_busqueda (o el id interno si no tiene). */
export function idVisible(b: Pick<Busqueda, 'id' | 'id_busqueda'>): string {
  const digitos = b.id_busqueda != null ? String(b.id_busqueda).replace(/\D/g, '') : ''
  return digitos || b.id
}

const dosDigitos = (n: number) => String(n).padStart(2, '0')

function formatearFecha(valor: string): string {
  const iso = valor.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(valor)) return valor
  const d = new Date(valor)
  if (!Number.isNaN(d.getTime())) return `${dosDigitos(d.getDate())}/${dosDigitos(d.getMonth() + 1)}/${d.getFullYear()}`
  return valor
}

/**
 * Fecha de asignación (solo fecha): el backend guarda UTC sin zona; se muestra el día en hora local. Los valores
 * históricos (solo fecha, medianoche exacta) se muestran tal cual.
 */
export function formatearFechaAsignacion(valor: string | null | undefined): string {
  if (!valor) return '—'
  const str = String(valor).trim()
  if (!str) return '—'
  const m = str.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/)
  if (!m) return formatearFecha(str)
  if (!m[4] || (m[4] === '00' && m[5] === '00' && /^\d{4}-\d{2}-\d{2}[T ]00:00(:00(\.0+)?)?$/.test(str))) {
    return `${m[3]}/${m[2]}/${m[1]}`
  }
  const d = new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(str) ? str : `${str.replace(' ', 'T')}Z`)
  if (Number.isNaN(d.getTime())) return formatearFecha(str)
  return `${dosDigitos(d.getDate())}/${dosDigitos(d.getMonth() + 1)}/${d.getFullYear()}`
}
