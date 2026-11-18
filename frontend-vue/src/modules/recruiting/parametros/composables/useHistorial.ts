import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { parametrosRepository } from '../api/parametros.repository'

/** Historial de cargas de CV de la empresa, con filtros y paginación del servidor. */
export function useHistorial(parametros: Ref<string>) {
  return useQuery({
    queryKey: computed(() => ['recruiting', 'parametros', 'historial', parametros.value]),
    queryFn: () => parametrosRepository.historial.listar(parametros.value),
    placeholderData: keepPreviousData,
  })
}
