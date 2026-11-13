<script setup lang="ts">
import { ChevronRight, Mail, Phone, SearchX } from '@lucide/vue'
import Button from 'primevue/button'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import { computed, ref, watch } from 'vue'

import { ESTILO_MOTIVO, fondoAvatar, formatearFecha, iniciales } from '../presentacion'
import type { PersonaBlacklist } from '../types'

const props = defineProps<{ personas: PersonaBlacklist[]; cargando: boolean; hayFiltros: boolean }>()
defineEmits<{ limpiarFiltros: [] }>()

/** Persona cuya fila esta seleccionada (se abre su detalle). */
const seleccionada = defineModel<PersonaBlacklist | null>('seleccionada', { required: true })
/** Indice de la primera fila visible; el padre lo reinicia al cambiar los filtros. */
const primera = defineModel<number>('primera', { required: true })

const filasPorPagina = ref(10)
const OPCIONES_FILAS = [10, 20, 30, 40, 50]
// Al cambiar la cantidad de filas se vuelve a la primera pagina.
watch(filasPorPagina, () => (primera.value = 0))
const ultima = computed(() => Math.min(primera.value + filasPorPagina.value, props.personas.length))

const ENCABEZADO = 'text-[11px] uppercase tracking-[0.08em] font-bold text-dark-500'
</script>

<template>
  <!-- Grilla: al seleccionar una fila (clic o Enter) se abre el detalle de la persona. -->
  <DataTable
    v-model:selection="seleccionada"
    v-model:first="primera"
    v-model:rows="filasPorPagina"
    class="grilla-blacklist bg-white"
    :value="personas"
    :loading="cargando"
    data-key="id"
    selection-mode="single"
    row-hover
    :row-class="() => 'group bg-white'"
    paginator
    paginator-template="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink"
    sort-field="fechaAlta"
    :sort-order="-1"
    removable-sort
    table-style="min-width: 54rem"
  >
    <Column field="apellido" header="Persona" sortable :header-class="ENCABEZADO" style="width: 28%">
      <template #body="{ data }: { data: PersonaBlacklist }">
        <div class="flex items-center gap-3.5">
          <span
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br text-[13px] font-bold tracking-wide text-white shadow-xs ring-1 ring-dark-900/10 transition-transform duration-200 group-hover:scale-105"
            :class="fondoAvatar(data)"
          >
            {{ iniciales(data) }}
          </span>
          <div class="min-w-0">
            <p class="truncate text-[15px] leading-tight font-semibold text-dark-900">
              {{ data.apellido }}, {{ data.nombre }}
            </p>
            <p class="mt-1 font-mono text-xs text-dark-400">DNI {{ data.documento || 'sin dato' }}</p>
          </div>
        </div>
      </template>
    </Column>

    <Column header="Contacto" :header-class="ENCABEZADO" style="width: 25%">
      <template #body="{ data }: { data: PersonaBlacklist }">
        <div class="space-y-1.5 text-[13px] text-dark-600">
          <p v-if="data.email" class="flex items-center gap-2">
            <Mail class="h-3.5 w-3.5 shrink-0 text-dark-400" /><span class="truncate text-dark-700">{{ data.email }}</span>
          </p>
          <p v-if="data.telefono" class="flex items-center gap-2 whitespace-nowrap text-dark-600">
            <Phone class="h-3.5 w-3.5 shrink-0 text-dark-400" />{{ data.telefono }}
          </p>
        </div>
      </template>
    </Column>

    <Column field="motivo" header="Motivo" sortable :header-class="ENCABEZADO" style="width: 28%">
      <template #body="{ data }: { data: PersonaBlacklist }">
        <Tag rounded class="ring-1 ring-inset" :class="ESTILO_MOTIVO.etiqueta">
          <span class="h-1.5 w-1.5 rounded-full" :class="ESTILO_MOTIVO.punto"></span>
          <span>{{ data.motivo }}</span>
        </Tag>
        <p v-if="data.observacion" class="mt-2 line-clamp-1 text-xs text-dark-500" :title="data.observacion">
          {{ data.observacion }}
        </p>
      </template>
    </Column>

    <Column field="fechaAlta" header="Registro" sortable :header-class="ENCABEZADO" style="width: 15%">
      <template #body="{ data }: { data: PersonaBlacklist }">
        <div class="whitespace-nowrap">
          <p class="text-[13px] font-semibold text-dark-800">{{ formatearFecha(data.fechaAlta) }}</p>
          <p class="mt-1 text-xs text-dark-400">por {{ data.registradoPor }}</p>
        </div>
      </template>
    </Column>

    <!-- Indicador de que la fila abre el detalle -->
    <Column style="width: 4%" body-class="text-right">
      <template #body>
        <ChevronRight
          class="ml-auto h-4 w-4 -translate-x-1 text-bordo-600 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100"
        />
      </template>
    </Column>

    <template #paginatorstart>
      <p v-if="personas.length" class="text-[13px] text-dark-500">
        Mostrando
        <strong class="font-semibold text-dark-800">{{ primera + 1 }}–{{ ultima }}</strong>
        de <strong class="font-semibold text-dark-800">{{ personas.length }}</strong> personas
      </p>
    </template>

    <template #paginatorend>
      <div class="flex items-center gap-2 text-[13px] text-dark-500">
        <span class="hidden sm:inline">Filas por página</span>
        <Select v-model="filasPorPagina" :options="OPCIONES_FILAS" size="small" class="bg-white!" aria-label="Filas por página" />
      </div>
    </template>

    <template #empty>
      <div class="mx-auto flex max-w-sm flex-col items-center py-12 text-center">
        <div
          class="mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-bordo-50 text-bordo-700 ring-1 ring-bordo-200"
        >
          <SearchX class="h-7 w-7" />
        </div>
        <template v-if="hayFiltros">
          <h2 class="mb-1 text-base font-semibold text-dark-900">Ninguna persona coincide con los filtros</h2>
          <p class="mb-5 text-[13px] text-dark-500">Probá con otro término de búsqueda o quitá los filtros aplicados.</p>
          <Button label="Limpiar filtros" severity="secondary" outlined size="small" @click="$emit('limpiarFiltros')" />
        </template>
        <template v-else>
          <h2 class="mb-1 text-base font-semibold text-dark-900">La Blacklist está vacía</h2>
          <p class="text-[13px] text-dark-500">No hay personas marcadas como no entrevistables.</p>
        </template>
      </div>
    </template>
  </DataTable>
</template>

<style>
/* Detalles de la grilla que el tema no cubre con tokens: linea de acento bordo en la fila bajo el
   cursor o seleccionada, separaciones sutiles y transicion suave. */
@layer components {
  .grilla-blacklist .p-datatable-tbody > tr {
    cursor: pointer;
    background-color: #ffffff;
    transition:
      background-color 0.18s ease,
      box-shadow 0.18s ease;
  }

  .grilla-blacklist .p-datatable-tbody > tr:hover {
    background-color: #fafafc;
  }

  .grilla-blacklist .p-datatable-tbody > tr.p-datatable-row-selected {
    background-color: #fef2f2;
  }

  .grilla-blacklist .p-datatable-tbody > tr:hover > td:first-child,
  .grilla-blacklist .p-datatable-tbody > tr.p-datatable-row-selected > td:first-child {
    box-shadow: inset 3px 0 0 0 var(--color-bordo-600);
  }

  .grilla-blacklist .p-datatable-tbody > tr > td {
    border-bottom: 1px solid var(--color-dark-100);
  }

  .grilla-blacklist .p-datatable-tbody > tr:last-child > td {
    border-bottom-width: 0;
  }

  .grilla-blacklist .p-datatable-paginator-bottom {
    border-top: 1px solid var(--color-dark-200);
    background-color: #ffffff;
  }
}
</style>
