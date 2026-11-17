<script setup lang="ts">
import { Award, Code2, Sparkles, X } from '@lucide/vue'
import { computed, ref } from 'vue'

/**
 * Selector de chips de la edición de una búsqueda (Skills, Habilidades y Skills deseadas): lo elegido, el catálogo
 * como botones que agregan o quitan, y un campo para tipear una nueva. Cada tipo tiene su color, como antes.
 */
const props = defineProps<{
  tipo: 'skills' | 'habilidades' | 'deseadas'
  catalogo: string[]
}>()
const seleccion = defineModel<string[]>({ required: true })

const TEMAS = {
  skills: {
    titulo: 'Skills / Tecnologías requeridas',
    vacio: 'Ninguna tecnología seleccionada. Podés elegir de la lista o tipear una nueva.',
    disponibles: 'Skills disponibles:',
    placeholder: 'Agregar otra tecnología (ej: NestJS, Redis, Kafka)...',
    boton: '+ Agregar Tecnología',
    contenedor: 'sm:col-span-2 space-y-2 mt-2 pt-3 border-t border-dark-100',
    icono: Code2,
    claseIcono: 'w-4 h-4 text-primary-600',
    chip: 'bg-primary-50 text-primary-700 border-primary-200/60',
    quitar: 'hover:text-primary-900',
    activa: 'bg-primary-600 text-white border-primary-600',
    entrada: 'focus:ring-primary-500/20 focus:border-primary-500',
  },
  habilidades: {
    titulo: 'Habilidades / Competencias requeridas',
    vacio: 'Ninguna habilidad o competencia seleccionada. Podés elegir de la lista o tipear una nueva.',
    disponibles: 'Competencias disponibles:',
    placeholder: 'Agregar otra habilidad o competencia (ej: Liderazgo, Comunicación, Negociación)...',
    boton: '+ Agregar Habilidad',
    contenedor: 'sm:col-span-2 space-y-2 pt-3 border-t border-dark-100',
    icono: Award,
    claseIcono: 'w-4 h-4 text-emerald-600',
    chip: 'bg-emerald-50 text-emerald-800 border-emerald-200/60',
    quitar: 'hover:text-emerald-950',
    activa: 'bg-emerald-600 text-white border-emerald-600',
    entrada: 'focus:ring-emerald-500/20 focus:border-emerald-500',
  },
  deseadas: {
    titulo: 'Skills deseadas',
    vacio: 'Ninguna skill deseada seleccionada. Podés elegir de la lista o tipear una nueva.',
    disponibles: 'Skills disponibles:',
    placeholder: 'Agregar otra skill deseada (ej: Terraform, Kubernetes, GraphQL)...',
    boton: '+ Agregar Skill',
    contenedor: 'sm:col-span-2 space-y-2 pt-3 border-t border-dark-100',
    icono: Sparkles,
    claseIcono: 'w-4 h-4 text-amber-600',
    chip: 'bg-amber-50 text-amber-800 border-amber-200/60',
    quitar: 'hover:text-amber-950',
    activa: 'bg-amber-600 text-white border-amber-600',
    entrada: 'focus:ring-amber-500/20 focus:border-amber-500',
  },
} as const
const t = computed(() => TEMAS[props.tipo])

const manual = ref('')

/** Un botón del catálogo agrega la opción o, si ya estaba, la quita. */
function alternar(opcion: string): void {
  const valor = opcion.trim()
  if (!valor) return
  seleccion.value = seleccion.value.includes(valor) ? seleccion.value.filter((s) => s !== valor) : [...seleccion.value, valor]
}
function agregarManual(): void {
  const valor = manual.value.trim()
  if (valor && !seleccion.value.includes(valor)) {
    seleccion.value = [...seleccion.value, valor]
    manual.value = ''
  }
}
const quitar = (indice: number) => (seleccion.value = seleccion.value.filter((_, i) => i !== indice))
</script>

<template>
  <div :class="t.contenedor" :data-testid="`selector-${tipo}`">
    <div class="flex items-center gap-2">
      <component :is="t.icono" :class="t.claseIcono" />
      <label class="block text-xs font-bold text-dark-700">{{ t.titulo }}</label>
    </div>

    <!-- Chips seleccionados -->
    <div class="flex flex-wrap gap-1.5 p-2 bg-dark-50 border border-dark-200 rounded-xl min-h-[44px] items-center">
      <span
        v-for="(valor, indice) in seleccion"
        :key="valor"
        class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border"
        :class="t.chip"
      >
        <span>{{ valor }}</span>
        <button type="button" class="focus:outline-none cursor-pointer" :class="t.quitar" @click="quitar(indice)">
          <X class="w-3 h-3" />
        </button>
      </span>
      <span v-if="!seleccion.length" class="text-xs text-dark-400 italic px-2">{{ t.vacio }}</span>
    </div>

    <!-- Selector rápido alimentado por el catálogo -->
    <div class="flex flex-wrap items-center gap-1.5 pt-1">
      <span class="text-xs font-medium text-dark-400 mr-1">{{ t.disponibles }}</span>
      <button
        v-for="opcion in catalogo"
        :key="opcion"
        type="button"
        class="px-2.5 py-1 text-xs font-medium rounded-lg border transition-colors cursor-pointer"
        :class="seleccion.includes(opcion) ? t.activa : 'bg-white text-dark-700 hover:bg-dark-100 border-dark-200'"
        @click="alternar(opcion)"
      >
        {{ opcion }}
      </button>
    </div>

    <!-- Agregar uno manualmente -->
    <div class="flex items-center gap-2 pt-2">
      <input
        v-model="manual"
        type="text"
        :placeholder="t.placeholder"
        class="flex-1 px-3.5 py-2 rounded-xl border border-dark-200 focus:outline-none focus:ring-2 text-sm"
        :class="t.entrada"
        @keydown.enter.prevent="agregarManual"
      />
      <button
        type="button"
        class="px-4 py-2 bg-dark-100 hover:bg-dark-200 text-dark-800 text-xs font-semibold rounded-xl transition-colors cursor-pointer"
        @click="agregarManual"
      >
        {{ t.boton }}
      </button>
    </div>
  </div>
</template>
