<script setup lang="ts">
import { ArrowRight, BarChart2, Briefcase, Building2, Kanban, Loader2, MapPin, Plus, User, Users } from '@lucide/vue'

import { etiquetaModalidad, idTarjeta, urlPipeline } from '../presentacion'
import type { AlcanceCandidatos, BusquedaAbierta } from '../types'

/** Pipeline individual: tarjetas de las búsquedas Abiertas para elegir cuál gestionar. */
defineProps<{
  busquedas: BusquedaAbierta[]
  cargando: boolean
  alcance: AlcanceCandidatos
  puedeCrearBusquedas: boolean
  enlaceNuevaBusqueda: string
}>()

const vacantes = (op: BusquedaAbierta): number => op.vacantes || 1
</script>

<template>
  <div v-if="cargando" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
    <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando búsquedas...</span>
  </div>

  <!-- Lista de búsquedas abiertas -->
  <div v-else-if="busquedas.length > 0" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
    <div
      v-for="op in busquedas"
      :key="op.id"
      class="group bg-white rounded-2xl border border-dark-100 hover:border-primary-300 p-5 shadow-soft hover:shadow-md transition-all flex flex-col gap-3"
      data-testid="tarjeta-busqueda"
    >
      <!-- Encabezado de la tarjeta -->
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <p class="text-xs font-mono text-dark-400 mb-1">{{ idTarjeta(op) }}</p>
          <a
            :href="urlPipeline(op.id, alcance)"
            class="font-bold text-dark-900 text-base leading-tight hover:text-primary-700 transition-colors truncate block"
            >{{ op.titulo || 'Sin título' }}</a
          >
        </div>
        <span class="flex-shrink-0 flex flex-col items-end gap-1">
          <span class="px-2.5 py-0.5 text-xs font-bold rounded-lg border bg-emerald-50 text-emerald-700 border-emerald-200">Abierta</span>
          <span
            class="px-2.5 py-0.5 text-[10px] font-bold rounded-lg border"
            :class="op.externo_id ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-dark-50 text-dark-600 border-dark-200'"
            >{{ op.externo_id ? 'Externa' : 'Interna' }}</span
          >
        </span>
      </div>

      <!-- Datos de la búsqueda -->
      <div class="flex flex-col gap-1.5 text-sm text-dark-500">
        <div v-show="op.cliente" class="flex items-center gap-2">
          <Building2 class="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
          <span class="truncate">{{ op.cliente }}</span>
        </div>
        <div v-show="op.recruiter_nombre || op.reclutador" class="flex items-center gap-2">
          <User class="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
          <span class="truncate">{{ op.recruiter_nombre || op.reclutador }}</span>
        </div>
        <div class="flex items-center gap-4">
          <div v-show="op.seniority" class="flex items-center gap-1.5">
            <BarChart2 class="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
            <span>{{ op.seniority }}</span>
          </div>
          <div v-show="op.modalidad" class="flex items-center gap-1.5">
            <MapPin class="w-3.5 h-3.5 text-dark-400 flex-shrink-0" />
            <span>{{ etiquetaModalidad(op.modalidad) }}</span>
          </div>
        </div>
      </div>

      <!-- Footer con vacantes y CTA Gestión de Pipeline -->
      <div class="flex items-center justify-between pt-3 border-t border-dark-100 mt-auto gap-3">
        <div class="flex items-center gap-1.5 text-xs text-dark-500">
          <Users class="w-3.5 h-3.5 text-dark-400" />
          <span>
            <span>{{ vacantes(op) }}</span>
            <span v-if="vacantes(op) === 1"> vacante</span>
            <span v-if="vacantes(op) > 1"> vacantes</span>
          </span>
        </div>
        <a
          :href="urlPipeline(op.id, alcance)"
          class="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-xl shadow-soft hover:shadow-md transition-all cursor-pointer"
          title="Gestionar flujo y etapas de candidatos en el Pipeline"
        >
          <Kanban class="w-3.5 h-3.5" />
          <span>Gestionar Pipeline</span>
          <ArrowRight class="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  </div>

  <!-- Estado vacío: sin búsquedas abiertas en absoluto -->
  <div v-else class="bg-white rounded-2xl border border-dark-100 shadow-soft p-12 text-center" data-testid="pipeline-individual-vacio">
    <div class="w-16 h-16 bg-amber-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
      <Briefcase class="w-8 h-8 text-amber-400" />
    </div>
    <p class="text-dark-700 font-semibold text-lg mb-1">No hay búsquedas abiertas</p>
    <p class="text-dark-400 text-sm mb-4">
      Para asignar candidatos primero necesitás tener al menos una búsqueda en estado <strong>Abierta</strong>.
    </p>
    <a
      v-if="puedeCrearBusquedas"
      :href="enlaceNuevaBusqueda"
      class="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white font-semibold rounded-xl shadow-soft transition-colors text-sm cursor-pointer"
    >
      <Plus class="w-4 h-4" />
      Crear nueva búsqueda
    </a>
  </div>
</template>
