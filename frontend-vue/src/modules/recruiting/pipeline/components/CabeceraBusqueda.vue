<script setup lang="ts">
import { ArrowLeft, BarChart2, Building2, FileText, Lock, MapPin, Users } from '@lucide/vue'

import { etiquetaModalidad, RUTA_BUSQUEDAS, RUTA_GESTION } from '../presentacion'
import type { BusquedaPipeline } from '../types'

/** Cabecera del Pipeline de una búsqueda: migas, estado, tipo, datos, acceso a la ficha y aviso de búsqueda Ganada. */
defineProps<{
  op: BusquedaPipeline
  ganada: boolean
  enlaceFicha: string
}>()
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-6 mb-6">
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div>
        <div class="flex items-center gap-2 mb-2">
          <a :href="RUTA_BUSQUEDAS" class="text-xs font-semibold text-primary-600 hover:text-primary-700 flex items-center gap-1">
            <ArrowLeft class="w-3.5 h-3.5" />
            <span>Búsquedas</span>
          </a>
          <span class="text-dark-300">/</span>
          <a :href="`${RUTA_GESTION}?vista=individual`" class="text-xs font-semibold text-dark-500 hover:text-primary-600">
            Gestión de Búsquedas
          </a>
          <span
            data-testid="estado-busqueda"
            class="px-2.5 py-0.5 text-xs font-bold rounded-lg border"
            :class="op.estado === 'Ganada' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'"
            >{{ op.estado || 'Abierta' }}</span
          >
          <span
            class="px-2.5 py-0.5 text-xs font-bold rounded-lg border"
            :class="op.externo_id ? 'bg-indigo-50 text-indigo-700 border-indigo-200' : 'bg-dark-50 text-dark-600 border-dark-200'"
            >{{ op.externo_id ? 'Búsqueda externa' : 'Búsqueda interna' }}</span
          >
        </div>
        <!-- lg:leading-9: en Tailwind 3 lg:text-3xl pisaba leading-tight (36px); en Tailwind 4 no -->
        <h1 class="text-2xl lg:text-3xl font-bold text-dark-900 leading-tight lg:leading-9" data-testid="pipeline-titulo">
          {{ op.titulo || 'Tech Lead Python / Cloud' }}
        </h1>

        <div class="flex flex-wrap items-center gap-4 mt-3 text-sm text-dark-600">
          <div v-show="op.cliente" class="flex items-center gap-1.5">
            <Building2 class="w-4 h-4 text-dark-400" />
            <span class="font-medium text-dark-800">{{ op.cliente }}</span>
          </div>
          <div class="flex items-center gap-1.5">
            <Users class="w-4 h-4 text-dark-400" />
            <span>Vacantes: <strong class="text-dark-800">{{ op.vacantes || 1 }}</strong></span>
          </div>
          <div v-show="op.seniority" class="flex items-center gap-1.5">
            <BarChart2 class="w-4 h-4 text-dark-400" />
            <span>{{ op.seniority }}</span>
          </div>
          <div v-show="op.modalidad" class="flex items-center gap-1.5">
            <MapPin class="w-4 h-4 text-dark-400" />
            <span>{{ etiquetaModalidad(op.modalidad) }}</span>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2.5">
        <a
          :href="enlaceFicha"
          data-testid="ver-ficha"
          class="inline-flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-dark-50 text-dark-700 border border-dark-200 font-semibold rounded-xl shadow-soft transition-colors text-sm"
        >
          <FileText class="w-4 h-4 text-dark-500" />
          <span>Ver ficha de búsqueda</span>
        </a>
      </div>
    </div>
    <!-- Búsqueda Ganada: cerrada automáticamente al confirmar el Ingreso de un candidato (solo consulta) -->
    <div
      v-if="ganada"
      data-testid="aviso-busqueda-ganada"
      class="flex items-start gap-3 mt-4 px-4 py-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-800 text-sm"
    >
      <Lock class="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div>
        <p class="font-bold">Búsqueda Ganada y cerrada</p>
        <p class="text-xs mt-0.5">
          Un candidato llegó a la etapa Ingreso. Los candidatos quedan visibles solo para consulta: no se pueden agregar
          nuevos, moverlos de etapa, descartarlos ni reingresarlos.
        </p>
      </div>
    </div>
  </div>
</template>
