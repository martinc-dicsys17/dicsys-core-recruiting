import { keepPreviousData, useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { parametrosRepository } from '../api/parametros.repository'

/** Carpetas de CV archivadas (cantidad de archivos y espacio ocupado). */
export function useCarpetasCv() {
  return useQuery({
    queryKey: ['recruiting', 'parametros', 'archivos-cv', 'resumen'],
    queryFn: () => parametrosRepository.archivos.resumen(),
  })
}

/**
 * Archivos de la carpeta seleccionada, con la paginación y la búsqueda resueltas por el backend. Mientras se pide otra
 * página se mantiene la anterior a la vista.
 */
export function useDetalleCarpeta(carpeta: Ref<string | null>, parametros: Ref<string>) {
  return useQuery({
    queryKey: computed(() => ['recruiting', 'parametros', 'archivos-cv', carpeta.value ?? '', parametros.value]),
    queryFn: () => parametrosRepository.archivos.detalle(carpeta.value ?? '', parametros.value),
    enabled: computed(() => Boolean(carpeta.value)),
    placeholderData: keepPreviousData,
  })
}
