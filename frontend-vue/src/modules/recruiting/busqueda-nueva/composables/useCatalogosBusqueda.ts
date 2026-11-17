import { useQuery } from '@tanstack/vue-query'

import { nuevaBusquedaRepository as repo } from '../api/nueva-busqueda.repository'

const DIEZ_MINUTOS = 10 * 60 * 1000
const CLAVE = ['recruiting', 'busqueda-nueva'] as const

const ordenAlfabetico = (a: string, b: string) => a.localeCompare(b, undefined, { sensitivity: 'base' })
const nombres = (items: { nombre?: string }[]) => items.map((i) => i.nombre ?? '').filter(Boolean)

/** Permiso de creación (restrictivo mientras carga o si falla; el backend lo valida de nuevo al guardar). */
export function usePermisoCrearBusqueda() {
  return useQuery({ queryKey: [...CLAVE, 'permisos'], queryFn: repo.permisos })
}

/** Catálogos del formulario. Casi no cambian: se mantienen frescos 10 minutos. */
export function useCatalogosBusqueda() {
  const puestos = useQuery({
    queryKey: [...CLAVE, 'puestos'],
    queryFn: async () => (await repo.listarPerfilesPuesto()).filter((p) => typeof p === 'string' && p.trim()),
    staleTime: DIEZ_MINUTOS,
  })
  const skills = useQuery({
    queryKey: [...CLAVE, 'skills'],
    queryFn: async () => nombres(await repo.listarSkills()).sort(ordenAlfabetico),
    staleTime: DIEZ_MINUTOS,
  })
  const habilidades = useQuery({
    queryKey: [...CLAVE, 'habilidades'],
    queryFn: async () => nombres(await repo.listarHabilidades()).sort(ordenAlfabetico),
    staleTime: DIEZ_MINUTOS,
  })
  // Líderes y reclutadores se respetan en el orden del catálogo (como la pantalla anterior).
  const lideres = useQuery({
    queryKey: [...CLAVE, 'lideres'],
    queryFn: async () => nombres(await repo.listarLideres()),
    staleTime: DIEZ_MINUTOS,
  })
  const reclutadores = useQuery({
    queryKey: [...CLAVE, 'reclutadores'],
    queryFn: async () => nombres(await repo.listarReclutadores()),
    staleTime: DIEZ_MINUTOS,
  })
  return { puestos, skills, habilidades, lideres, reclutadores }
}
