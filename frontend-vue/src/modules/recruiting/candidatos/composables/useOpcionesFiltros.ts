import { useQuery } from '@tanstack/vue-query'

import { candidatosRepository as catalogos } from '../../candidato-nuevo/api/candidatos.repository'
import { nombreVisibleProvincia, provinciasParaMostrar } from '../../candidato-nuevo/catalogos'
import { candidatosRepository as repo } from '../api/candidatos.repository'
import { agruparPorCategoria } from '../catalogos'
import type { OpcionesFiltros } from '../types'

const DIEZ_MINUTOS = 10 * 60 * 1000

/**
 * Opciones de los filtros (TanStack Query), de los catálogos reales. Si un catálogo falla, ese filtro queda
 * sin opciones y el resto sigue funcionando (como la pantalla anterior).
 */
export function useOpcionesFiltros() {
  return useQuery({
    queryKey: ['recruiting', 'candidatos', 'opciones-filtros'],
    staleTime: DIEZ_MINUTOS,
    queryFn: async (): Promise<OpcionesFiltros> => {
      const [provincias, skills, perfiles, niveles] = await Promise.allSettled([
        catalogos.listarProvincias(),
        repo.listarSkillsConCategoria(),
        catalogos.listarPerfilesPuesto(),
        catalogos.listarNivelesSeniority(),
      ])
      const valor = <T>(r: PromiseSettledResult<T>, vacio: T): T => (r.status === 'fulfilled' ? r.value : vacio)
      // «No identificada» se filtra con la opción fija «Otros» de la pantalla.
      const nombresProvincias = provinciasParaMostrar(valor(provincias, []))
        .map((p) => p.nombre)
        .filter((n) => n !== nombreVisibleProvincia('No identificada'))
      return {
        provincias: nombresProvincias,
        ...agruparPorCategoria(valor(skills, [])),
        perfiles: valor(perfiles, []).filter((p) => p.trim()),
        // Se respeta el orden del catálogo (de menor a mayor nivel).
        niveles: nombresOrdenadosSinReordenar(valor(niveles, [])),
      }
    },
  })
}

const nombresOrdenadosSinReordenar = (items: { nombre: string }[]): string[] =>
  items.map((i) => i.nombre).filter(Boolean)

