import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { busquedasRepository as repo } from '../api/busquedas.repository'
import type { PermisosBusquedas } from '../types'

const SIN_PERMISOS: PermisosBusquedas = {
  puede_crear_busquedas: false,
  puede_eliminar_busquedas: false,
  puede_ver_lider_tipo_fecha_busqueda: false,
  puede_ver_smart_matching: false,
  puede_asignar_candidatos: false,
  puede_asignar_reclutador: false,
  puede_administrar_externos: false,
  es_externo: false,
}

/** Acciones habilitadas del usuario. Restrictivo mientras carga o si falla; el backend valida cada llamada. */
export function usePermisosBusquedas() {
  const consulta = useQuery({ queryKey: ['recruiting', 'busquedas', 'permisos'], queryFn: repo.permisos })
  const permisos = computed(() => ({ ...SIN_PERMISOS, ...(consulta.data.value ?? {}) }))
  return { permisos, consulta }
}
