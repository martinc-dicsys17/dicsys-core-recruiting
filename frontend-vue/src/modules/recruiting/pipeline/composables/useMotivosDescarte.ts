import { useQuery } from '@tanstack/vue-query'
import type { Ref } from 'vue'

import { pipelineRepository as repo } from '../api/pipeline.repository'
import { normalizarEtapaNombre } from '../etapas'

/**
 * Motivos de descarte de la etapa del candidato. Se piden cada vez que se abre el modal (sin caché entre aperturas),
 * como la pantalla anterior; «Reintentar» los vuelve a pedir.
 */
export function useMotivosDescarte(etapa: Ref<string>) {
  return useQuery({
    queryKey: ['recruiting', 'pipeline', 'motivos-descarte', etapa],
    queryFn: () => repo.motivosDescarte(normalizarEtapaNombre(etapa.value)),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  })
}
