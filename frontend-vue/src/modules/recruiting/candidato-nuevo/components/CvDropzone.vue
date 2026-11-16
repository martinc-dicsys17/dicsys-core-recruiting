<script setup lang="ts">
import { AlertCircle, FileText, UploadCloud, X } from '@lucide/vue'
import { ref } from 'vue'

import { errorArchivoCv, tamanoLegible } from '../validacion'

/** Adjunto opcional del CV (PDF, DOC o DOCX, hasta 2 MB). El archivo se sube después de crear el candidato. */
const archivo = defineModel<File | null>({ required: true })

const entrada = ref<HTMLInputElement | null>(null)
const arrastrando = ref(false)
const error = ref('')

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

function quitar(): void {
  archivo.value = null
  if (entrada.value) entrada.value.value = ''
}

function alSeleccionar(evento: Event): void {
  elegir((evento.target as HTMLInputElement).files?.[0])
}

function alSoltar(evento: DragEvent): void {
  arrastrando.value = false
  elegir(evento.dataTransfer?.files[0])
}
</script>

<template>
  <div>
    <label class="mb-1 block text-xs font-semibold text-dark-600">Curriculum Vitae (CV)</label>
    <input
      ref="entrada"
      type="file"
      class="hidden"
      data-testid="cv-input"
      accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      @change="alSeleccionar"
    />

    <div
      v-if="!archivo"
      role="button"
      tabindex="0"
      class="group cursor-pointer rounded-2xl border-2 border-dashed p-5 text-center transition-all"
      :class="
        arrastrando
          ? 'border-bordo-600 bg-bordo-50/40 ring-2 ring-bordo-600/20'
          : 'border-dark-200 bg-dark-50/50 hover:border-bordo-400 hover:bg-white'
      "
      @click="entrada?.click()"
      @keydown.enter.prevent="entrada?.click()"
      @dragover.prevent="arrastrando = true"
      @dragleave.prevent="arrastrando = false"
      @drop.prevent="alSoltar"
    >
      <div class="flex flex-col items-center justify-center gap-2">
        <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-bordo-50 text-bordo-700">
          <UploadCloud class="h-5 w-5" />
        </span>
        <p class="text-xs text-dark-600">
          <span class="font-semibold text-bordo-700">Hacé click para adjuntar</span> o arrastrá el archivo acá
        </p>
        <p class="text-[11px] text-dark-400">Archivos permitidos: PDF, DOC o DOCX (Máx. 2MB)</p>
      </div>
    </div>

    <div
      v-else
      class="flex items-center justify-between rounded-2xl border border-bordo-200 bg-bordo-50/30 p-3.5"
    >
      <div class="flex min-w-0 items-center gap-3">
        <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-bordo-100 text-bordo-700">
          <FileText class="h-5 w-5" />
        </span>
        <div class="min-w-0">
          <p class="truncate text-xs font-semibold text-dark-800" data-testid="cv-nombre">{{ archivo.name }}</p>
          <p class="text-[11px] text-dark-500">{{ tamanoLegible(archivo.size) }} • Listo para adjuntar</p>
        </div>
      </div>
      <div class="ml-3 flex shrink-0 items-center gap-2">
        <button
          type="button"
          class="cursor-pointer rounded-lg border border-bordo-200 bg-white px-2.5 py-1 text-xs font-medium text-bordo-700 hover:bg-bordo-50"
          @click="entrada?.click()"
        >
          Cambiar
        </button>
        <button
          type="button"
          title="Quitar archivo"
          aria-label="Quitar archivo"
          class="cursor-pointer rounded-lg p-1.5 text-dark-400 hover:bg-white hover:text-red-600"
          @click="quitar"
        >
          <X class="h-4 w-4" />
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-2 flex items-center gap-1.5 text-xs text-red-600" role="alert" data-testid="cv-error">
      <AlertCircle class="h-3.5 w-3.5 shrink-0" />
      {{ error }}
    </p>
  </div>
</template>
