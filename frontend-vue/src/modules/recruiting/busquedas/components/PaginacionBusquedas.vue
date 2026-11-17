<script setup lang="ts">
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import Button from 'primevue/button'
import { computed } from 'vue'

import { CLASE_BOTON_PAGINA } from '../../candidatos/estilos'
import { LIMITES, rangoRegistros } from '../filtros'

const props = defineProps<{ pagina: number; limite: number; total: number; totalPaginas: number; cargando?: boolean }>()
const emit = defineEmits<{ pagina: [numero: number]; limite: [valor: number] }>()

const rango = computed(() => rangoRegistros(props.pagina, props.limite, props.total))
const ultima = computed(() => Math.max(1, props.totalPaginas))
const NEGRITA = 'font-bold text-dark-900 dark:text-slate-100'
</script>

<template>
  <!-- Barra de paginación -->
  <div
    class="flex items-center justify-between gap-4 border-t border-dark-100 bg-dark-50/40 px-5 py-3.5 text-xs text-dark-600 dark:border-slate-800 dark:bg-slate-900/90 dark:text-slate-300"
  >
    <div class="flex items-center gap-2">
      <span class="font-medium text-dark-500 dark:text-slate-300">Mostrar por página:</span>
      <select
        :value="limite"
        aria-label="Registros por página"
        data-testid="selector-limite"
        class="cursor-pointer rounded-lg border border-dark-200 bg-white px-2.5 py-1 text-xs font-semibold text-dark-800 shadow-2xs outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        @change="emit('limite', Number(($event.target as HTMLSelectElement).value))"
      >
        <option v-for="l in LIMITES" :key="l" :value="l">{{ l }}</option>
      </select>
      <span class="text-dark-400 dark:text-slate-400">registros</span>
    </div>

    <div class="text-center font-medium text-dark-600 dark:text-slate-300" data-testid="indicador-registros">
      <span v-if="total > 0">
        Mostrando <strong :class="NEGRITA">{{ rango.desde }}</strong> a
        <strong :class="NEGRITA">{{ rango.hasta }}</strong> de <strong :class="NEGRITA">{{ total }}</strong>
        búsquedas
      </span>
      <span v-else-if="!cargando">Sin búsquedas para mostrar</span>
    </div>

    <div class="flex items-center gap-2">
      <Button
        type="button"
        unstyled
        :class="CLASE_BOTON_PAGINA"
        title="Página anterior"
        :disabled="pagina <= 1"
        data-testid="pagina-anterior"
        @click="emit('pagina', pagina - 1)"
      >
        <ChevronLeft class="h-3.5 w-3.5" /><span>Anterior</span>
      </Button>
      <span class="px-2 font-semibold text-dark-700 dark:text-slate-300" data-testid="indicador-pagina">
        Página {{ pagina }} de {{ ultima }}
      </span>
      <Button
        type="button"
        unstyled
        :class="CLASE_BOTON_PAGINA"
        title="Página siguiente"
        :disabled="pagina >= ultima"
        data-testid="pagina-siguiente"
        @click="emit('pagina', pagina + 1)"
      >
        <span>Siguiente</span><ChevronRight class="h-3.5 w-3.5" />
      </Button>
    </div>
  </div>
</template>
