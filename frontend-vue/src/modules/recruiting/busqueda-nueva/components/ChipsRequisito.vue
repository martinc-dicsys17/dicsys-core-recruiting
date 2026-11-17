<script setup lang="ts">
import { X } from '@lucide/vue'
import { computed, ref, type Component } from 'vue'

/**
 * Bloque de etiquetas de «Requisitos del Perfil» (skills, habilidades o skills deseadas): chips elegidos, catálogo para
 * alternar y campo para agregar una nueva. Mismo aspecto que oportunidad_form.html (cada bloque con su color).
 */
const props = defineProps<{
  titulo: string
  icono: Component
  opciones: string[]
  etiquetaDisponibles: string
  textoVacio: string
  placeholderNueva: string
  textoBoton: string
  tono: 'primario' | 'esmeralda' | 'ambar'
  idCampo: string
  separado?: boolean
}>()

const elegidas = defineModel<string[]>({ required: true })
const nueva = ref('')

const CLASES = {
  primario: {
    icono: 'text-primary-600',
    chip: 'bg-primary-50 text-primary-700 border-primary-200/60',
    quitar: 'hover:text-primary-900',
    activa: 'bg-primary-600 text-white border-primary-600',
    foco: 'focus:ring-primary-500/20 focus:border-primary-500',
  },
  esmeralda: {
    icono: 'text-emerald-600',
    chip: 'bg-emerald-50 text-emerald-800 border-emerald-200/60',
    quitar: 'hover:text-emerald-950',
    activa: 'bg-emerald-600 text-white border-emerald-600',
    foco: 'focus:ring-emerald-500/20 focus:border-emerald-500',
  },
  ambar: {
    icono: 'text-amber-600',
    chip: 'bg-amber-50 text-amber-800 border-amber-200/60',
    quitar: 'hover:text-amber-950',
    activa: 'bg-amber-600 text-white border-amber-600',
    foco: 'focus:ring-amber-500/20 focus:border-amber-500',
  },
} as const
const clases = computed(() => CLASES[props.tono])

function alternar(opcion: string): void {
  elegidas.value = elegidas.value.includes(opcion)
    ? elegidas.value.filter((e) => e !== opcion)
    : [...elegidas.value, opcion]
}
function quitar(indice: number): void {
  elegidas.value = elegidas.value.filter((_, i) => i !== indice)
}
function agregarNueva(): void {
  const valor = nueva.value.trim()
  if (valor && !elegidas.value.includes(valor)) {
    elegidas.value = [...elegidas.value, valor]
    nueva.value = ''
  }
}
</script>

<template>
  <div class="col-span-2 space-y-2" :class="separado ? 'border-t border-dark-100 pt-3' : ''">
    <div class="flex items-center gap-2">
      <component :is="icono" class="h-4 w-4" :class="clases.icono" />
      <label :for="idCampo" class="block text-xs font-bold text-dark-700">{{ titulo }}</label>
    </div>

    <div
      class="flex min-h-[44px] flex-wrap items-center gap-1.5 rounded-xl border border-dark-200 bg-dark-50 p-2"
      :data-testid="`${idCampo}-elegidas`"
    >
      <span
        v-for="(e, i) in elegidas"
        :key="e"
        class="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium"
        :class="clases.chip"
      >
        <span>{{ e }}</span>
        <button
          type="button"
          class="cursor-pointer focus:outline-none"
          :class="clases.quitar"
          :aria-label="`Quitar ${e}`"
          @click="quitar(i)"
        >
          <X class="h-3 w-3" />
        </button>
      </span>
      <span v-if="elegidas.length === 0" class="px-2 text-xs italic text-dark-400">{{ textoVacio }}</span>
    </div>

    <div class="flex flex-wrap items-center gap-1.5 pt-1" :data-testid="`${idCampo}-catalogo`">
      <span class="mr-1 text-xs font-medium text-dark-400">{{ etiquetaDisponibles }}</span>
      <button
        v-for="o in opciones"
        :key="o"
        type="button"
        class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors"
        :class="elegidas.includes(o) ? clases.activa : 'border-dark-200 bg-white text-dark-700 hover:bg-dark-100'"
        @click="alternar(o)"
      >
        {{ o }}
      </button>
    </div>

    <div class="flex items-center gap-2 pt-2">
      <input
        :id="idCampo"
        v-model="nueva"
        type="text"
        :placeholder="placeholderNueva"
        class="flex-1 rounded-xl border border-dark-200 px-3.5 py-2 text-sm focus:ring-2 focus:outline-none"
        :class="clases.foco"
        @keydown.enter.prevent="agregarNueva"
      />
      <button
        type="button"
        class="cursor-pointer rounded-xl bg-dark-100 px-4 py-2 text-xs font-semibold text-dark-800 transition-colors hover:bg-dark-200"
        @click="agregarNueva"
      >
        {{ textoBoton }}
      </button>
    </div>
  </div>
</template>
