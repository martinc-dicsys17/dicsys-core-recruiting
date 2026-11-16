import { useMutation } from '@tanstack/vue-query'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import type { FormularioCandidato } from '../types'
import { armarAlta } from '../validacion'

interface Alta {
  formulario: FormularioCandidato
  busquedaId: string
  cv: File | null
}

/**
 * Alta del candidato y, si se adjuntó, subida de su CV. Si el alta falla, la mutación falla con el mensaje
 * del backend. Si solo falla el CV, el candidato ya existe: se informa con `cvSubido: false`.
 */
export function useCrearCandidato() {
  return useMutation({
    mutationFn: async ({ formulario, busquedaId, cv }: Alta) => {
      const candidato = await repo.crear(armarAlta(formulario), busquedaId)
      let cvSubido = true
      if (cv && candidato.id) {
        try {
          await repo.subirCv(candidato.id, cv)
        } catch {
          cvSubido = false
        }
      }
      return { candidato, cvSubido }
    },
  })
}
