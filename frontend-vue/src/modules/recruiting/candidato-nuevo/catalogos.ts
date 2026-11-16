import type { Provincia } from './types'

/** Comparación sin tildes ni mayúsculas (nombres de provincias). */
function clave(texto: string): string {
  return texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
}

const ORDEN_PROVINCIAS = ['cordoba', 'buenos aires']

/** El registro interno «No identificada» se muestra como «Otros» (igual que la pantalla anterior). */
export function nombreVisibleProvincia(nombre: string): string {
  return clave(nombre) === 'no identificada' ? 'Otros' : nombre
}

/** Córdoba, Buenos Aires y luego el resto en orden alfabético. */
export function provinciasParaMostrar(provincias: Provincia[]): Provincia[] {
  const orden = (nombre: string): [number, string] => {
    const k = clave(nombre)
    const i = ORDEN_PROVINCIAS.indexOf(k)
    return [i === -1 ? ORDEN_PROVINCIAS.length : i, k]
  }
  return provincias
    .map((p) => ({ ...p, nombre: nombreVisibleProvincia(p.nombre) }))
    .sort((a, b) => {
      const [ia, ka] = orden(a.nombre)
      const [ib, kb] = orden(b.nombre)
      return ia - ib || ka.localeCompare(kb)
    })
}

/** Nombres de un catálogo, sin vacíos y ordenados sin distinguir mayúsculas. */
export function nombresOrdenados(items: { nombre: string }[]): string[] {
  return items
    .map((i) => i.nombre)
    .filter(Boolean)
    .sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))
}
