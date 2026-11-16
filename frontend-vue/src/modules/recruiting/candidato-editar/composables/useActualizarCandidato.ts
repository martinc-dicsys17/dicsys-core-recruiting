import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { CLAVE_LISTADO } from '../../candidatos/composables/useListadoCandidatos'
import { actualizarCandidato, reemplazarCv } from '../api/editar.repository'
import type { ActualizacionCandidato } from '../types'

interface Cambios {
  id: string
  datos: ActualizacionCandidato
  cv: File | null
}

/** Guarda los datos del candidato y, si se eligió un archivo, reemplaza su CV. Si falla el guardado, falla con el mensaje. */
export function useActualizarCandidato() {
  const cliente = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, datos, cv }: Cambios) => {
      await actualizarCandidato(id, datos)
      if (cv) await reemplazarCv(id, cv)
    },
    // La grilla muestra los datos editados al volver a ella.
    onSuccess: () => cliente.invalidateQueries({ queryKey: CLAVE_LISTADO }),
  })
}
