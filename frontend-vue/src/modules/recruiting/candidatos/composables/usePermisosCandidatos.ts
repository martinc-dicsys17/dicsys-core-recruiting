import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import type { PermisosCandidatos } from '../types'

const SIN_PERMISOS: PermisosCandidatos = {
  puede_eliminar_candidatos: false,
  puede_cargar_cv_general: false,
  puede_carga_masiva: false,
  puede_asignar_candidatos: false,
}

/** Acciones habilitadas del usuario. Restrictivo mientras carga o si falla; el backend valida cada llamada. */
export function usePermisosCandidatos() {
  const consulta = useQuery({ queryKey: ['recruiting', 'candidatos', 'permisos'], queryFn: repo.permisos })
  const permisos = computed(() => ({ ...SIN_PERMISOS, ...(consulta.data.value ?? {}) }))
  return { permisos, consulta }
}
