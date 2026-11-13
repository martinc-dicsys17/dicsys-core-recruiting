import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import { blacklistRepository } from '../api/blacklist.repository'
import type { PersonaBlacklist } from '../types'

const CLAVE = ['recruiting', 'blacklist'] as const

/** Estado de servidor de Blacklist (TanStack Query): listado y reactivacion de personas. */
export function useBlacklist() {
  const cliente = useQueryClient()

  const listado = useQuery({ queryKey: CLAVE, queryFn: () => blacklistRepository.listar() })

  // Actualizacion optimista: la persona sale de la grilla al instante y vuelve si la operacion falla.
  const reactivar = useMutation({
    mutationFn: (persona: PersonaBlacklist) => blacklistRepository.reactivar(persona.id),
    async onMutate(persona) {
      await cliente.cancelQueries({ queryKey: CLAVE })
      const anterior = cliente.getQueryData<PersonaBlacklist[]>(CLAVE)
      cliente.setQueryData<PersonaBlacklist[]>(CLAVE, (actual) => actual?.filter((p) => p.id !== persona.id))
      return { anterior }
    },
    onError(_error, _persona, contexto) {
      cliente.setQueryData(CLAVE, contexto?.anterior)
    },
    onSettled: () => cliente.invalidateQueries({ queryKey: CLAVE }),
  })

  return { listado, reactivar }
}
