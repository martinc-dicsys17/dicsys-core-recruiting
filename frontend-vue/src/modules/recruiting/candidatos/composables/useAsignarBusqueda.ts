import { useMutation, useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { candidatosRepository as repo } from '../api/candidatos.repository'

/** Búsquedas abiertas compatibles con el candidato (Match > 50 % y todavía sin asignar), calculadas por el backend. */
export function useBusquedasElegibles(candidatoId: Ref<string | null>) {
  return useQuery({
    queryKey: computed(() => ['recruiting', 'candidatos', 'busquedas-elegibles', candidatoId.value]),
    queryFn: () => repo.busquedasElegibles(candidatoId.value as string),
    enabled: computed(() => candidatoId.value !== null),
    gcTime: 0,
    retry: false,
  })
}

export function useAsignarBusqueda() {
  return useMutation({
    mutationFn: ({ busquedaId, candidatoId }: { busquedaId: string; candidatoId: string }) =>
      repo.asignarABusqueda(busquedaId, candidatoId),
  })
}
