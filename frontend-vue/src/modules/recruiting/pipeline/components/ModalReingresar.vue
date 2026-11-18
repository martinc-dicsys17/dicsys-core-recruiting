<script setup lang="ts">
import { Check, RotateCw, X } from '@lucide/vue'
import { ref } from 'vue'

import type { CandidatoPipeline } from '../types'
import ModalPipeline from './ModalPipeline.vue'

/** «Reingresar Candidato al Proceso» (excepción por cambio de perfil): vuelve a Entrevista RRHH con un motivo obligatorio. */
defineProps<{ candidato: CandidatoPipeline; guardando: boolean }>()
const emit = defineEmits<{ cerrar: []; confirmar: [motivo: string] }>()

const motivo = ref('')

function confirmar(): void {
  const texto = motivo.value.trim()
  if (texto) emit('confirmar', texto)
}
</script>

<template>
  <ModalPipeline ancho="max-w-lg w-full p-6 gap-4" data-testid="modal-reingresar" @cerrar="emit('cerrar')">
    <div class="flex items-start justify-between">
      <div class="flex items-center gap-3">
        <span class="p-2 bg-amber-50 text-amber-600 rounded-xl">
          <RotateCw class="w-5 h-5" />
        </span>
        <div>
          <h3 class="text-lg font-bold text-dark-900">Reingresar Candidato al Proceso</h3>
          <p class="text-xs text-dark-500">{{ 'Candidato: ' + (candidato.nombre || '') }}</p>
        </div>
      </div>
      <button type="button" class="text-dark-400 hover:text-dark-600 p-1" aria-label="Cerrar" @click="emit('cerrar')">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div class="bg-amber-50 rounded-xl p-3.5 text-xs text-amber-900 border border-amber-200">
      <p class="font-semibold mb-1">Excepción: Reingreso por cambio de perfil</p>
      <p>
        Si se modificaron los requerimientos de la búsqueda, el candidato se reingresará a partir de la etapa
        <strong>Entrevista RRHH</strong>, conservando todo su historial previo de evaluaciones.
      </p>
    </div>

    <!-- Etapa destino fija -->
    <div>
      <label for="etapaReingreso" class="block text-xs font-semibold text-dark-700 mb-1">Etapa de Reingreso:</label>
      <input
        id="etapaReingreso"
        type="text"
        disabled
        value="Entrevista RRHH"
        class="w-full px-3.5 py-2.5 bg-dark-50 border border-dark-200 rounded-xl text-sm font-semibold text-dark-700 cursor-not-allowed"
      />
    </div>

    <!-- Motivo de reingreso (Obligatorio) -->
    <div>
      <label for="motivoReingreso" class="block text-xs font-semibold text-dark-700 mb-1">
        Motivo del reingreso / cambio de requerimientos <span class="text-rose-500">*</span>:
      </label>
      <textarea
        id="motivoReingreso"
        v-model="motivo"
        rows="3"
        placeholder="Ej: Se flexibilizó el seniority requerido / Nuevo alcance técnico del cliente."
        class="w-full px-3.5 py-2.5 bg-white border border-dark-200 rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
        required
        data-testid="motivo-reingreso"
      ></textarea>
      <p class="text-[11px] text-dark-400 mt-1">Este motivo quedará registrado en el historial de auditoría de la postulación.</p>
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
        :disabled="!motivo.trim() || guardando"
        data-testid="confirmar-reingreso"
        class="px-5 py-2.5 text-sm font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl shadow-soft transition-colors cursor-pointer inline-flex items-center gap-1.5"
        @click="confirmar"
      >
        <Check class="w-4 h-4" />
        <span>{{ guardando ? 'Reingresando...' : 'Confirmar Reingreso' }}</span>
      </button>
    </div>
  </ModalPipeline>
</template>
