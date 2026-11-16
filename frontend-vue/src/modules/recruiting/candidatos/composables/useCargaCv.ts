import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import { CLAVE_LISTADO } from './useListadoCandidatos'

/** Carga individual de un CV; `confirmar` reemplaza el CV de un candidato existente (tras la comparación). */
export function useCargaCv() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: ({ archivo, confirmar }: { archivo: File; confirmar: boolean }) => repo.cargarCv(archivo, confirmar),
    onSuccess: (resultado) => {
      if (resultado.tipo === 'ok') void cliente.invalidateQueries({ queryKey: CLAVE_LISTADO })
    },
  })
}
