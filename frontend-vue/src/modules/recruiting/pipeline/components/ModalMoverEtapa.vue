<script setup lang="ts">
import { ArrowRight, Check, FileText, Info, Paperclip, X } from '@lucide/vue'
import { computed, ref } from 'vue'

import { destinosPermitidos, estiloEtapa, normalizarEtapaNombre, obtenerSiguienteEtapa, pideTransicionPretension } from '../etapas'
import {
  ACEPTA_ADJUNTO,
  errorAdjunto,
  formatearPretension,
  MAX_COMENTARIO_ETAPA,
  tamanoAdjunto,
  validarPretension,
} from '../movimientos'
import type { CandidatoPipeline, DatosAvance } from '../types'
import ModalPipeline from './ModalPipeline.vue'

/**
 * «Mover Etapa» (embudo secuencial estricto): la siguiente etapa o un salto permitido, la pretensión salarial (solo de
 * Entrevista RRHH a Entrevista Líder Dicsys), una nota de hasta 50 caracteres y un archivo adjunto opcional.
 */
const props = defineProps<{ candidato: CandidatoPipeline; guardando: boolean }>()
const emit = defineEmits<{ cerrar: []; confirmar: [datos: DatosAvance] }>()

const destinos = destinosPermitidos(props.candidato.etapa_actual)
const nuevaEtapa = ref(obtenerSiguienteEtapa(props.candidato.etapa_actual) ?? '')
const comentario = ref('')
const pretensionTexto = ref('')
const pretensionError = ref('')

const etapaActual = computed(() => props.candidato.etapa_actual || 'Screening')
const conPretension = computed(() => pideTransicionPretension(props.candidato.etapa_actual, nuevaEtapa.value))

function escribirPretension(evento: Event): void {
  pretensionError.value = ''
  pretensionTexto.value = formatearPretension((evento.target as HTMLInputElement).value)
  ;(evento.target as HTMLInputElement).value = pretensionTexto.value
}

// ---- Archivo adjunto ----
const entradaArchivo = ref<HTMLInputElement | null>(null)
const archivo = ref<File | null>(null)

function limpiarArchivo(): void {
  archivo.value = null
  if (entradaArchivo.value) entradaArchivo.value.value = ''
}

function seleccionarArchivo(evento: Event): void {
  const elegido = (evento.target as HTMLInputElement).files?.[0]
  if (!elegido) return
  // Como la pantalla anterior: un archivo de más de 10 MB o de otro formato se descarta (el campo queda vacío).
  if (errorAdjunto(elegido)) {
    limpiarArchivo()
    return
  }
  archivo.value = elegido
}

function confirmar(): void {
  if (!nuevaEtapa.value) return
  let pretension: number | null = null
  if (conPretension.value) {
    const v = validarPretension(pretensionTexto.value)
    pretensionError.value = v.error
    if (v.error) return
    pretension = v.valor
  }
  emit('confirmar', { nuevaEtapa: nuevaEtapa.value, comentario: comentario.value, pretension, archivo: archivo.value })
}
</script>

<template>
  <ModalPipeline ancho="max-w-2xl w-full mx-4 p-6 sm:p-7 gap-5" data-testid="modal-mover" @cerrar="emit('cerrar')">
    <div class="flex items-start justify-between">
      <div class="flex items-center gap-3">
        <span class="p-2 bg-primary-50 text-primary-600 rounded-xl">
          <ArrowRight class="w-5 h-5" />
        </span>
        <div>
          <h3 class="text-lg font-bold text-dark-900">Mover Etapa</h3>
          <p class="text-xs text-dark-500">{{ 'Candidato: ' + (candidato.nombre || '') }}</p>
        </div>
      </div>
      <button type="button" class="text-dark-400 hover:text-dark-600 p-1" aria-label="Cerrar" @click="emit('cerrar')">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div class="bg-dark-50 rounded-xl p-3 text-xs flex items-center justify-between">
      <span class="text-dark-500">Etapa actual:</span>
      <span
        class="inline-flex items-center gap-1.5 font-semibold px-2.5 py-1 rounded-full border"
        :class="estiloEtapa(etapaActual, candidato.estado).badge"
      >
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="estiloEtapa(etapaActual, candidato.estado).dot"></span>
        <span>{{ normalizarEtapaNombre(etapaActual) }}</span>
      </span>
    </div>

    <!-- Selector de nueva etapa del embudo (Estricto: Solo siguiente etapa inmediata) -->
    <div>
      <label for="nuevaEtapaSelect" class="block text-xs font-semibold text-dark-700 mb-1.5">Siguiente etapa del embudo:</label>
      <div class="relative">
        <select
          id="nuevaEtapaSelect"
          v-model="nuevaEtapa"
          data-testid="nueva-etapa"
          class="w-full px-3.5 py-2.5 bg-white border border-dark-200 rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option v-for="d in destinos" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
    </div>

    <!-- Pretensión salarial bruta (solo Entrevista RRHH -> Entrevista Líder Dicsys) -->
    <div v-show="conPretension">
      <label for="pretensionSalarialInput" class="block text-xs font-semibold text-dark-700 mb-1.5"
        >Pretensión salarial bruta (ARS): <span class="text-rose-600" aria-hidden="true">*</span></label
      >
      <input
        id="pretensionSalarialInput"
        type="text"
        inputmode="numeric"
        autocomplete="off"
        :value="pretensionTexto"
        placeholder="$ 1.500.000"
        class="w-full px-3.5 py-2.5 bg-white border rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
        required
        aria-required="true"
        :aria-invalid="pretensionError ? 'true' : 'false'"
        :class="pretensionError ? 'border-rose-500 focus:ring-rose-300' : 'border-dark-200'"
        @input="escribirPretension"
      />
      <p v-show="pretensionError" class="text-[11px] text-rose-600 font-medium mt-1" data-testid="error-pretension">{{ pretensionError }}</p>
      <p v-show="!pretensionError" class="text-[10px] text-dark-400 mt-1">Monto en pesos argentinos, sin decimales.</p>
    </div>

    <!-- Comentario opcional -->
    <div>
      <label for="comentarioEtapa" class="block text-xs font-semibold text-dark-700 mb-1.5">Nota o feedback de la etapa (opcional):</label>
      <textarea
        id="comentarioEtapa"
        v-model="comentario"
        rows="2"
        :maxlength="MAX_COMENTARIO_ETAPA"
        placeholder="Ej: Aprobó entrevista con muy buena predisposición. Se coordina siguiente instancia."
        class="w-full h-[60px] px-3.5 py-2 bg-white border border-dark-200 rounded-xl text-sm text-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
      ></textarea>
      <p class="text-[11px] text-dark-400 mt-1 flex items-center justify-between gap-2">
        <span>
          <Info class="w-3 h-3 inline mr-0.5" />
          Máximo 50 caracteres para la observación.
        </span>
        <span>{{ comentario.length + '/50' }}</span>
      </p>
    </div>

    <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-3 border-t border-dark-100">
      <!-- Adjuntar Archivo (Abajo a la izquierda) -->
      <div class="flex flex-col gap-1">
        <input
          ref="entradaArchivo"
          type="file"
          class="hidden"
          :accept="ACEPTA_ADJUNTO"
          data-testid="archivo-etapa"
          @change="seleccionarArchivo"
        />
        <div class="flex items-center gap-2">
          <button
            type="button"
            title="Adjuntar archivo asociado a esta etapa (opcional)"
            class="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-dark-700 bg-dark-50 hover:bg-dark-100 border border-dark-200 rounded-xl transition-colors cursor-pointer"
            @click="entradaArchivo?.click()"
          >
            <Paperclip class="w-3.5 h-3.5 text-dark-500" />
            <span>{{ archivo ? 'Cambiar archivo' : 'Adjuntar archivo' }}</span>
          </button>

          <div
            v-if="archivo"
            class="inline-flex items-center gap-1.5 bg-primary-50 border border-primary-200 text-primary-700 px-2.5 py-1 rounded-lg text-xs"
            data-testid="archivo-elegido"
          >
            <FileText class="w-3.5 h-3.5 flex-shrink-0 text-primary-600" />
            <span class="max-w-[170px] truncate font-medium" :title="archivo.name">{{ archivo.name }}</span>
            <span class="text-[10px] text-primary-500">{{ '(' + tamanoAdjunto(archivo.size) + ')' }}</span>
            <button
              type="button"
              class="text-primary-500 hover:text-rose-600 p-0.5 rounded cursor-pointer ml-0.5"
              title="Quitar archivo adjunto"
              @click="limpiarArchivo"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <p v-show="!archivo" class="text-[10px] text-dark-400">Opcional (PDF, DOCX, imágenes, etc. Máx 10 MB)</p>
      </div>

      <!-- Botones de Acción (Abajo a la derecha) -->
      <div class="flex items-center justify-end gap-2.5">
        <button
          type="button"
          class="px-4 py-2 text-sm font-semibold text-dark-600 hover:bg-dark-100 rounded-xl transition-colors cursor-pointer"
          @click="emit('cerrar')"
        >
          Cancelar
        </button>
        <button
          type="button"
          :disabled="guardando"
          data-testid="confirmar-avance"
          class="px-5 py-2 text-sm font-semibold text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50 rounded-xl shadow-soft transition-colors cursor-pointer inline-flex items-center gap-1.5"
          @click="confirmar"
        >
          <Check class="w-4 h-4" />
          <span>{{ guardando ? 'Guardando...' : 'Confirmar Avance' }}</span>
        </button>
      </div>
    </div>
  </ModalPipeline>
</template>
