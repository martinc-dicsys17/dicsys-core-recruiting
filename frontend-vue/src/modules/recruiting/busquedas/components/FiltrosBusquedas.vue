<script setup lang="ts">
import { RotateCcw, Search } from '@lucide/vue'
import InputText from 'primevue/inputtext'

import { CLASE_BOTON_LIMPIAR, CLASE_BUSCADOR } from '../../candidatos/estilos'
import { ESTADOS } from '../filtros'
import type { FiltrosBusquedas, TipoBusqueda } from '../types'

defineProps<{ filtros: FiltrosBusquedas; puedeVerTipo: boolean }>()
const emit = defineEmits<{ cambiar: [parcial: Partial<FiltrosBusquedas>]; buscar: []; limpiar: [] }>()

// El texto lo guarda la página (v-model): se aplica con Enter y viaja con cualquier otro cambio de filtro.
const texto = defineModel<string>('texto', { required: true })

const TIPOS: { valor: TipoBusqueda; etiqueta: string }[] = [
  { valor: 'Efectiva', etiqueta: 'Efectivas' },
  { valor: 'Potencial', etiqueta: 'Potenciales' },
  { valor: 'Todas', etiqueta: 'Todas' },
]
const ESTADOS_OPCIONES = [
  { valor: 'todos', etiqueta: 'Todos los estados' },
  ...ESTADOS.map((e) => ({ valor: e, etiqueta: e })),
]
// Combos nativos, como el <select> de la pantalla anterior.
const CLASE_COMBO =
  'w-full cursor-pointer rounded-xl border border-dark-200 bg-dark-50 px-3 py-2 text-sm text-dark-700 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20'
const ETIQUETA = 'mb-1 block text-xs font-semibold text-dark-500'
</script>

<template>
  <!-- Barra de filtros superior: filtra el servidor, así la paginación cuenta todas las búsquedas -->
  <div class="mb-6 rounded-2xl border border-dark-100 bg-white p-4 shadow-soft">
    <div class="flex items-center justify-between gap-3">
      <div class="flex flex-1 items-center gap-3">
        <div class="relative w-72">
          <label for="filtro-busqueda" :class="ETIQUETA">Búsqueda rápida</label>
          <div class="relative">
            <Search class="absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-dark-400" />
            <InputText
              id="filtro-busqueda"
              v-model="texto"
              placeholder="Buscar por título, cliente..."
              data-testid="filtro-busqueda"
              :class="[CLASE_BUSCADOR, 'text-black placeholder:text-[#9ca3af]']"
              @keydown.enter.prevent="emit('buscar')"
            />
          </div>
        </div>

        <div v-if="puedeVerTipo" class="w-52">
          <label for="filtro-tipo" :class="ETIQUETA">Tipo de Búsqueda</label>
          <select
            id="filtro-tipo"
            :value="filtros.tipo"
            :class="[CLASE_COMBO, 'font-medium']"
            data-testid="filtro-tipo"
            @change="emit('cambiar', { tipo: ($event.target as HTMLSelectElement).value as TipoBusqueda })"
          >
            <option v-for="t in TIPOS" :key="t.valor" :value="t.valor">{{ t.etiqueta }}</option>
          </select>
        </div>

        <div class="w-48">
          <label for="filtro-estado" :class="ETIQUETA">Estado</label>
          <select
            id="filtro-estado"
            :value="filtros.estado"
            :class="CLASE_COMBO"
            data-testid="filtro-estado"
            @change="emit('cambiar', { estado: ($event.target as HTMLSelectElement).value })"
          >
            <option v-for="e in ESTADOS_OPCIONES" :key="e.valor" :value="e.valor">{{ e.etiqueta }}</option>
          </select>
        </div>
      </div>

      <div class="mt-5 flex items-end self-auto">
        <button type="button" :class="CLASE_BOTON_LIMPIAR" title="Restablecer todos los filtros" data-testid="limpiar-filtros" @click="emit('limpiar')">
          <RotateCcw class="h-3.5 w-3.5 text-dark-500" />
          <span>Limpiar Filtros</span>
        </button>
      </div>
    </div>
  </div>
</template>
