<script setup lang="ts">
import { RotateCcw, Search } from '@lucide/vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import { computed, ref, watch } from 'vue'

import { CLASE_BOTON_LIMPIAR, CLASE_BUSCADOR, PT_SELECT_FILTRO } from '../estilos'
import type { FiltrosListado, OpcionesFiltros } from '../types'

const props = defineProps<{ filtros: FiltrosListado; opciones: OpcionesFiltros | undefined }>()
const emit = defineEmits<{ cambiar: [parcial: Partial<FiltrosListado>]; limpiar: [] }>()

// La búsqueda de texto se aplica con Enter (como la pantalla anterior); el resto, al elegir.
const texto = ref(props.filtros.busqueda)
watch(
  () => props.filtros.busqueda,
  (nuevo) => (texto.value = nuevo),
)

/**
 * La opción inicial de cada combo («Todos los seniorities», etc.) equivale al `<option value="">` de la pantalla
 * anterior: hacia afuera el filtro sigue siendo '' (sin filtrar). Adentro lleva un valor propio porque PrimeVue trata
 * '' como «sin selección» y mostraría el combo vacío en lugar del texto de la opción.
 */
const TODOS = '__todos__'
const conTodos = (todos: string, valores: string[] | undefined) => [
  { valor: TODOS, etiqueta: todos },
  ...(valores ?? []).map((v) => ({ valor: v, etiqueta: v })),
]
const mostrado = (valor: string) => valor || TODOS
const hacia = (valor: string | null | undefined) => (!valor || valor === TODOS ? '' : valor)

const seniority = computed(() => conTodos('Todos los seniorities', props.opciones?.niveles))
const ubicaciones = computed(() => [
  ...conTodos('Todas las ubicaciones', props.opciones?.provincias),
  { valor: 'otros', etiqueta: 'Otros' },
])
const perfiles = computed(() => conTodos('Todos los perfiles de puesto', props.opciones?.perfiles))
const categorias = computed(() => conTodos('Todas las categorías', props.opciones?.categorias))
const skills = computed(() =>
  conTodos('Todas las skills de la categoría', props.opciones?.skillsPorCategoria[props.filtros.categoria]),
)

const aplicarBusqueda = () => emit('cambiar', { busqueda: texto.value.trim() })
</script>

<template>
  <!-- Barra de filtros: los controles se distribuyen en las filas que haga falta según el ancho disponible -->
  <div class="mb-6 rounded-2xl border border-dark-100 bg-white p-4 shadow-soft">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-3">
      <div class="relative min-w-[14rem] flex-[2_1_18rem]">
        <Search class="absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-dark-400" />
        <InputText
          v-model="texto"
          placeholder="Buscar (Enter para filtrar)"
          aria-label="Buscar candidatos"
          data-testid="filtro-busqueda"
          :class="CLASE_BUSCADOR"
          @keydown.enter.prevent="aplicarBusqueda"
        />
      </div>
      <div class="min-w-[12rem] flex-[1_1_13rem]">
        <Select
          :model-value="mostrado(filtros.seniority)"
          :options="seniority"
          option-label="etiqueta"
          option-value="valor"
          :pt="PT_SELECT_FILTRO"
          aria-label="Filtrar por seniority"
          data-testid="filtro-seniority"
          @update:model-value="emit('cambiar', { seniority: hacia($event) })"
        />
      </div>
      <div class="min-w-[12rem] flex-[1_1_13rem]">
        <Select
          :model-value="mostrado(filtros.ubicacion)"
          :options="ubicaciones"
          option-label="etiqueta"
          option-value="valor"
          :pt="PT_SELECT_FILTRO"
          aria-label="Filtrar por ubicación"
          data-testid="filtro-ubicacion"
          @update:model-value="emit('cambiar', { ubicacion: hacia($event) })"
        />
      </div>
      <div class="min-w-[14rem] flex-[1_1_16rem]">
        <Select
          :model-value="mostrado(filtros.puesto)"
          :options="perfiles"
          option-label="etiqueta"
          option-value="valor"
          :pt="PT_SELECT_FILTRO"
          title="Perfil de puesto"
          aria-label="Perfil de puesto"
          data-testid="filtro-puesto"
          @update:model-value="emit('cambiar', { puesto: hacia($event) })"
        />
      </div>
      <!-- Categorías de skills: candidatos con al menos una skill de la categoría elegida -->
      <div class="max-w-sm min-w-[14rem] flex-[1_1_16rem]">
        <Select
          :model-value="mostrado(filtros.categoria)"
          :options="categorias"
          option-label="etiqueta"
          option-value="valor"
          :pt="PT_SELECT_FILTRO"
          title="Categoría de skills"
          aria-label="Categoría de skills"
          data-testid="filtro-categoria"
          @update:model-value="emit('cambiar', { categoria: hacia($event), skill: '' })"
        />
      </div>
      <!-- Skills de la categoría elegida (opcional): sin selección se filtra solo por categoría -->
      <div class="max-w-sm min-w-[14rem] flex-[1_1_16rem]">
        <Select
          :model-value="mostrado(filtros.skill)"
          :options="skills"
          option-label="etiqueta"
          option-value="valor"
          :disabled="!filtros.categoria"
          :pt="PT_SELECT_FILTRO"
          title="Skills de la categoría"
          aria-label="Skills de la categoría"
          data-testid="filtro-skill"
          @update:model-value="emit('cambiar', { skill: hacia($event) })"
        />
      </div>
      <div class="flex shrink-0 items-center lg:ml-auto">
        <Button
          type="button"
          unstyled
          :class="CLASE_BOTON_LIMPIAR"
          title="Restablecer todos los filtros"
          data-testid="limpiar-filtros"
          @click="emit('limpiar')"
        >
          <RotateCcw class="h-3.5 w-3.5 text-dark-500" />
          <span>Limpiar Filtros</span>
        </Button>
      </div>
    </div>
  </div>
</template>
