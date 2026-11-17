<script setup lang="ts">
import { Cpu, Sparkles, UserPlus } from '@lucide/vue'
import { computed } from 'vue'

import { iniciales, porcentajeMatch, tooltipMatch } from '../presentacion'
import type { CandidatoSugerido, Oportunidad } from '../types'

/** Tarjeta «Candidatos Sugeridos (Match de Skills)»: Smart Matching, con el desglose y «Postular a Búsqueda». */
const props = defineProps<{
  datos: Oportunidad
  sugeridos: CandidatoSugerido[]
  matchMinimo: number
  volverActual: string
  /** Id del candidato que se está postulando (su botón queda en «Postulando...»), o null. */
  postulandoId: string | null
}>()
const emit = defineEmits<{ postular: [candidato: CandidatoSugerido]; desglose: [candidato: CandidatoSugerido] }>()

const volver = computed(() => encodeURIComponent(props.volverActual))
const enlaceFicha = (c: CandidatoSugerido) => `/recruiting/candidatos/${c.id}?volver=${volver.value}`
const califica = (c: CandidatoSugerido) => porcentajeMatch(c) >= props.matchMinimo
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-dark-100 gap-3">
      <div>
        <h2 class="text-base font-bold text-dark-900 flex items-center gap-2">
          <Sparkles class="w-5 h-5 text-amber-500" />
          <span>Candidatos Sugeridos (Match de Skills)</span>
        </h2>
      </div>
      <div class="flex items-center gap-2">
        <span class="px-2.5 py-1 text-xs font-semibold rounded-lg bg-amber-50 text-amber-800 border border-amber-200 inline-flex items-center gap-1.5">
          <Cpu class="w-3.5 h-3.5 text-amber-600" />
          <span>Smart Matching Activo</span>
        </span>
      </div>
    </div>

    <div v-if="sugeridos.length > 0" class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm" data-testid="tabla-sugeridos">
        <thead>
          <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold uppercase tracking-wider text-dark-500">
            <th class="px-4 py-3">Candidato</th>
            <th class="px-4 py-3">Seniority</th>
            <th class="px-4 py-3">Match de Skills</th>
            <th class="px-4 py-3">Skills que Coinciden</th>
            <th class="px-4 py-3 text-right">Acción</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-dark-100 text-sm">
          <tr v-for="c in sugeridos" :key="c.id" class="hover:bg-dark-50/60 transition-colors">
            <td class="px-4 py-3.5">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-primary-100 text-primary-700 flex items-center justify-center font-bold text-xs flex-shrink-0">
                  {{ iniciales(c.nombre_completo || c.nombre) }}
                </div>
                <div>
                  <a :href="enlaceFicha(c)" class="font-semibold text-dark-900 hover:text-primary-600 transition-colors block">
                    {{ c.nombre_completo || c.nombre }}
                  </a>
                  <p class="text-xs text-dark-400 mt-0.5">{{ c.headline }}</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-3.5">
              <span class="px-2.5 py-1 text-xs font-semibold rounded-lg bg-dark-100 text-dark-700">{{ c.seniority }}</span>
            </td>
            <td class="px-4 py-3.5">
              <div class="flex items-center gap-2.5 min-w-[130px]">
                <div class="w-20 bg-dark-100 rounded-full h-2 overflow-hidden">
                  <div
                    class="h-2 rounded-full transition-all duration-500"
                    :class="califica(c) ? 'bg-emerald-500' : 'bg-rose-500'"
                    :style="{ width: `${porcentajeMatch(c)}%` }"
                  ></div>
                </div>
                <span
                  class="px-2 py-0.5 text-xs font-bold rounded-md border cursor-help transition-shadow hover:shadow-xs"
                  :class="califica(c) ? 'bg-emerald-50 text-emerald-600 border-emerald-200' : 'bg-rose-50 text-rose-600 border-rose-200'"
                  :title="tooltipMatch(datos, c)"
                  data-testid="porcentaje-match"
                >
                  {{ porcentajeMatch(c) }}%
                </span>
                <button
                  type="button"
                  title="Ver desglose del cálculo de Smart Matching"
                  data-testid="ver-desglose"
                  class="w-5 h-5 rounded-full bg-dark-100 hover:bg-primary-50 text-dark-500 hover:text-primary-600 border border-dark-200 hover:border-primary-300 flex items-center justify-center text-[11px] font-bold transition-all shadow-2xs cursor-pointer shrink-0"
                  @click="emit('desglose', c)"
                >
                  ?
                </button>
              </div>
            </td>
            <td class="px-4 py-3.5">
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="skill in c.skills_coincidentes ?? []"
                  :key="skill"
                  class="px-2 py-0.5 text-[11px] font-medium bg-dark-100 text-dark-700 rounded-md border border-dark-200/50"
                  >{{ skill }}</span
                >
              </div>
            </td>
            <td class="px-4 py-3.5 text-right whitespace-nowrap">
              <div class="inline-flex items-center justify-end gap-2">
                <button
                  type="button"
                  title="Postular a la búsqueda"
                  data-testid="postular"
                  :disabled="postulandoId !== null"
                  class="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-xl text-white bg-primary-600 hover:bg-primary-700 cursor-pointer shadow-soft disabled:cursor-not-allowed"
                  @click="emit('postular', c)"
                >
                  <svg v-if="postulandoId === c.id" class="w-3.5 h-3.5 animate-spin inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
                  </svg>
                  <UserPlus v-else class="w-3.5 h-3.5" />
                  <span>{{ postulandoId === c.id ? 'Postulando...' : 'Postular a Búsqueda' }}</span>
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Sin sugerencias -->
    <div v-else class="py-10 text-center text-dark-500" data-testid="sugeridos-vacio">
      <div class="w-12 h-12 bg-dark-50 rounded-2xl flex items-center justify-center mx-auto mb-3 text-dark-400">
        <Sparkles class="w-6 h-6" />
      </div>
      <p class="text-sm font-semibold text-dark-800">No hay sugerencias automáticas de candidatos para esta búsqueda</p>
      <p class="text-xs text-dark-400 mt-1">Podés asignar candidatos manualmente desde la sección de Gestión de Búsquedas.</p>
    </div>
  </div>
</template>
