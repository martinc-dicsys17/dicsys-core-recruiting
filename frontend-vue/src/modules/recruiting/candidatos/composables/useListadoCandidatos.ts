import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import { parametrosApi } from '../filtros'
import type { FiltrosListado } from '../types'

export const CLAVE_LISTADO = ['recruiting', 'candidatos', 'listado'] as const

/**
 * Listado paginado contra el backend (paginación del servidor). Se espera a tener las opciones de los filtros
 * (`habilitado`) para validar la skill contra su categoría antes de consultar; mientras cambia la página se
 * mantiene la anterior a la vista.
 */
export function useListadoCandidatos(
  filtros: Ref<FiltrosListado>,
  skillsDeLaCategoria: Ref<string[]>,
  habilitado: Ref<boolean>,
) {
  const parametros = computed(() => parametrosApi(filtros.value, skillsDeLaCategoria.value).toString())
  return useQuery({
    queryKey: computed(() => [...CLAVE_LISTADO, parametros.value]),
    queryFn: () => repo.listar(new URLSearchParams(parametros.value)),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  })
}

export function useEliminarCandidato() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => repo.eliminar(id),
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_LISTADO }),
  })
}
