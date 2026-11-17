import type { FiltrosBusquedas, TipoBusqueda } from './types'

/** Filtros y paginación del listado: se leen y escriben en la URL con los nombres de la pantalla anterior. */

export const ESTADOS = ['Abierta', 'Pre-ingreso', 'Suspendida', 'Ganada', 'Cancelada'] as const
export const LIMITES = [20, 50, 100] as const
const TIPOS: TipoBusqueda[] = ['Efectiva', 'Potencial', 'Todas']

type Query = Record<string, unknown>

function texto(valor: unknown): string {
  const primero = Array.isArray(valor) ? valor[0] : valor
  return typeof primero === 'string' ? primero.trim() : ''
}

function entero(valor: unknown): number | null {
  const n = Number.parseInt(texto(valor), 10)
  return Number.isFinite(n) ? n : null
}

/** El tamaño de página se acota a 20, 50 o 100 (como el listado anterior). */
export function normalizarLimite(valor: number | null): number {
  if (valor === null || valor <= 20) return 20
  return valor <= 50 ? 50 : 100
}

export function filtrosVacios(): FiltrosBusquedas {
  return { busqueda: '', estado: 'Abierta', tipo: 'Efectiva', pagina: 1, limite: 20 }
}

/** Filtros desde la URL: un estado o tipo inválido vuelve al predeterminado (Abierta, Efectiva). */
export function filtrosDesdeQuery(query: Query): FiltrosBusquedas {
  const estado = texto(query.estado) || 'Abierta'
  const tipo = texto(query.tipo) as TipoBusqueda
  return {
    busqueda: texto(query.busqueda),
    estado: estado === 'todos' || (ESTADOS as readonly string[]).includes(estado) ? estado : 'Abierta',
    tipo: TIPOS.includes(tipo) ? tipo : 'Efectiva',
    pagina: Math.max(1, entero(query.pagina) ?? 1),
    limite: normalizarLimite(entero(query.por_pagina)),
  }
}

/** Query de la URL: estado, tipo y por_pagina siempre; la búsqueda y la página solo si tienen valor. */
export function queryDesdeFiltros(f: FiltrosBusquedas): Record<string, string> {
  const q: Record<string, string> = { estado: f.estado, tipo: f.tipo, por_pagina: String(f.limite) }
  if (f.busqueda) q.busqueda = f.busqueda
  if (f.pagina > 1) q.pagina = String(f.pagina)
  return q
}

/** Parámetros del GET /oportunidades. El tipo solo se elige con permiso (EXTERNOS solo ve las efectivas). */
export function parametrosApi(f: FiltrosBusquedas, puedeElegirTipo: boolean): URLSearchParams {
  const p = new URLSearchParams({
    pagina: String(f.pagina),
    por_pagina: String(f.limite),
    estado: f.estado,
    tipo: puedeElegirTipo ? f.tipo : 'Efectiva',
  })
  if (f.busqueda) p.set('busqueda', f.busqueda)
  return p
}

export function rangoRegistros(pagina: number, limite: number, total: number): { desde: number; hasta: number } {
  if (total <= 0) return { desde: 0, hasta: 0 }
  return { desde: (pagina - 1) * limite + 1, hasta: Math.min(pagina * limite, total) }
}
