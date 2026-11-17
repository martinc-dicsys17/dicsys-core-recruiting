import { useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { busquedaRepository as repo } from '../api/busqueda.repository'
import { MATCH_MINIMO_POR_DEFECTO } from '../presentacion'
import type { PermisosBusquedas } from '../types'

export const claveBusqueda = (id: string) => ['recruiting', 'busqueda-detalle', id] as const

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
const DIEZ_MINUTOS = 10 * 60 * 1000

/**
 * Estado de servidor de la ficha (TanStack Query): la búsqueda, los permisos del usuario, los candidatos del proceso,
 * las sugerencias de Smart Matching y los catálogos. Como en la pantalla anterior, lo que no es la búsqueda misma
 * degrada en silencio (lista vacía / permisos restrictivos) y la ficha sigue.
 */
export function useBusquedaDetalle(id: Ref<string>, editando: Ref<boolean>) {
  const clave = (...resto: string[]) => computed(() => [...claveBusqueda(id.value), ...resto])

  const oportunidad = useQuery({
    queryKey: clave(),
    queryFn: () => repo.obtener(id.value),
    retry: false,
    gcTime: 0,
  })
  const hayBusqueda = computed(() => oportunidad.isSuccess.value)

  const consultaPermisos = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'permisos'],
    queryFn: () => repo.permisos().catch(() => SIN_PERMISOS),
    retry: false,
  })
  const permisosListos = computed(() => consultaPermisos.isFetched.value)
  const permisos = computed<PermisosBusquedas>(() => ({ ...SIN_PERMISOS, ...(consultaPermisos.data.value ?? {}) }))

  // Búsqueda Ganada = cerrada: se muestra para consulta, sin acciones que modifiquen el proceso.
  const ganada = computed(() => String(oportunidad.data.value?.estado ?? '').trim().toLowerCase() === 'ganada')
  const veSmartMatching = computed(() => permisos.value.puede_ver_smart_matching && !ganada.value)
  const puedeAsignarReclutador = computed(() => permisos.value.puede_asignar_reclutador && !ganada.value)
  const puedeAdministrarExternos = computed(() => permisos.value.puede_administrar_externos && !ganada.value)
  const puedeCargarCv = computed(() => permisos.value.es_externo && !ganada.value)

  const asignados = useQuery({
    queryKey: clave('candidatos'),
    queryFn: () => repo.candidatos(id.value).catch(() => []),
    enabled: hayBusqueda,
    retry: false,
  })

  const sugeridos = useQuery({
    queryKey: clave('compatibles'),
    queryFn: () => repo.compatibles(id.value).catch(() => []),
    enabled: computed(() => hayBusqueda.value && permisosListos.value && veSmartMatching.value),
    retry: false,
  })
  const consultaMatchMinimo = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'match-minimo'],
    queryFn: () => repo.matchMinimo().catch(() => MATCH_MINIMO_POR_DEFECTO),
    enabled: computed(() => permisosListos.value && veSmartMatching.value),
    retry: false,
  })
  const matchMinimo = computed(() => consultaMatchMinimo.data.value ?? MATCH_MINIMO_POR_DEFECTO)

  const reclutadores = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'reclutadores'],
    queryFn: () => repo.reclutadores().catch(() => []),
    enabled: hayBusqueda,
    retry: false,
    staleTime: DIEZ_MINUTOS,
  })
  const externos = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'externos'],
    queryFn: () => repo.externosDisponibles().catch(() => []),
    enabled: computed(() => permisosListos.value && puedeAdministrarExternos.value),
    retry: false,
  })

  // Catálogos del formulario de edición: solo se piden al editar (los pide el mismo permiso que Candidatos).
  const skills = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'skills'],
    queryFn: () => repo.skills().catch(() => []),
    enabled: editando,
    retry: false,
    staleTime: DIEZ_MINUTOS,
  })
  const habilidades = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'habilidades'],
    queryFn: () => repo.habilidades().catch(() => []),
    enabled: editando,
    retry: false,
    staleTime: DIEZ_MINUTOS,
  })
  const perfilesPuesto = useQuery({
    queryKey: ['recruiting', 'busqueda-detalle', 'perfiles-puesto'],
    queryFn: () => repo.perfilesPuesto(),
    enabled: editando,
    retry: false,
    staleTime: DIEZ_MINUTOS,
  })

  return {
    oportunidad,
    permisos,
    permisosListos,
    ganada,
    veSmartMatching,
    puedeAsignarReclutador,
    puedeAdministrarExternos,
    puedeCargarCv,
    asignados,
    sugeridos,
    matchMinimo,
    reclutadores,
    externos,
    skills,
    habilidades,
    perfilesPuesto,
  }
}
