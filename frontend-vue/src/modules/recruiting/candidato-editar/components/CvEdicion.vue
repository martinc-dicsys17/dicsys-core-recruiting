<script setup lang="ts">
import { AlertCircle, FileText, UploadCloud, X } from '@lucide/vue'
import { ref } from 'vue'

import { errorArchivoCv, tamanoLegible } from '../../candidato-nuevo/validacion'

/** Reemplazo del CV en la edición (mismo markup que la ficha anterior). El archivo se sube después de guardar los datos. */
defineProps<{ tieneCv: boolean }>()
const archivo = defineModel<File | null>({ required: true })

const entrada = ref<HTMLInputElement | null>(null)
const arrastrando = ref(false)
const error = ref('')

function quitar(): void {
  archivo.value = null
  if (entrada.value) entrada.value.value = ''
}

function elegir(nuevo: File | undefined): void {
  error.value = ''
  if (!nuevo) return
  const problema = errorArchivoCv(nuevo)
  if (problema) {
    error.value = problema
    quitar()
    return
  }
  archivo.value = nuevo
}

defineExpose({ quitar })
</script>

<template>
  <div>
    <input
      ref="entrada"
      type="file"
      class="hidden"
      data-testid="cv-input"
      accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      @change="elegir(($event.target as HTMLInputElement).files?.[0])"
    />

    <!-- Dropzone cuando no hay archivo nuevo seleccionado -->
    <div
      v-if="!archivo"
      role="button"
      tabindex="0"
      class="group cursor-pointer rounded-2xl border-2 border-dashed p-5 text-center transition-all"
      :class="
        arrastrando
          ? 'border-primary-500 bg-primary-50/40 ring-2 ring-primary-500/20'
          : 'border-dark-200 bg-dark-50/50 hover:border-primary-400 hover:bg-white'
      "
      @click="entrada?.click()"
      @keydown.enter.prevent="entrada?.click()"
      @dragover.prevent="arrastrando = true"
      @dragleave.prevent="arrastrando = false"
      @drop.prevent="((arrastrando = false), elegir($event.dataTransfer?.files[0]))"
    >
      <div class="flex flex-col items-center justify-center gap-2">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-600 transition-transform group-hover:scale-105">
          <UploadCloud class="h-5 w-5" />
        </div>
        <div class="text-xs text-dark-600">
          <span class="font-semibold text-primary-600 hover:underline">
            <span>{{ tieneCv ? 'Reemplazar archivo de CV' : 'Hacé click para adjuntar' }}</span>
          </span>
          o arrastrá el archivo acá
        </div>
        <p class="text-[11px] text-dark-400">Archivos permitidos: PDF, DOC o DOCX (Máx. 2MB)</p>
      </div>
    </div>

    <!-- Card de nuevo archivo seleccionado para guardar -->
    <div v-else class="flex items-center justify-between rounded-2xl border border-primary-200 bg-primary-50/30 p-3.5 transition-all">
      <div class="flex min-w-0 items-center gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-100 text-primary-700">
          <FileText class="h-5 w-5" />
        </div>
        <div class="truncate">
          <p class="truncate text-xs font-semibold text-dark-800" data-testid="cv-nombre">{{ archivo.name }}</p>
          <p class="text-[11px] text-dark-500">{{ tamanoLegible(archivo.size) }} • Listo para guardar</p>
        </div>
      </div>
      <div class="ml-3 flex shrink-0 items-center gap-2">
        <button
          type="button"
          class="rounded-lg border border-primary-200 bg-white px-2.5 py-1 text-xs font-medium text-primary-700 transition-colors hover:bg-primary-50 hover:text-primary-900"
          @click="entrada?.click()"
        >
          Cambiar
        </button>
        <button
          type="button"
          title="Cancelar subida"
          class="rounded-lg p-1.5 text-dark-400 transition-colors hover:bg-white hover:text-red-600"
          @click="quitar"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </div>

    <!-- Error específico de archivo -->
    <div v-if="error" class="mt-2 flex items-center gap-1.5 text-xs text-red-600" role="alert" data-testid="cv-error">
      <AlertCircle class="h-3.5 w-3.5 shrink-0" />
      <span>{{ error }}</span>
    </div>
  </div>
</template>
