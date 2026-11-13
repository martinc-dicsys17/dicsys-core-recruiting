import type { PersonaBlacklist } from './types'

/** Estilo neutro de la etiqueta (PrimeVue Tag) y del punto de todos los motivos. */
export const ESTILO_MOTIVO = {
  etiqueta: 'bg-slate-100 text-slate-700 ring-slate-400/30',
  punto: 'bg-slate-500',
} as const

const FONDOS_AVATAR = [
  'from-bordo-700 to-dark-900',
  'from-bordo-600 to-bordo-800',
  'from-dark-800 to-dark-950',
  'from-rose-700 to-bordo-900',
  'from-bordo-800 to-slate-900',
] as const

/** Degradado del avatar: estable para cada persona (depende de su id). */
export function fondoAvatar(p: PersonaBlacklist): string {
  let suma = 0
  for (const letra of p.id) suma += letra.charCodeAt(0)
  return FONDOS_AVATAR[suma % FONDOS_AVATAR.length] ?? FONDOS_AVATAR[0]
}

export function iniciales(p: PersonaBlacklist): string {
  return `${p.nombre.charAt(0)}${p.apellido.charAt(0)}`.toUpperCase()
}

/** Fecha ISO (AAAA-MM-DD) en formato local, sin corrimiento por zona horaria. */
export function formatearFecha(iso: string, mes: 'short' | 'long' = 'short'): string {
  const [anio = 0, mesNumero = 1, dia = 1] = iso.split('-').map(Number)
  return new Intl.DateTimeFormat('es-AR', { day: '2-digit', month: mes, year: 'numeric' }).format(
    new Date(anio, mesNumero - 1, dia),
  )
}
