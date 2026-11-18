import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { parametrosRepository } from '../api/parametros.repository'
import type { RegistroAbm } from '../types'

/** Operaciones comunes de un catálogo de Parámetros (con o sin baja lógica). */
export interface RecursoAbm {
  listar: (parametros?: string) => Promise<RegistroAbm[]>
  crear: (datos: Record<string, unknown>) => Promise<RegistroAbm>
  actualizar: (id: string | number, datos: Record<string, unknown>) => Promise<RegistroAbm>
  desactivar?: (id: string | number) => Promise<RegistroAbm>
  eliminar?: (id: string | number) => Promise<unknown>
}

const RECURSOS: Record<string, RecursoAbm> = {
  skills: parametrosRepository.skills,
  habilidades: parametrosRepository.habilidades,
  lideres: parametrosRepository.lideres,
  reclutadores: parametrosRepository.reclutadores,
  'perfiles-puesto': parametrosRepository.perfiles,
  provincias: parametrosRepository.provincias,
  ciudades: parametrosRepository.ciudades,
  'motivos-blacklist': parametrosRepository.motivos,
}

/**
 * Estado de servidor de un ABM de Parámetros: listado (con inactivos) y altas, ediciones y bajas. Al guardar o dar de
 * baja se invalida el listado para traer los datos reales del backend.
 */
export function useAbm(ruta: string, parametros?: Ref<string>) {
  const cliente = useQueryClient()
  const recurso = RECURSOS[ruta]
  if (!recurso) throw new Error(`Catálogo de Parámetros desconocido: ${ruta}`)

  const clave = computed(() => ['recruiting', 'parametros', ruta, parametros?.value ?? ''] as const)
  const listado = useQuery({
    queryKey: clave,
    queryFn: () => recurso.listar(parametros?.value ?? ''),
  })

  const invalidar = () => cliente.invalidateQueries({ queryKey: ['recruiting', 'parametros', ruta] })

  const crear = useMutation({
    mutationFn: (datos: Record<string, unknown>) => recurso.crear(datos),
    onSuccess: invalidar,
  })
  const actualizar = useMutation({
    mutationFn: (cambio: { id: string | number; datos: Record<string, unknown> }) =>
      recurso.actualizar(cambio.id, cambio.datos),
    onSuccess: invalidar,
  })
  const desactivar = useMutation({
    mutationFn: (id: string | number) => {
      if (!recurso.desactivar) throw new Error('El catálogo no tiene baja lógica.')
      return recurso.desactivar(id)
    },
    onSuccess: invalidar,
  })
  const eliminar = useMutation({
    mutationFn: (id: string | number) => {
      if (!recurso.eliminar) throw new Error('El catálogo no tiene borrado.')
      return recurso.eliminar(id)
    },
    onSuccess: invalidar,
  })

  return { listado, crear, actualizar, desactivar, eliminar }
}

export function useConfig() {
  const cliente = useQueryClient()
  const clave = ['recruiting', 'parametros', 'config'] as const
  const consulta = useQuery({
    queryKey: clave,
    queryFn: () => parametrosRepository.config.obtener(),
  })
  const guardar = useMutation({
    mutationFn: (valor: number) => parametrosRepository.config.guardar(valor),
    onSuccess: (datos) => cliente.setQueryData(clave, datos),
  })
  return { consulta, guardar }
}

/** Provincias para los combos de Ciudades (filtro y formulario). */
export function useProvincias() {
  return useQuery({
    queryKey: ['recruiting', 'parametros', 'provincias', 'opciones'],
    queryFn: () => parametrosRepository.provincias.listar(),
  })
}
