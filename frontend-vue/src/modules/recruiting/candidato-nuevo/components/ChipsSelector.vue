<script setup lang="ts">
import { Plus, X } from '@lucide/vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import { computed, ref } from 'vue'

/**
 * Selector de etiquetas: las elegidas se ven como chips, las del catálogo se alternan con un clic y se
 * puede agregar una nueva escribiéndola. Sirve para Skills y para Habilidades.
 */
const props = defineProps<{
  titulo: string
  /** Opciones del catálogo. */
  opciones: string[]
  etiquetaDisponibles: string
  textoVacio: string
  placeholderNueva: string
  tono: 'bordo' | 'esmeralda'
  idCampo: string
}>()

const elegidas = defineModel<string[]>({ required: true })
const nueva = ref('')

const CLASES = {
  bordo: {
    chip: 'bg-bordo-50 text-bordo-700 border-bordo-200/60',
    activa: 'bg-bordo-700 text-white border-bordo-700',
  },
  esmeralda: {
    chip: 'bg-emerald-50 text-emerald-700 border-emerald-200/60',
    activa: 'bg-emerald-600 text-white border-emerald-600',
  },
} as const
const clases = computed(() => CLASES[props.tono])

function alternar(opcion: string): void {
  elegidas.value = elegidas.value.includes(opcion)
    ? elegidas.value.filter((e) => e !== opcion)
    : [...elegidas.value, opcion]
}

function quitar(opcion: string): void {
  elegidas.value = elegidas.value.filter((e) => e !== opcion)
}

function agregarNueva(): void {
  const valor = nueva.value.trim()
  // Como la pantalla anterior: solo se vacía el campo cuando se agrega; con un valor vacío o repetido queda como está.
  if (valor && !elegidas.value.includes(valor)) {
    elegidas.value = [...elegidas.value, valor]
    nueva.value = ''
  }
}
</script>

<template>
  <div class="space-y-2">
    <label :for="idCampo" class="block text-xs font-semibold text-dark-600">{{ titulo }}</label>

    <div
      class="flex min-h-11 flex-wrap items-center gap-1.5 rounded-xl border border-dark-200 bg-dark-50 p-2"
      :data-testid="`${idCampo}-elegidas`"
    >
      <span
        v-for="e in elegidas"
        :key="e"
        class="inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium"
        :class="clases.chip"
      >
        {{ e }}
        <button type="button" class="cursor-pointer focus:outline-none" :aria-label="`Quitar ${e}`" @click="quitar(e)">
          <X class="h-3 w-3" />
        </button>
      </span>
      <span v-if="elegidas.length === 0" class="px-2 text-xs italic text-dark-400">{{ textoVacio }}</span>
    </div>

    <div v-if="opciones.length" class="flex flex-wrap items-center gap-1.5 pt-1">
      <span class="mr-1 text-xs font-medium text-dark-400">{{ etiquetaDisponibles }}</span>
      <button
        v-for="o in opciones"
        :key="o"
        type="button"
        class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors"
        :class="elegidas.includes(o) ? clases.activa : 'border-dark-200 bg-white text-dark-700 hover:bg-dark-100'"
        :aria-pressed="elegidas.includes(o)"
        @click="alternar(o)"
      >
        {{ o }}
      </button>
    </div>

    <div class="flex items-center gap-2 pt-2">
      <InputText
        :id="idCampo"
        v-model="nueva"
        fluid
        size="small"
        :placeholder="placeholderNueva"
        @keydown.enter.prevent="agregarNueva"
      />
      <Button type="button" severity="secondary" size="small" label="Agregar" @click="agregarNueva">
        <template #icon><Plus class="mr-1 h-3.5 w-3.5" /></template>
      </Button>
    </div>
  </div>
</template>
