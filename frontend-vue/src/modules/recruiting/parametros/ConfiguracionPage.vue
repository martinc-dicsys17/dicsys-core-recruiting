<script setup lang="ts">
import { Info, Loader2, Save, Sparkles } from '@lucide/vue'
import { computed, ref, watch } from 'vue'

import { ErrorApi } from './api/parametros.repository'
import AvisoFlotante from './components/AvisoFlotante.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import { useConfig } from './composables/useAbm'
import { useAviso } from './composables/useAviso'

const { consulta, guardar: guardarConfig } = useConfig()
const { mensaje, tipo, notificar } = useAviso()

const matchMinimo = ref(50)
const guardando = computed(() => guardarConfig.isPending.value)

watch(
  () => consulta.data.value,
  (datos) => {
    if (datos) matchMinimo.value = datos.match_minimo_porcentaje
  },
  { immediate: true },
)

watch(
  () => consulta.error.value,
  (error) => {
    if (error) notificar(mensajeDeError(error), 'error')
  },
)

function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) return error.message
  if (error instanceof Error && error.message) return error.message
  return 'Error de conexión.'
}

async function guardar(): Promise<void> {
  if (matchMinimo.value < 1 || matchMinimo.value > 100) {
    notificar('El valor debe estar entre 1 y 100.', 'error')
    return
  }
  try {
    await guardarConfig.mutateAsync(Number(matchMinimo.value))
    notificar('Configuración guardada correctamente.')
  } catch (error) {
    notificar(mensajeDeError(error), 'error')
  }
}
</script>

<template>
  <ParametrosLayout activa="config">
    <AvisoFlotante :mensaje="mensaje" :tipo="tipo" />

    <div class="max-w-xl rounded-2xl border border-dark-100 bg-white p-6 shadow-soft">
      <div class="mb-5 flex items-center gap-3 border-b border-dark-100 pb-4">
        <span class="rounded-xl bg-amber-50 p-2 text-amber-600">
          <Sparkles class="h-5 w-5" />
        </span>
        <div>
          <h2 class="text-sm font-bold text-dark-900">Porcentaje de Aceptación (Smart Matching)</h2>
          <p class="mt-0.5 text-xs text-dark-400">Umbral mínimo de coincidencia de skills para candidatos sugeridos</p>
        </div>
      </div>

      <div class="flex flex-col gap-5">
        <div>
          <div class="mb-2 flex items-center justify-between">
            <label class="text-xs font-semibold text-dark-700">Porcentaje mínimo de coincidencia</label>
            <div class="flex items-center gap-1.5">
              <input
                v-model.number="matchMinimo"
                type="number"
                min="1"
                max="100"
                class="w-16 rounded-lg border border-dark-200 px-2 py-1 text-center text-sm font-bold focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
              <span class="text-sm font-semibold text-dark-500">%</span>
            </div>
          </div>
          <input
            v-model.number="matchMinimo"
            type="range"
            min="1"
            max="100"
            step="1"
            class="h-2 w-full cursor-pointer appearance-none rounded-full bg-dark-100 accent-primary-600"
          />
          <div class="mt-1.5 flex justify-between text-xs text-dark-400">
            <span>1%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>

        <div class="flex items-center gap-3 rounded-xl bg-dark-50 px-4 py-3">
          <Info class="h-4 w-4 shrink-0 text-dark-400" />
          <p class="text-xs text-dark-500">
            Candidatos con match
            <span class="font-bold text-emerald-600">≥ {{ matchMinimo }}%</span>
            se mostrarán en <span class="font-semibold text-emerald-600">verde</span>. Los de
            <span class="font-bold text-rose-500">&lt; {{ matchMinimo }}%</span>
            se mostrarán en <span class="font-semibold text-rose-500">rojo</span> y requerirán confirmación para asignar.
          </p>
        </div>

        <div class="flex justify-end pt-1">
          <button
            type="button"
            :disabled="guardando"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700 disabled:opacity-50"
            @click="guardar"
          >
            <Loader2 v-if="guardando" class="h-4 w-4 animate-spin" />
            <Save v-else class="h-4 w-4" />
            <span>{{ guardando ? 'Guardando...' : 'Guardar cambios' }}</span>
          </button>
        </div>
      </div>
    </div>
  </ParametrosLayout>
</template>
