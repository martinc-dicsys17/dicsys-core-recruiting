import { useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { candidatosRepository as catalogos } from '../../candidato-nuevo/api/candidatos.repository'
import { provinciasParaMostrar } from '../../candidato-nuevo/catalogos'
import { obtenerCandidato } from '../api/candidato.repository'
import { ciudadInicial, provinciaInicial } from '../presentacion'

const DIEZ_MINUTOS = 10 * 60 * 1000

/**
 * Estado de servidor de la ficha (TanStack Query): el candidato y los catálogos que necesita para mostrar su
 * ubicación y el aviso de perfiles de puesto. Si un catálogo falla, queda vacío y la ficha sigue (como antes).
 */
export function useCandidatoDetalle(id: Ref<string>) {
  const candidato = useQuery({
    queryKey: computed(() => ['recruiting', 'candidato-detalle', id.value]),
    queryFn: () => obtenerCandidato(id.value),
    retry: false,
    gcTime: 0,
  })

  const provincias = useQuery({
    queryKey: ['recruiting', 'candidato-detalle', 'provincias'],
    queryFn: async () => provinciasParaMostrar(await catalogos.listarProvincias()),
    staleTime: DIEZ_MINUTOS,
    retry: false,
  })

  const provinciaId = computed(() =>
    candidato.data.value && provincias.data.value ? provinciaInicial(candidato.data.value, provincias.data.value) : null,
  )
  const ciudades = useQuery({
    queryKey: computed(() => ['recruiting', 'candidato-detalle', 'ciudades', provinciaId.value]),
    queryFn: () => catalogos.listarCiudades(provinciaId.value as number),
    enabled: computed(() => provinciaId.value !== null),
    staleTime: DIEZ_MINUTOS,
    retry: false,
  })

  const perfilesPuesto = useQuery({
    queryKey: ['recruiting', 'candidato-detalle', 'perfiles-puesto'],
    queryFn: async () => (await catalogos.listarPerfilesPuesto()).filter((p) => p.trim()),
    staleTime: DIEZ_MINUTOS,
    retry: false,
  })

  const ciudadId = computed(() =>
    candidato.data.value ? ciudadInicial(candidato.data.value, provinciaId.value, ciudades.data.value ?? []) : null,
  )

  // La ficha espera a los catálogos para no mostrar la ubicación ni los avisos a medias.
  const listo = computed(
    () =>
      candidato.isSuccess.value &&
      !provincias.isPending.value &&
      (provinciaId.value === null || !ciudades.isPending.value) &&
      !perfilesPuesto.isPending.value,
  )

  return { candidato, provincias, ciudades, perfilesPuesto, provinciaId, ciudadId, listo }
}
