<script setup lang="ts">
import { Kanban } from '@lucide/vue'

import { conteoEtapa, ETAPAS_TODAS, estiloEtapa, etiquetaEtapa, totalEnProceso } from '../etapas'
import type { CandidatoPipeline } from '../types'

/** Barra «Etapas del Proceso»: total en proceso y un filtro por etapa con su cantidad de candidatos. */
defineProps<{ candidatos: CandidatoPipeline[] }>()
const etapaFiltro = defineModel<string>({ required: true })

const TODAS = estiloEtapa('Todas')
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-5 mb-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3.5 pb-2 border-b border-dark-100/60">
      <div class="flex items-center gap-2">
        <Kanban class="w-5 h-5 text-primary-600" />
        <h2 class="text-base font-bold text-dark-900">Etapas del Proceso</h2>
      </div>
      <span class="text-xs text-dark-500 font-medium whitespace-nowrap">
        Total en proceso: <strong class="text-dark-900 font-bold" data-testid="total-en-proceso">{{ totalEnProceso(candidatos) }}</strong>
        candidatos
      </span>
    </div>

    <div class="flex flex-wrap lg:flex-nowrap items-center gap-2 lg:gap-1.5 pt-0.5 lg:overflow-x-auto">
      <!-- Botón Todas -->
      <button
        type="button"
        data-testid="etapa-Todas"
        :class="etapaFiltro === 'Todas' ? TODAS.tabActive : TODAS.tabInactive"
        class="inline-flex items-center justify-center gap-1.5 lg:flex-1 px-3 lg:px-2.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border cursor-pointer"
        @click="etapaFiltro = 'Todas'"
      >
        <span>Todas</span>
        <span
          class="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold leading-none"
          :class="etapaFiltro === 'Todas' ? TODAS.badgeCountActive : TODAS.badgeCountInactive"
          >{{ conteoEtapa(candidatos, 'Todas') }}</span
        >
      </button>

      <!-- Badges de cada etapa -->
      <button
        v-for="etapa in ETAPAS_TODAS"
        :key="etapa"
        type="button"
        :data-testid="`etapa-${etapa}`"
        :class="etapaFiltro === etapa ? estiloEtapa(etapa).tabActive : estiloEtapa(etapa).tabInactive"
        class="inline-flex items-center justify-center gap-1.5 lg:flex-1 px-3 lg:px-2.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all border cursor-pointer flex-shrink-0"
        @click="etapaFiltro = etapa"
      >
        <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="etapaFiltro === etapa ? 'bg-white' : estiloEtapa(etapa).dot"></span>
        <span>{{ etiquetaEtapa(etapa) }}</span>
        <span
          class="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold leading-none"
          :class="etapaFiltro === etapa ? estiloEtapa(etapa).badgeCountActive : estiloEtapa(etapa).badgeCountInactive"
          >{{ conteoEtapa(candidatos, etapa) }}</span
        >
      </button>
    </div>
  </div>
</template>
