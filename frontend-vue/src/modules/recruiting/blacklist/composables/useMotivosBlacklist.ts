import { useQuery } from '@tanstack/vue-query'

import { listarMotivos } from '../api/blacklist.repository'

/** Catálogo de motivos de Blacklist (TanStack Query). Casi no cambia: se mantiene fresco 10 minutos. */
export function useMotivosBlacklist() {
  const motivos = useQuery({
    queryKey: ['recruiting', 'blacklist', 'motivos'],
    queryFn: listarMotivos,
    staleTime: 10 * 60 * 1000,
  })
  return { motivos }
}
