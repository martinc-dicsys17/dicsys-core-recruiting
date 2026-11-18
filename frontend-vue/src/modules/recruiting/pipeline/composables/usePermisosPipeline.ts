import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { pipelineRepository as repo } from '../api/pipeline.repository'
import type { PermisosPipeline } from '../types'

const SIN_PERMISOS: PermisosPipeline = {
  puede_mover_descartar: false,
  puede_eliminar_candidatos: false,
  puede_asignar_candidatos: false,
  puede_crear_busquedas: false,
  puede_eliminar_busquedas: false,
  puede_ver_lider_tipo_fecha_busqueda: false,
  puede_ver_smart_matching: false,
  puede_cargar_cv_general: false,
  puede_cargar_cv_en_busqueda: false,
}

/** Acciones del Pipeline que ve el usuario. Restrictivo mientras carga o si falla; el backend valida cada llamada. */
export function usePermisosPipeline() {
  const consulta = useQuery({
    queryKey: ['recruiting', 'pipeline', 'permisos'],
    queryFn: () => repo.permisos().catch(() => SIN_PERMISOS),
    retry: false,
  })
  const permisos = computed<PermisosPipeline>(() => ({ ...SIN_PERMISOS, ...(consulta.data.value ?? {}) }))
  const listos = computed(() => consulta.isFetched.value)
  return { permisos, listos }
}
