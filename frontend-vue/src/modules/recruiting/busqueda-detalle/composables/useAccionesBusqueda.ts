import { useMutation, useQueryClient } from '@tanstack/vue-query'
import type { Ref } from 'vue'

import { busquedaRepository as repo } from '../api/busqueda.repository'
import type { Oportunidad, TipoAviso } from '../types'
import { claveBusqueda } from './useBusquedaDetalle'

export type Avisar = (tipo: TipoAviso, mensaje: string) => void

/**
 * Operaciones de la ficha sobre la búsqueda (mutaciones de TanStack Query). El backend devuelve la búsqueda completa y
 * se refleja tal cual en la caché; los candidatos del proceso y las sugerencias se vuelven a pedir cuando cambian.
 */
export function useAccionesBusqueda(id: Ref<string>, avisar: Avisar) {
  const cliente = useQueryClient()
  const reflejar = (op: Oportunidad) => cliente.setQueryData(claveBusqueda(id.value), op)
  const refrescarCandidatos = () =>
    Promise.all([
      cliente.invalidateQueries({ queryKey: [...claveBusqueda(id.value), 'candidatos'] }),
      cliente.invalidateQueries({ queryKey: [...claveBusqueda(id.value), 'compatibles'] }),
      cliente.invalidateQueries({ queryKey: claveBusqueda(id.value), exact: true }),
    ])
  const textoDe = (e: unknown, porDefecto: string) => (e instanceof Error && e.message ? e.message : porDefecto)

  const guardar = useMutation({
    mutationFn: (cambios: { skills_deseadas: string[]; descripcion: string | null }) => repo.actualizar(id.value, cambios),
    onSuccess: (op) => {
      reflejar(op)
      avisar('success', 'Búsqueda actualizada correctamente.')
    },
    onError: (e) => avisar('error', textoDe(e, 'Ocurrió un error al actualizar la búsqueda.')),
  })

  const asignarReclutador = useMutation({
    mutationFn: (nombre: string) => repo.asignarReclutador(id.value, nombre),
    onSuccess: (op) => {
      reflejar(op)
      avisar('success', 'Reclutador asignado correctamente.')
    },
    onError: (e) => avisar('error', textoDe(e, 'No se pudo asignar el reclutador.')),
  })

  const asignarExterno = useMutation({
    mutationFn: (externoId: string) => repo.asignarExterno(id.value, externoId),
    onSuccess: (op) => {
      reflejar(op)
      avisar('success', 'Usuario externo asignado correctamente.')
    },
    onError: (e) => avisar('error', textoDe(e, 'No se pudo asignar el usuario externo.')),
  })

  const quitarExterno = useMutation({
    mutationFn: () => repo.quitarExterno(id.value),
    onSuccess: (op) => {
      reflejar(op)
      avisar('success', 'Asignación del usuario externo quitada.')
    },
    onError: (e) => avisar('error', textoDe(e, 'No se pudo quitar la asignación.')),
  })

  // La pantalla anterior avisaba los errores de la postulación con un `alert` del navegador y recargaba al terminar.
  const postular = useMutation({
    mutationFn: (candidatoId: string) => repo.postular(id.value, candidatoId),
    onSuccess: refrescarCandidatos,
    onError: (e) => window.alert(textoDe(e, 'Error de comunicación con el servidor')),
  })

  const cargarCv = useMutation({
    mutationFn: (archivo: File) => repo.cargarCv(id.value, archivo),
    onSuccess: async (resultado) => {
      await refrescarCandidatos()
      avisar('success', resultado.mensaje)
    },
    onError: (e) =>
      avisar('error', e instanceof Error && 'estado' in e && e.estado === 0 ? 'Error de conexión al cargar el CV.' : textoDe(e, 'No se pudo cargar el CV.')),
  })

  return { guardar, asignarReclutador, asignarExterno, quitarExterno, postular, cargarCv }
}
