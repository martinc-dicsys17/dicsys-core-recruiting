import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { pipelineRepository as repo } from '../api/pipeline.repository'
import type { AlcanceCandidatos, CandidatoColumna } from '../types'

const CLAVE = ['recruiting', 'pipeline'] as const

/**
 * Datos de la pantalla Pipeline: el resumen de la vista global o las búsquedas Abiertas de la selección individual
 * (cada uno solo cuando su vista está activa), con el filtro de candidatos de la URL.
 */
export function useVistaGlobal(vista: Ref<'global' | 'individual'>, alcance: Ref<AlcanceCandidatos>) {
  const resumen = useQuery({
    queryKey: computed(() => [...CLAVE, 'resumen', alcance.value]),
    queryFn: () => repo.resumen(alcance.value),
    enabled: computed(() => vista.value === 'global'),
    retry: false,
  })
  const abiertas = useQuery({
    queryKey: [...CLAVE, 'busquedas-abiertas'],
    queryFn: () => repo.busquedasAbiertas(),
    enabled: computed(() => vista.value === 'individual'),
    retry: false,
  })
  return { resumen, abiertas }
}

/**
 * Candidatos de una cifra de la vista global (detalle emergente). Lo que ya se pidió queda en caché mientras la
 * pantalla está abierta, como antes; un error no se guarda y se vuelve a pedir al pasar de nuevo el mouse.
 */
export function useCandidatosColumna() {
  const cliente = useQueryClient()
  const clave = (busquedaId: string, columna: string, alcance: AlcanceCandidatos) =>
    [...CLAVE, 'columna', busquedaId, columna, alcance] as const

  return {
    enCache: (busquedaId: string, columna: string, alcance: AlcanceCandidatos) =>
      cliente.getQueryData<CandidatoColumna[]>(clave(busquedaId, columna, alcance)),
    pedir: (busquedaId: string, columna: string, alcance: AlcanceCandidatos) =>
      cliente.fetchQuery({
        queryKey: clave(busquedaId, columna, alcance),
        queryFn: async () => {
          const datos = await repo.candidatosDeColumna(busquedaId, columna, alcance)
          return Array.isArray(datos) ? datos : []
        },
        staleTime: Infinity,
        retry: false,
      }),
  }
}
