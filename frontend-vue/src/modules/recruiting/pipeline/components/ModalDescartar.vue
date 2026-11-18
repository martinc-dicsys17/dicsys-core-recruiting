<script setup lang="ts">
import { Trash2, UserX, X } from '@lucide/vue'
import { computed, ref, toRef, watch } from 'vue'

import { useMotivosDescarte } from '../composables/useMotivosDescarte'
import { normalizarEtapaNombre } from '../etapas'
import type { CandidatoPipeline } from '../types'
import ModalPipeline from './ModalPipeline.vue'

/** «Descartar Candidato»: motivo de la etapa activa (catálogo del backend) y observaciones opcionales. */
const props = defineProps<{ candidato: CandidatoPipeline; guardando: boolean }>()
const emit = defineEmits<{ cerrar: []; confirmar: [datos: { motivo: string; comentario: string }] }>()

const etapa = toRef(() => props.candidato.etapa_actual)
const motivos = useMotivosDescarte(etapa)
const cargando = computed(() => motivos.isFetching.value)
const error = computed(() => !cargando.value && motivos.isError.value)
const opciones = computed(() => (motivos.isError.value ? [] : (motivos.data.value ?? []).map((m) => m.motivo)))

const motivo = ref('')
const comentario = ref('')

// Al cargar los motivos queda elegido el primero; mientras carga (o si falla) no hay ninguno elegido.
watch(
  [cargando, () => motivos.data.value],
  ([enCurso, datos]) => {
    motivo.value = !enCurso && !motivos.isError.value && datos?.length ? (datos[0]?.motivo ?? '') : ''
  },
  { immediate: true },
)

const motivoValido = computed(() => !cargando.value && opciones.value.includes(motivo.value))

function confirmar(): void {
  if (motivoValido.value) emit('confirmar', { motivo: motivo.value, comentario: comentario.value })
}
</script>

<template>
  <ModalPipeline ancho="max-w-lg w-full p-6 gap-4" data-testid="modal-descartar" @cerrar="emit('cerrar')">
    <div class="flex items-start justify-between">
      <div class="flex items-center gap-3">
        <span class="p-2 bg-rose-50 text-rose-600 rounded-xl">
          <UserX class="w-5 h-5" />
        </span>
        <div>
          <h3 class="text-lg font-bold text-dark-900">Descartar Candidato</h3>
          <p class="text-xs text-dark-500">{{ 'Candidato: ' + (candidato.nombre || '') }}</p>
        </div>
      </div>
      <button type="button" class="text-dark-400 hover:text-dark-600 p-1" aria-label="Cerrar" @click="emit('cerrar')">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div class="bg-rose-50/60 rounded-xl p-3 text-xs text-rose-800 border border-rose-200/60">
      <span>Etapa activa de descarte: </span>
      <strong>{{ normalizarEtapaNombre(candidato.etapa_actual || 'Screening') }}</strong>
    </div>

    <!-- Motivo de descarte (específico de la etapa) -->
    <div>
      <label for="motivoDescarteSelect" class="block text-xs font-semibold text-dark-700 mb-1.5">Motivo de no avance / descarte / baja:</label>
      <div v-show="cargando" class="px-3.5 py-2.5 text-sm text-dark-500">Cargando motivos...</div>
      <div
        v-show="error"
        class="flex items-center justify-between gap-3 px-3.5 py-2.5 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-800"
        data-testid="error-motivos"
      >
        <span>No se pudieron cargar los motivos de descarte. Intente nuevamente.</span>
        <button type="button" class="font-semibold underline cursor-pointer" @click="motivos.refetch()">Reintentar</button>
      </div>
      <select
        v-show="!cargando && !error"
        id="motivoDescarteSelect"
        v-model="motivo"
        data-testid="motivo-descarte"
        class="w-full px-3.5 py-2.5 bg-white border border-dark-200 rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-rose-500"
      >
        <option v-for="m in opciones" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <!-- Observaciones adicionales -->
    <div>
      <label for="comentarioDescarte" class="block text-xs font-semibold text-dark-700 mb-1.5">Observaciones adicionales (opcional):</label>
      <textarea
        id="comentarioDescarte"
        v-model="comentario"
        rows="3"
        placeholder="Detalle o feedback adicional sobre el motivo de descarte..."
        class="w-full px-3.5 py-2.5 bg-white border border-dark-200 rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-rose-500 resize-none"
      ></textarea>
    </div>

    <div class="flex items-center justify-end gap-3 pt-2 border-t border-dark-100">
      <button
        type="button"
        class="px-4 py-2.5 text-sm font-semibold text-dark-600 hover:bg-dark-100 rounded-xl transition-colors cursor-pointer"
        @click="emit('cerrar')"
      >
        Cancelar
      </button>
      <button
        type="button"
        :disabled="!motivoValido || guardando"
        data-testid="confirmar-descarte"
        class="px-5 py-2.5 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-xl shadow-soft transition-colors cursor-pointer inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
        @click="confirmar"
      >
        <Trash2 class="w-4 h-4" />
        <span>Confirmar Descarte</span>
      </button>
    </div>
  </ModalPipeline>
</template>
