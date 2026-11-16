/** Reglas puras de los catálogos de los filtros del listado. */

/** Une categorías que solo difieren en mayúsculas o espacios y arma sus skills (ordenadas, sin repetir). */
export function agruparPorCategoria(
  skills: { nombre: string; categoria?: string | null }[],
): { categorias: string[]; skillsPorCategoria: Record<string, string[]> } {
  const vistas = new Map<string, string>()
  const porCategoria = new Map<string, Set<string>>()
  for (const skill of skills) {
    const original = (skill.categoria ?? '').split(/\s+/).filter(Boolean).join(' ')
    if (!original) continue
    const clave = original.toLowerCase()
    if (!vistas.has(clave)) vistas.set(clave, original)
    const nombre = (skill.nombre ?? '').split(/\s+/).filter(Boolean).join(' ')
    if (nombre) {
      const categoria = vistas.get(clave) as string
      porCategoria.set(categoria, (porCategoria.get(categoria) ?? new Set()).add(nombre))
    }
  }
  const ordenar = (a: string, b: string) => a.toLowerCase().localeCompare(b.toLowerCase())
  return {
    categorias: [...vistas.values()].sort(ordenar),
    skillsPorCategoria: Object.fromEntries([...porCategoria].map(([c, nombres]) => [c, [...nombres].sort(ordenar)])),
  }
}
