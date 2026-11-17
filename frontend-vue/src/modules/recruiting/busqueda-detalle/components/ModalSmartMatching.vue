<script setup lang="ts">
import { Award, Code2, Sparkles, UserCheck, X } from '@lucide/vue'
import { onBeforeUnmount, onMounted } from 'vue'

import type { DesgloseMatch } from '../types'

/** «Cálculo de Smart Matching»: desglose del porcentaje de un candidato sugerido. Escape, fondo y Cerrar lo cierran. */
defineProps<{ desglose: DesgloseMatch; matchMinimo: number }>()
const emit = defineEmits<{ cerrar: [] }>()

function alTeclear(evento: KeyboardEvent): void {
  if (evento.key === 'Escape') emit('cerrar')
}
onMounted(() => window.addEventListener('keydown', alTeclear))
onBeforeUnmount(() => window.removeEventListener('keydown', alTeclear))

const CHIP_REQ = 'px-2 py-0.5 rounded-md bg-white border border-dark-200 text-dark-700 font-medium text-[11px]'
const CHIP_COINC = 'px-2 py-0.5 rounded-md bg-emerald-100/70 border border-emerald-300 text-emerald-800 font-semibold text-[11px]'
const CHIP_FALT = 'px-2 py-0.5 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-[11px]'
const ROTULO = 'text-[10px] font-bold uppercase tracking-wider block mb-1'
</script>

<template>
  <div class="fixed inset-0 z-50 overflow-y-auto" role="dialog" aria-modal="true" aria-labelledby="modal-smart-matching-title" data-testid="modal-smart-matching">
    <div class="fixed inset-0 bg-dark-900/60 backdrop-blur-xs transition-opacity" @click="emit('cerrar')"></div>

    <div class="flex min-h-full items-center justify-center p-4 text-center">
      <div class="relative transform overflow-hidden rounded-2xl bg-white text-left shadow-2xl transition-all w-full max-w-lg p-6 border border-dark-100">
        <!-- Encabezado -->
        <div class="flex items-center justify-between pb-4 border-b border-dark-100 mb-5">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
              <Sparkles class="w-5 h-5" />
            </div>
            <div>
              <h3 id="modal-smart-matching-title" class="text-base font-bold text-dark-900">Cálculo de Smart Matching</h3>
              <p class="text-xs text-dark-500">{{ desglose.nombre }}</p>
            </div>
          </div>
          <button type="button" class="text-dark-400 hover:text-dark-600 p-1.5 rounded-lg hover:bg-dark-50 transition-colors" @click="emit('cerrar')">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div class="space-y-4 text-xs">
          <!-- Resultado final -->
          <div
            class="p-3.5 rounded-xl border flex items-center justify-between"
            :class="desglose.porcentaje >= matchMinimo ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900' : 'bg-rose-50/70 border-rose-200 text-rose-900'"
          >
            <div>
              <span class="text-[11px] font-semibold uppercase tracking-wider block opacity-75">Resultado Final</span>
              <span class="text-2xl font-black">{{ desglose.porcentaje }}%</span>
              <span class="text-xs ml-1 font-semibold">{{ desglose.porcentaje >= matchMinimo ? '• Califica' : '• Por debajo del mínimo' }}</span>
            </div>
            <div class="text-right">
              <span class="text-[11px] block text-dark-500">Umbral mínimo requerido:</span>
              <span class="font-bold text-dark-700">{{ matchMinimo }}%</span>
            </div>
          </div>

          <!-- Skills / Tecnologías -->
          <div class="bg-dark-50/60 p-3.5 rounded-xl border border-dark-100 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="font-bold text-dark-800 flex items-center gap-1.5 text-xs">
                <Code2 class="w-3.5 h-3.5 text-primary-600" />
                <span>Skills / Tecnologías</span>
              </span>
              <span class="text-[11px] text-dark-500">{{ desglose.coincSkills.length }} de {{ desglose.reqSkills.length }} coincidentes</span>
            </div>
            <div>
              <span :class="[ROTULO, 'text-dark-500']">Requeridas en la búsqueda:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="s in desglose.reqSkills" :key="s" :class="CHIP_REQ">{{ s }}</span>
                <span v-if="!desglose.reqSkills.length" class="text-dark-400 italic text-[11px]">Ninguna tecnología especificada</span>
              </div>
            </div>
            <div>
              <span :class="[ROTULO, 'text-emerald-700']">Coincidentes con el candidato:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="s in desglose.coincSkills" :key="s" :class="CHIP_COINC">{{ s }}</span>
                <span v-if="!desglose.coincSkills.length" class="text-dark-400 italic text-[11px]">Sin coincidencias técnicas</span>
              </div>
            </div>
            <div v-if="desglose.faltSkills.length > 0">
              <span :class="[ROTULO, 'text-rose-600']">Faltantes en el candidato:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="s in desglose.faltSkills" :key="s" :class="CHIP_FALT">{{ s }}</span>
              </div>
            </div>
          </div>

          <!-- Habilidades / Competencias (si aplican) -->
          <div v-if="desglose.aplicaHabs" class="bg-dark-50/60 p-3.5 rounded-xl border border-dark-100 space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="font-bold text-dark-800 flex items-center gap-1.5 text-xs">
                <Award class="w-3.5 h-3.5 text-emerald-600" />
                <span>Habilidades / Competencias</span>
              </span>
              <span class="text-[11px] text-dark-500">{{ desglose.coincHabs.length }} de {{ desglose.reqHabs.length }} coincidentes</span>
            </div>
            <div>
              <span :class="[ROTULO, 'text-dark-500']">Requeridas:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="h in desglose.reqHabs" :key="h" :class="CHIP_REQ">{{ h }}</span>
              </div>
            </div>
            <div>
              <span :class="[ROTULO, 'text-emerald-700']">Coincidentes:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="h in desglose.coincHabs" :key="h" :class="CHIP_COINC">{{ h }}</span>
                <span v-if="!desglose.coincHabs.length" class="text-dark-400 italic text-[11px]">Sin coincidencias</span>
              </div>
            </div>
            <div v-if="desglose.faltHabs.length > 0">
              <span :class="[ROTULO, 'text-rose-600']">Faltantes:</span>
              <div class="flex flex-wrap gap-1">
                <span v-for="h in desglose.faltHabs" :key="h" :class="CHIP_FALT">{{ h }}</span>
              </div>
            </div>
          </div>

          <!-- Seniority -->
          <div class="bg-dark-50/60 p-3.5 rounded-xl border border-dark-100 space-y-2">
            <div class="flex items-center justify-between">
              <span class="font-bold text-dark-800 flex items-center gap-1.5 text-xs">
                <UserCheck class="w-3.5 h-3.5 text-blue-600" />
                <span>Seniority</span>
              </span>
              <span
                class="px-2 py-0.5 rounded text-[11px] font-bold"
                :class="desglose.senCoincide ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-amber-100 text-amber-800 border border-amber-300'"
              >
                {{ desglose.senCoincide ? 'Coincide' : 'No coincide' }}
              </span>
            </div>
            <div class="grid grid-cols-2 gap-2 pt-1 text-[11px]">
              <div class="p-2 rounded-lg bg-white border border-dark-200">
                <span class="text-[10px] text-dark-400 block font-medium">Requerido en búsqueda:</span>
                <span class="font-bold text-dark-800">{{ desglose.senRequerido || 'Senior' }}</span>
              </div>
              <div class="p-2 rounded-lg bg-white border border-dark-200">
                <span class="text-[10px] text-dark-400 block font-medium">Candidato:</span>
                <span class="font-bold text-dark-800">{{ desglose.senCandidato || 'Senior' }}</span>
              </div>
            </div>
          </div>

          <!-- Fórmula de cálculo -->
          <div class="p-3 bg-dark-100/60 rounded-xl border border-dark-200/60 text-dark-700">
            <span class="text-[10px] font-bold uppercase tracking-wider text-dark-500 block mb-0.5">Fórmula de Cálculo:</span>
            <div class="font-mono text-[11.5px] font-semibold text-dark-900 mt-1">
              Skills (+{{ desglose.aporteSkills }}%) + Seniority (+{{ desglose.aporteSeniority }}%) =
              <span class="font-bold text-primary-700">{{ desglose.porcentaje }}%</span>
            </div>
            <div class="text-[10.5px] text-dark-500 mt-1">
              Skills: ({{ desglose.totCoinc }} coincidentes / {{ desglose.totReq || 1 }} requeridas) × 70% | Seniority:
              {{ desglose.senCoincide ? '100% × 30% = +30%' : '0% × 30% = +0%' }}
            </div>
          </div>
        </div>

        <!-- Pie -->
        <div class="pt-4 mt-5 border-t border-dark-100 flex justify-end">
          <button type="button" class="px-4 py-2 bg-dark-100 hover:bg-dark-200 text-dark-800 font-semibold rounded-xl text-xs transition-colors cursor-pointer" @click="emit('cerrar')">
            Cerrar
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
