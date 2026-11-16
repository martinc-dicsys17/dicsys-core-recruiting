import type { FiltrosListado } from './types'

/** Filtros y paginación del listado: se leen y escriben en la URL con los nombres de la pantalla anterior. */

export const LIMITES = [20, 50, 100] as const
export const LIMITE_POR_DEFECTO = 20
export const RUTA_LISTADO = '/recruiting/candidatos'

type Query = Record<string, unknown>

/** Primer valor de un parámetro de la URL (puede venir repetido o como lista). */
function texto(valor: unknown): string {
  const primero = Array.isArray(valor) ? valor[0] : valor
  return typeof primero === 'string' ? primero.replace(/\s+/g, ' ').trim() : ''
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

export function filtrosVacios(limite = LIMITE_POR_DEFECTO): FiltrosListado {
  return {
    busqueda: '',
    seniority: '',
    ubicacion: '',
    puesto: '',
    categoria: '',
    skill: '',
    estado: '',
    fuente: '',
    pagina: 1,
    limite,
  }
}

/** Filtros desde la query de la URL (acepta también los alias `search`, `q` y `pagina`/`por_pagina`). */
export function filtrosDesdeQuery(query: Query): FiltrosListado {
  return {
    busqueda: texto(query.busqueda) || texto(query.search) || texto(query.q),
    seniority: texto(query.seniority),
    ubicacion: texto(query.ubicacion),
    puesto: texto(query.puesto),
    categoria: texto(query.categorias),
    skill: texto(query.skills),
    estado: texto(query.estado),
    fuente: texto(query.fuente),
    pagina: Math.max(1, entero(query.page) ?? entero(query.pagina) ?? 1),
    limite: normalizarLimite(entero(query.limit) ?? entero(query.por_pagina)),
  }
}

/**
 * Query de la URL (page y limit siempre, como la pantalla anterior; el resto solo si tiene valor).
 * La skill solo viaja si hay categoría: es una skill de esa categoría.
 */
export function queryDesdeFiltros(f: FiltrosListado): Record<string, string> {
  const query: Record<string, string> = { page: String(f.pagina), limit: String(f.limite) }
  const opcionales: [string, string][] = [
    ['busqueda', f.busqueda],
    ['seniority', f.seniority],
    ['ubicacion', f.ubicacion],
    ['puesto', f.puesto],
    ['categorias', f.categoria],
    ['skills', f.categoria ? f.skill : ''],
    ['fuente', f.fuente],
    ['estado', f.estado],
  ]
  for (const [clave, valor] of opcionales) if (valor) query[clave] = valor
  return query
}

/**
 * Parámetros del GET /recruiting/candidatos. La skill se envía solo si pertenece a la categoría elegida
 * (`skillsDeLaCategoria`), igual que hacía la pantalla anterior.
 */
export function parametrosApi(f: FiltrosListado, skillsDeLaCategoria: string[]): URLSearchParams {
  const parametros = new URLSearchParams({ pagina: String(f.pagina), por_pagina: String(f.limite) })
  const opcionales: [string, string][] = [
    ['busqueda', f.busqueda],
    ['estado', f.estado],
    ['fuente', f.fuente],
    ['seniority', f.seniority],
    ['ubicacion', f.ubicacion],
    ['puesto', f.puesto],
  ]
  for (const [clave, valor] of opcionales) if (valor) parametros.set(clave, valor)
  if (f.categoria) {
    parametros.append('categorias', f.categoria)
    if (f.skill && skillsDeLaCategoria.includes(f.skill)) parametros.append('skills', f.skill)
  }
  return parametros
}

/**
 * URL de la grilla en la ruta de Flask (la que valida el parámetro `volver` de las demás pantallas): al volver
 * se conservan los filtros y la página.
 */
export function urlDeVuelta(f: FiltrosListado): string {
  return `${RUTA_LISTADO}?${new URLSearchParams(queryDesdeFiltros(f)).toString()}`
}

/** «Mostrando X a Y de Z»: primer y último registro de la página (0 y 0 si no hay). */
export function rangoRegistros(pagina: number, limite: number, total: number): { desde: number; hasta: number } {
  if (total <= 0) return { desde: 0, hasta: 0 }
  return { desde: (pagina - 1) * limite + 1, hasta: Math.min(pagina * limite, total) }
}

/** Skills visibles en la fila y las ocultas (se ven en el tooltip del «+N»). */
export function dividirSkills(skills: string[], visibles = 2): { visibles: string[]; ocultas: string[] } {
  return { visibles: skills.slice(0, visibles), ocultas: skills.slice(visibles) }
}

/** Color del estado de la fila; un candidato dado de baja se muestra como tal. */
export function estadoParaMostrar(estado: string | undefined, activo: boolean): { texto: string; clases: string } {
  if (!activo) return { texto: 'Dado de baja', clases: 'bg-gray-100 text-gray-700 border border-gray-200' }
  const texto = estado || 'Activo'
  if (texto === 'Activo') return { texto, clases: 'bg-emerald-100 text-emerald-700' }
  if (texto === 'Rechazado') return { texto, clases: 'bg-red-100 text-red-700' }
  if (texto === 'Baja del proceso') return { texto, clases: 'bg-dark-100 text-dark-600' }
  return { texto, clases: 'bg-amber-100 text-amber-700' }
}
