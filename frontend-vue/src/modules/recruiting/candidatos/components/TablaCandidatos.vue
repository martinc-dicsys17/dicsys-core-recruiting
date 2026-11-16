<script setup lang="ts">
import { Compass, Eye, FileSearch, FileText, Inbox, Trash2, UserPlus } from '@lucide/vue'
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import Tooltip from 'primevue/tooltip'

import { urlCv } from '../api/candidatos.repository'
import { CLASE_ENCABEZADO } from '../estilos'
import { dividirSkills, estadoParaMostrar } from '../filtros'
import type { CandidatoListado, PermisosCandidatos } from '../types'

defineProps<{
  candidatos: CandidatoListado[]
  cargando: boolean
  permisos: PermisosCandidatos
  /** Texto del estado vacío: quien puede cargar CV desde el listado ve la «Carga Masiva». */
  puedeCargarCv: boolean
  /** Enlace de la ficha, con `volver` para regresar a esta grilla con sus filtros. */
  enlaceFicha: (id: string) => string
  eliminandoId: string | null
}>()
const emit = defineEmits<{
  asignar: [candidato: CandidatoListado]
  detalles: [candidato: CandidatoListado]
  eliminar: [candidato: CandidatoListado]
}>()

const vTooltip = Tooltip
// La tabla se ve como la anterior: w-full, mínimo 850 px, filas text-xs con separadores y fondo al pasar el cursor.
const PT_TABLA = {
  tableContainer: { class: 'overflow-x-auto' },
  table: { class: 'w-full min-w-[850px] border-collapse text-left lg:min-w-full' },
  bodyRow: { class: 'text-xs transition-colors hover:bg-dark-50/50' },
}
// Skills ocultas («+N»): panel oscuro con una etiqueta por skill, como la pantalla anterior.
const escapar = (t: string) => t.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const tooltipSkills = (skills: string[]) => ({
  value: `<div class="flex flex-wrap gap-1">${skills
    .map((k) => `<span class="rounded-md border border-white/15 bg-white/10 px-1.5 py-0.5 text-[10px] font-medium">${escapar(k)}</span>`)
    .join('')}</div>`,
  escape: false,
  pt: { arrow: { class: 'hidden' }, root: { class: 'max-w-[260px]' }, text: { class: 'rounded-lg bg-dark-900 px-2.5 py-2 text-white shadow-xl' } },
})
const CELDA_PRIMERA = 'px-4 py-3 border-b border-dark-100 text-xs leading-4'
const CELDA = 'px-3 py-3 border-b border-dark-100 text-xs leading-4'
const nombreCompleto = (c: CandidatoListado) => `${c.nombre} ${c.apellido ?? ''}`.trim()
const BOTON =
  'inline-flex cursor-pointer items-center justify-center rounded-lg border p-1 text-xs font-medium transition-colors'
</script>

<template>
  <DataTable
    :value="candidatos"
    :loading="cargando"
    data-key="id"
    :pt="PT_TABLA"
  >
    <Column header="Candidato" :header-class="CLASE_ENCABEZADO" :body-class="CELDA_PRIMERA">
      <template #body="{ data }: { data: CandidatoListado }">
        <a
          :href="enlaceFicha(data.id)"
          class="block text-[13px] font-bold text-dark-900 transition-colors hover:text-primary-600"
        >
          {{ nombreCompleto(data) }}
        </a>
      </template>
    </Column>

    <Column header="Contacto / Email" :header-class="CLASE_ENCABEZADO" :body-class="CELDA">
      <template #body="{ data }: { data: CandidatoListado }">
        <p class="text-xs font-medium text-dark-800">{{ data.email }}</p>
        <p v-if="data.telefono" class="text-[11px] text-gray-500">Tel: {{ data.telefono }}</p>
      </template>
    </Column>

    <Column header="Ubicación" :header-class="CLASE_ENCABEZADO" :body-class="CELDA">
      <template #body="{ data }: { data: CandidatoListado }">
        <span class="text-xs font-medium text-dark-800">{{ data.ubicacion || data.ciudad || data.localidad || '—' }}</span>
      </template>
    </Column>

    <Column header="Skills" :header-class="CLASE_ENCABEZADO" :body-class="CELDA">
      <template #body="{ data }: { data: CandidatoListado }">
        <div class="max-w-[220px]">
          <div v-if="data.skills?.length" class="flex flex-wrap items-center gap-1">
            <span
              v-for="skill in dividirSkills(data.skills).visibles"
              :key="skill"
              class="rounded-md border border-blue-200/50 bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-700"
              title="Tecnología"
            >
              {{ skill }}
            </span>
            <button
              v-if="data.skills.length > 2"
              v-tooltip.top="tooltipSkills(dividirSkills(data.skills).ocultas)"
              type="button"
              data-testid="skills-ocultas"
              :aria-label="`Ver las ${data.skills.length - 2} skills restantes`"
              class="cursor-default rounded px-1 py-0.5 text-[9px] font-semibold text-dark-400 hover:text-primary-600 focus:ring-1 focus:ring-primary-300 focus:outline-none"
            >
              +{{ data.skills.length - 2 }}
            </button>
          </div>
          <span v-else class="text-xs text-dark-400 italic">Sin skills registradas</span>
        </div>
      </template>
    </Column>

    <Column header="Origen / Fuente" :header-class="CLASE_ENCABEZADO" :body-class="CELDA">
      <template #body="{ data }: { data: CandidatoListado }">
        <span
          class="inline-flex items-center gap-1 rounded-lg border border-dark-200/60 bg-dark-100 px-2 py-0.5 text-[11px] font-medium whitespace-nowrap text-dark-700"
        >
          <Compass class="h-3 w-3 text-dark-500" />
          <span>{{ data.fuente || 'Portal Propio' }}</span>
        </span>
      </template>
    </Column>

    <Column header="Estado" :header-class="CLASE_ENCABEZADO" :body-class="CELDA">
      <template #body="{ data }: { data: CandidatoListado }">
        <span
          class="inline-block rounded-lg px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap"
          :class="estadoParaMostrar(data.estado, data.activo).clases"
        >
          {{ estadoParaMostrar(data.estado, data.activo).texto }}
        </span>
      </template>
    </Column>

    <Column header="Acciones" :pt="{ columnHeaderContent: { class: 'justify-end' } }" :header-class="`${CLASE_ENCABEZADO} text-right`" :body-class="`${CELDA_PRIMERA} text-right whitespace-nowrap`">
      <template #body="{ data }: { data: CandidatoListado }">
        <div class="flex items-center justify-end gap-1.5">
          <a
            v-if="data.cv_url"
            :href="urlCv(data.cv_url)"
            target="_blank"
            rel="noopener noreferrer"
            title="Descargar CV"
            class="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-dark-200 bg-white px-2 py-1 text-xs font-medium text-dark-700 transition-colors hover:bg-dark-50"
          >
            <FileText class="h-3.5 w-3.5 text-primary-600" /><span>CV</span>
          </a>
          <button
            v-if="permisos.puede_asignar_candidatos"
            type="button"
            title="Asignar a búsqueda"
            aria-label="Asignar a búsqueda"
            data-testid="accion-asignar"
            :class="`${BOTON} border-emerald-200/60 bg-emerald-50 text-emerald-700 hover:bg-emerald-100`"
            @click="emit('asignar', data)"
          >
            <UserPlus class="h-3.5 w-3.5 text-emerald-600" />
          </button>
          <a
            :href="enlaceFicha(data.id)"
            title="Ver candidato"
            aria-label="Ver candidato"
            data-testid="accion-ver"
            class="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg bg-primary-50 text-primary-600 transition-colors hover:bg-primary-100"
          >
            <Eye class="h-3.5 w-3.5" /><span class="sr-only">Ver candidato</span>
          </a>
          <button
            v-if="data.tiene_pipeline"
            type="button"
            title="Ver Detalles"
            aria-label="Ver detalles"
            data-testid="accion-detalles"
            :class="`${BOTON} border-dark-200/60 bg-dark-50 text-dark-600 hover:bg-dark-100`"
            @click="emit('detalles', data)"
          >
            <FileSearch class="h-3.5 w-3.5" />
          </button>
          <button
            v-if="permisos.puede_eliminar_candidatos"
            type="button"
            title="Eliminar candidato"
            aria-label="Eliminar candidato"
            data-testid="accion-eliminar"
            :disabled="eliminandoId === data.id"
            :class="`${BOTON} border-red-200/60 bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50`"
            @click="emit('eliminar', data)"
          >
            <Trash2 class="h-3.5 w-3.5" />
          </button>
        </div>
      </template>
    </Column>

    <template #empty>
      <div v-if="!cargando" class="px-6 py-16 text-center text-dark-400" data-testid="sin-candidatos">
        <Inbox class="mx-auto mb-3 h-10 w-10 text-dark-300" />
        <p class="text-base font-semibold text-dark-700">No se encontraron candidatos en la base de talentos</p>
        <p v-if="puedeCargarCv" class="mx-auto mt-1 max-w-sm text-xs">
          Comenzá sumando perfiles mediante "+ Nuevo Candidato" o utilizá la "Carga Masiva CVs".
        </p>
        <p v-else class="mx-auto mt-1 max-w-sm text-xs">
          Sumá perfiles mediante "+ Nuevo Candidato" o cargá CVs desde el detalle de una búsqueda que tengas asignada.
        </p>
      </div>
    </template>
  </DataTable>
</template>
