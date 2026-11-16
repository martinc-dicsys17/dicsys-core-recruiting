<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref } from 'vue'

/**
 * Selector de Skills y de Habilidades de la edición (mismo markup y colores que la ficha anterior): chips elegidos,
 * opciones del catálogo que se alternan con un clic y un campo para agregar una nueva (sin repetir, sin distinguir
 * mayúsculas).
 */
const props = defineProps<{
  titulo: string
  opciones: string[]
  etiquetaDisponibles: string
  textoVacio: string
  placeholderNueva: string
  tono: 'primario' | 'esmeralda'
  idCampo: string
}>()

const elegidas = defineModel<string[]>({ required: true })
const nueva = ref('')

const CLASES = {
  primario: {
    chip: 'bg-primary-50 text-primary-700 border border-primary-200/60',
    quitar: 'hover:text-primary-900',
    activa: 'bg-primary-600 text-white border-primary-600',
  },
  esmeralda: {
    chip: 'bg-emerald-50 text-emerald-700 border border-emerald-200/60',
    quitar: 'hover:text-emerald-900',
    activa: 'bg-emerald-600 text-white border-emerald-600',
  },
} as const
const clases = computed(() => CLASES[props.tono])

const igual = (a: string, b: string): boolean => a.toLowerCase() === b.toLowerCase()
const estaElegida = (opcion: string): boolean => elegidas.value.some((e) => igual(e, opcion))

function alternar(opcion: string): void {
  elegidas.value = estaElegida(opcion) ? elegidas.value.filter((e) => !igual(e, opcion)) : [...elegidas.value, opcion]
}

function quitar(indice: number): void {
  elegidas.value = elegidas.value.filter((_, i) => i !== indice)
}

function agregarNueva(): void {
  const valor = nueva.value.trim()
  if (!valor) return
  if (!estaElegida(valor)) elegidas.value = [...elegidas.value, valor]
  nueva.value = ''
}
</script>

<template>
  <div class="space-y-2">
    <label class="mb-1 block text-xs font-semibold text-dark-600">{{ titulo }}</label>

    <div
      class="flex min-h-[44px] flex-wrap items-center gap-1.5 rounded-xl border border-dark-200 bg-dark-50 p-2"
      :data-testid="`${idCampo}-elegidas`"
    >
      <span
        v-for="(e, i) in elegidas"
        :key="e"
        class="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium"
        :class="clases.chip"
      >
        <span>{{ e }}</span>
        <button type="button" class="focus:outline-none" :class="clases.quitar" :aria-label="`Quitar ${e}`" @click="quitar(i)">
          <X class="h-3 w-3" />
        </button>
      </span>
      <span v-if="!elegidas.length" class="px-2 text-xs italic text-dark-400">{{ textoVacio }}</span>
    </div>

    <div class="space-y-2 pt-1">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="mr-1 text-xs font-medium text-dark-400">{{ etiquetaDisponibles }}</span>
        <button
          v-for="o in opciones"
          :key="o"
          type="button"
          class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors"
          :class="estaElegida(o) ? clases.activa : 'border-dark-200 bg-white text-dark-700 hover:bg-dark-100'"
          @click="alternar(o)"
        >
          {{ o }}
        </button>
      </div>

      <div class="flex items-center gap-2 pt-1">
        <input
          v-model="nueva"
          type="text"
          :data-testid="`${idCampo}-nueva`"
          :placeholder="placeholderNueva"
          class="flex-1 rounded-xl border border-dark-200 px-3.5 py-2 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
          @keydown.enter.prevent="agregarNueva"
        />
        <button
          type="button"
          class="cursor-pointer rounded-xl bg-dark-100 px-4 py-2 text-xs font-semibold text-dark-800 transition-colors hover:bg-dark-200"
          @click="agregarNueva"
        >
          + Agregar
        </button>
      </div>
    </div>
  </div>
</template>
