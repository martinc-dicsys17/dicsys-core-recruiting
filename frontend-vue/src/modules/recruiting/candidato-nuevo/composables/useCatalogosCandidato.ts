import { useQuery } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import { nombresOrdenados, provinciasParaMostrar } from '../catalogos'

const DIEZ_MINUTOS = 10 * 60 * 1000
const CLAVE = ['recruiting', 'candidato-nuevo'] as const

/** Catálogos del formulario (TanStack Query). Casi no cambian: se mantienen frescos 10 minutos. */
export function useCatalogosCandidato(provinciaId: Ref<number | null>) {
  const provincias = useQuery({
    queryKey: [...CLAVE, 'provincias'],
    queryFn: async () => provinciasParaMostrar(await repo.listarProvincias()),
    staleTime: DIEZ_MINUTOS,
  })
  // La ciudad depende de la provincia: se piden solo las de la provincia elegida.
  const ciudades = useQuery({
    queryKey: computed(() => [...CLAVE, 'ciudades', provinciaId.value]),
    queryFn: () => repo.listarCiudades(provinciaId.value as number),
    enabled: computed(() => provinciaId.value !== null),
    staleTime: DIEZ_MINUTOS,
  })
  const puestos = useQuery({
    queryKey: [...CLAVE, 'puestos'],
    queryFn: async () => (await repo.listarPerfilesPuesto()).filter((p) => p.trim()),
    staleTime: DIEZ_MINUTOS,
  })
  const seniority = useQuery({
    queryKey: [...CLAVE, 'seniority'],
    // Se respeta el orden del catálogo (de menor a mayor nivel), como la pantalla anterior.
    queryFn: async () => (await repo.listarNivelesSeniority()).map((n) => n.nombre).filter(Boolean),
    staleTime: DIEZ_MINUTOS,
  })
  const skills = useQuery({
    queryKey: [...CLAVE, 'skills'],
    queryFn: async () => nombresOrdenados(await repo.listarSkills()),
    staleTime: DIEZ_MINUTOS,
  })
  const habilidades = useQuery({
    queryKey: [...CLAVE, 'habilidades'],
    queryFn: async () => nombresOrdenados(await repo.listarHabilidades()),
    staleTime: DIEZ_MINUTOS,
  })

  return { provincias, ciudades, puestos, seniority, skills, habilidades }
}
