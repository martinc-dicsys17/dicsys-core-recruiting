<script setup lang="ts">
import { Eye, Inbox, Trash2, UserPlus } from '@lucide/vue'
import { computed } from 'vue'

import { claseEstado, formatearFechaAsignacion, idVisible } from '../presentacion'
import type { Busqueda } from '../types'

const props = defineProps<{
  busquedas: Busqueda[]
  cargando: boolean
  /** Muestra la columna Líder (permiso de líder, tipo y fecha). */
  verLider: boolean
  puedeAdministrarExternos: boolean
  puedeCancelar: boolean
  cancelandoId: string | null
}>()
const emit = defineEmits<{ externo: [busqueda: Busqueda]; cancelar: [busqueda: Busqueda] }>()

const COLUMNAS = computed(() => (props.verLider ? 16 : 15))
const ANCHOS = computed(() => {
  const a = [3, 5.5, 6, 5.5, 5, ...(props.verLider ? [5] : []), 4.5, 6, 7.5, 7, 6.5, 6.5, 6.5, 4, 6, 9.5]
  return a.map((w) => `${w}%`)
})
const TH = 'px-1 py-2.5 break-words'
const CONTADOR =
  'inline-block rounded-md border border-dark-200/60 bg-dark-100/80 px-1.5 py-0.5 font-mono text-[10px] leading-4 font-bold text-dark-700'
const BOTON = 'inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-lg border shadow-2xs transition-colors'
const enlace = (id: string) => `/recruiting/oportunidades/${id}`
const recruiter = (b: Busqueda) => b.recruiter_nombre || '—'
const lider = (b: Busqueda) => b.lider_nombre || '—'
</script>

<template>
  <div class="w-full">
    <table class="w-full table-fixed border-collapse text-left" :class="{ 'opacity-60': cargando }" data-testid="tabla-busquedas">
      <colgroup>
        <col v-for="(ancho, i) in ANCHOS" :key="i" :style="{ width: ancho }" />
      </colgroup>
      <thead>
        <tr
          class="border-b border-slate-200 bg-slate-100 text-[9px] leading-tight font-semibold tracking-tight text-slate-600 uppercase dark:border-slate-700/80 dark:bg-slate-900/90 dark:text-slate-200"
        >
          <th :class="[TH, 'text-center']">ID</th>
          <th :class="TH">Cliente</th>
          <th :class="TH">Búsqueda</th>
          <th :class="[TH, 'text-center']">Estado</th>
          <th :class="TH">Recruiter</th>
          <th v-if="verLider" :class="TH">Líder</th>
          <th :class="[TH, 'text-center']">Días Abierta</th>
          <th :class="[TH, 'text-center']">Candidatos en Pipeline</th>
          <th :class="[TH, 'text-center']">Coordinando entrevista</th>
          <th :class="[TH, 'text-center']">Entrevistados RRHH</th>
          <th :class="[TH, 'text-center']">Presentación al líder</th>
          <th :class="[TH, 'text-center']">Feedback entrevista Líder</th>
          <th :class="[TH, 'text-center']">Presentación al cliente</th>
          <th :class="[TH, 'text-center']">Q Activos</th>
          <th :class="[TH, 'text-center']">Fecha de asignación</th>
          <th :class="[TH, 'text-center']">Acciones</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-dark-100 text-xs">
        <tr v-for="b in busquedas" :key="b.id" class="transition-colors hover:bg-dark-50/60" data-testid="fila-busqueda">
          <td class="px-1 py-2 text-center">
            <span class="rounded-md bg-dark-100/70 px-1 py-0.5 font-mono text-[10px] leading-4 font-semibold text-dark-600">{{ idVisible(b) }}</span>
          </td>
          <td class="truncate px-1 py-2 font-semibold text-dark-900" :title="b.cliente">{{ b.cliente }}</td>
          <td class="px-1 py-2">
            <a
              :href="enlace(b.id)"
              class="block truncate text-xs leading-snug font-medium text-dark-900 transition-colors hover:text-primary-600"
              :title="b.titulo"
              data-testid="enlace-busqueda"
              >{{ b.titulo }}</a
            >
          </td>
          <td class="px-1 py-2 text-center">
            <span
              class="inline-block max-w-full truncate rounded-lg border px-1.5 py-0.5 align-middle text-[10px] leading-4 font-semibold"
              :class="claseEstado(b.estado)"
              :title="b.estado"
              data-testid="estado-busqueda"
              >{{ b.estado }}</span
            >
          </td>
          <td class="truncate px-1 py-2 text-dark-600" :title="recruiter(b)">{{ recruiter(b) }}</td>
          <td v-if="verLider" class="truncate px-1 py-2 text-dark-600" :title="lider(b)">{{ lider(b) }}</td>
          <td class="bg-yellow-200 px-1 py-2 text-center whitespace-nowrap">
            <span
              class="inline-block rounded-lg px-1 py-0.5 font-mono text-[10px] leading-4 font-bold"
              :class="(b.dias_abierta || 0) > 30 ? 'border border-red-200 bg-red-50 text-red-700' : 'border border-dark-200/60 bg-dark-100/80 text-dark-700'"
              >{{ b.dias_abierta || 0 }}</span
            >
          </td>
          <td class="px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.candidatos_pipeline ?? 0 }}</span></td>
          <td class="px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.coordinando_entrevista ?? 0 }}</span></td>
          <td class="px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.entrevistados_rrhh ?? 0 }}</span></td>
          <td class="px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.presentacion_lider ?? 0 }}</span></td>
          <td class="bg-yellow-200 px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.feedback_lider ?? 0 }}</span></td>
          <td class="px-1 py-2 text-center whitespace-nowrap"><span :class="CONTADOR">{{ b.presentacion_cliente ?? 0 }}</span></td>
          <td class="px-1 py-2 text-center whitespace-nowrap">
            <span class="inline-block rounded-md border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 font-mono text-[10px] leading-4 font-bold text-emerald-800">{{ b.q_activos ?? 0 }}</span>
          </td>
          <td class="px-1 py-2 text-center font-mono text-[10px] leading-tight text-dark-500">{{ formatearFechaAsignacion(b.fecha_asignacion) }}</td>
          <td class="px-1 py-2 text-center whitespace-nowrap">
            <div class="flex flex-nowrap items-center justify-center gap-1">
              <a
                :href="enlace(b.id)"
                :class="[BOTON, 'shrink-0 border-primary-100 bg-primary-50 text-primary-700 hover:bg-primary-100']"
                title="Ver detalle"
                aria-label="Ver detalle"
                data-testid="ver-detalle"
              >
                <Eye class="h-3.5 w-3.5 text-primary-600" />
              </a>
              <!-- Asignar usuario externo (solo grupo Recruiting; no disponible en una búsqueda Ganada/cerrada) -->
              <button
                v-if="puedeAdministrarExternos && b.estado !== 'Ganada'"
                type="button"
                :class="[BOTON, 'shrink-0 border-indigo-100 bg-indigo-50 text-indigo-600 hover:bg-indigo-100']"
                title="Asignar usuario externo"
                aria-label="Asignar usuario externo"
                data-testid="asignar-externo"
                @click="emit('externo', b)"
              >
                <UserPlus class="h-3.5 w-3.5 text-indigo-600" />
              </button>
              <!-- Cancelar búsqueda (cambia el estado a Cancelada; no elimina nada). Una búsqueda Ganada está cerrada -->
              <button
                v-if="puedeCancelar && b.estado !== 'Cancelada' && b.estado !== 'Ganada'"
                type="button"
                :disabled="cancelandoId === b.id"
                :class="[BOTON, 'shrink-0 border-red-100 bg-red-50 text-red-600 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60']"
                title="Cancelar búsqueda"
                aria-label="Cancelar búsqueda"
                data-testid="cancelar-busqueda"
                @click="emit('cancelar', b)"
              >
                <Trash2 v-if="cancelandoId !== b.id" class="h-3.5 w-3.5 text-red-600" />
                <span v-else class="inline-block h-3 w-3 animate-spin rounded-full border-2 border-red-600 border-t-transparent" />
              </button>
            </div>
          </td>
        </tr>
        <tr v-if="!cargando && busquedas.length === 0" data-testid="sin-resultados">
          <td :colspan="COLUMNAS" class="px-6 py-14 text-center text-dark-400">
            <Inbox class="mx-auto mb-2 h-9 w-9 text-dark-300" />
            <p class="text-sm font-semibold text-dark-700">No se encontraron búsquedas con los filtros actuales</p>
            <p class="mt-0.5 text-xs text-dark-400">Probá restableciendo los filtros o ampliando los términos de búsqueda.</p>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
