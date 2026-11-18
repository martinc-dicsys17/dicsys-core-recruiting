import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, type Ref } from 'vue'

import { pipelineRepository as repo } from '../api/pipeline.repository'
import { aplicarCambio } from '../movimientos'
import type { AlcanceCandidatos, BusquedaPipeline, CambioEtapa, CandidatoPipeline } from '../types'

export const claveBusqueda = (id: string) => ['recruiting', 'pipeline', 'busqueda', id] as const

/**
 * Pipeline de una búsqueda: la búsqueda y sus candidatos con el filtro de la URL. Los candidatos se piden recién
 * cuando la búsqueda se pudo abrir (si no, la pantalla vuelve a Pipeline con el aviso, como antes).
 */
export function usePipelineBusqueda(id: Ref<string>, alcance: Ref<AlcanceCandidatos>) {
  const busqueda = useQuery({
    queryKey: computed(() => claveBusqueda(id.value)),
    queryFn: () => repo.busqueda(id.value),
    retry: false,
    gcTime: 0,
  })
  const candidatos = useQuery({
    queryKey: computed(() => [...claveBusqueda(id.value), 'candidatos', alcance.value]),
    queryFn: () => repo.candidatos(id.value, alcance.value),
    enabled: computed(() => busqueda.isSuccess.value),
    retry: false,
    gcTime: 0,
  })
  return { busqueda, candidatos }
}

export interface VariablesCambio {
  candidatoId: string
  cambio: CambioEtapa
  archivo: File | null
  porDefecto: string
  /** Lo que se guarda en la fila si difiere de lo que viajó (el descarte guarda el texto tal como se escribió). */
  visible?: { motivo_descarte?: string; feedback_etapa?: string | null }
}

/**
 * Mover de etapa, descartar y reingresar. Como la pantalla anterior, la fila se actualiza en su lugar con lo que se
 * guardó (sin volver a pedir la lista); Ingreso cierra la búsqueda como Ganada.
 */
export function useCambiarEtapa(id: Ref<string>, alcance: Ref<AlcanceCandidatos>) {
  const cliente = useQueryClient()
  const cambiar = useMutation({
    mutationFn: (v: VariablesCambio) => repo.cambiarEtapa(id.value, v.candidatoId, v.cambio, v.archivo, v.porDefecto),
    onSuccess: (resultado, v) => {
      if (!resultado.ok) return
      cliente.setQueryData<CandidatoPipeline[]>([...claveBusqueda(id.value), 'candidatos', alcance.value], (lista) =>
        lista ? aplicarCambio(lista, v.candidatoId, v.cambio, v.visible) : lista,
      )
    },
  })
  const marcarGanada = () =>
    cliente.setQueryData<BusquedaPipeline>(claveBusqueda(id.value), (op) => (op ? { ...op, estado: 'Ganada' } : op))
  return { cambiar, marcarGanada }
}
