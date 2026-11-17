import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { busquedasRepository as repo } from '../api/busquedas.repository'
import { parametrosApi } from '../filtros'
import type { Busqueda, ExternoDisponible, FiltrosBusquedas, PaginaBusquedas } from '../types'

export const CLAVE_LISTADO = ['recruiting', 'busquedas', 'listado'] as const

/** Listado paginado contra el backend. Espera a conocer los permisos (de ellos depende el filtro de tipo). */
export function useListadoBusquedas(
  filtros: Ref<FiltrosBusquedas>,
  puedeElegirTipo: Ref<boolean>,
  habilitado: Ref<boolean>,
) {
  const parametros = computed(() => parametrosApi(filtros.value, puedeElegirTipo.value).toString())
  return useQuery({
    queryKey: computed(() => [...CLAVE_LISTADO, parametros.value]),
    queryFn: () => repo.listar(new URLSearchParams(parametros.value)),
    enabled: habilitado,
    placeholderData: keepPreviousData,
  })
}

export function useExternosDisponibles(habilitado: Ref<boolean>) {
  return useQuery<ExternoDisponible[]>({
    queryKey: ['recruiting', 'busquedas', 'externos-disponibles'],
    queryFn: repo.externosDisponibles,
    enabled: habilitado,
  })
}

/**
 * Como la pantalla anterior, la fila se actualiza en su lugar con la respuesta (una búsqueda cancelada o con otro
 * externo sigue a la vista hasta que se vuelve a filtrar o a cargar la página).
 */
function useActualizarFila<V>(accion: (variables: V) => Promise<Busqueda>) {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: accion,
    onSuccess: (nueva) => {
      cliente.setQueriesData<PaginaBusquedas>({ queryKey: CLAVE_LISTADO }, (pagina) =>
        pagina ? { ...pagina, items: pagina.items.map((b) => (b.id === nueva.id ? { ...b, ...nueva } : b)) } : pagina,
      )
    },
  })
}

export const useCancelarBusqueda = () => useActualizarFila((id: string) => repo.cancelar(id))
export const useAsignarExterno = () =>
  useActualizarFila((v: { id: string; externoId: string }) => repo.asignarExterno(v.id, v.externoId))
export const useQuitarExterno = () => useActualizarFila((id: string) => repo.quitarExterno(id))
