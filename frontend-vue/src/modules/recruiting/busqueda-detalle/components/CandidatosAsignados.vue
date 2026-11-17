<script setup lang="ts">
import { Eye, FileUp, Mail, Phone, Plus, Users } from '@lucide/vue'
import { computed, ref } from 'vue'

import { claseEtapa, iniciales } from '../presentacion'
import type { CandidatoAsignado } from '../types'

/** Tarjeta «Candidatos Asignados a la Búsqueda» (pipeline) con la carga de CV del grupo EXTERNOS. */
const props = defineProps<{
  busquedaId: string
  candidatos: CandidatoAsignado[]
  /** Dirección de esta pantalla con sus parámetros (sin /v2): el «volver» de las fichas y del alta. */
  volverActual: string
  esExterno: boolean
  puedeCargarCv: boolean
  cargandoCv: boolean
}>()
const emit = defineEmits<{ cargarCv: [archivo: File] }>()

const entradaCv = ref<HTMLInputElement | null>(null)
const volver = computed(() => encodeURIComponent(props.volverActual))
const enlaceNuevo = computed(
  () => `/recruiting/candidatos/nuevo?busqueda_id=${props.busquedaId}&volver=${volver.value}`,
)
const enlaceFicha = (c: CandidatoAsignado) => `/recruiting/candidatos/${c.candidato_id || c.id}?volver=${volver.value}`
const nombreDe = (c: CandidatoAsignado) => c.nombre || `${c.nombre_pila || ''} ${c.apellido || ''}`
const etapaDe = (c: CandidatoAsignado) => c.etapa_actual || c.etapa || 'Postulado'

function alElegirArchivo(evento: Event): void {
  const entrada = evento.target as HTMLInputElement
  const archivo = entrada.files?.[0]
  entrada.value = ''
  if (archivo) emit('cargarCv', archivo)
}
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-dark-100 gap-3">
      <div>
        <h2 class="text-base font-bold text-dark-900 flex items-center gap-2">
          <Users class="w-5 h-5 text-primary-600" />
          <span>Candidatos Asignados a la Búsqueda</span>
        </h2>
      </div>
      <div v-if="puedeCargarCv" class="flex flex-wrap items-center gap-3">
        <a
          :href="enlaceNuevo"
          data-testid="nuevo-candidato-busqueda"
          class="inline-flex items-center gap-2 px-4 py-2.5 bg-white border border-dark-200 hover:border-primary-400 text-dark-700 font-semibold rounded-xl shadow-soft transition-colors cursor-pointer text-sm"
        >
          <Plus class="w-4 h-4" />
          <span>Nuevo Candidato</span>
        </a>
        <input
          ref="entradaCv"
          type="file"
          accept=".pdf,.doc,.docx"
          class="hidden"
          data-testid="input-cargar-cv-busqueda"
          @change="alElegirArchivo"
        />
        <button
          type="button"
          :disabled="cargandoCv"
          data-testid="cargar-cv-busqueda"
          class="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-60 text-white font-semibold rounded-xl shadow-soft transition-colors cursor-pointer text-sm"
          @click="entradaCv?.click()"
        >
          <FileUp class="w-4 h-4" />
          <span>{{ cargandoCv ? 'Procesando CV...' : 'Cargar CV' }}</span>
        </button>
      </div>
    </div>

    <div v-if="candidatos.length > 0" class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm" data-testid="tabla-asignados">
        <thead>
          <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold uppercase tracking-wider text-dark-500">
            <th class="px-4 py-3">Candidato</th>
            <th class="px-4 py-3">Seniority</th>
            <th class="px-4 py-3">Contacto</th>
            <th class="px-4 py-3">Etapa Actual</th>
            <th class="px-4 py-3 text-right">Acción</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-dark-100 text-sm">
          <tr v-for="c in candidatos" :key="c.id || c.candidato_id" class="hover:bg-dark-50/60 transition-colors">
            <td class="px-4 py-3.5">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-primary-100 text-primary-700 flex items-center justify-center font-bold text-xs flex-shrink-0">
                  {{ iniciales(c.nombre || c.nombre_pila) }}
                </div>
                <div>
                  <span v-if="esExterno && c.es_anonimo" data-testid="candidato-anonimo-texto" class="font-semibold text-dark-900 block">
                    {{ nombreDe(c) }}
                  </span>
                  <a v-else :href="enlaceFicha(c)" class="font-semibold text-dark-900 hover:text-primary-600 transition-colors block">
                    {{ nombreDe(c) }}
                  </a>
                  <p class="text-xs text-dark-400 mt-0.5">{{ c.headline || 'Candidato en proceso' }}</p>
                </div>
              </div>
            </td>
            <td class="px-4 py-3.5">
              <span class="px-2.5 py-1 text-xs font-semibold rounded-lg bg-dark-100 text-dark-700">{{ c.seniority || 'Senior' }}</span>
            </td>
            <td class="px-4 py-3.5">
              <div class="space-y-0.5">
                <div class="flex items-center gap-1.5 text-xs text-dark-700">
                  <Phone class="w-3.5 h-3.5 text-dark-400" />
                  <span>{{ c.telefono || '—' }}</span>
                </div>
                <div class="flex items-center gap-1.5 text-xs text-dark-500">
                  <Mail class="w-3.5 h-3.5 text-dark-400" />
                  <span>{{ c.email || '—' }}</span>
                </div>
              </div>
            </td>
            <td class="px-4 py-3.5">
              <span class="px-2.5 py-1 text-xs font-semibold rounded-lg border inline-flex items-center gap-1.5" :class="claseEtapa(etapaDe(c))">
                {{ etapaDe(c) }}
              </span>
            </td>
            <td class="px-4 py-3.5 text-right whitespace-nowrap">
              <div class="inline-flex items-center justify-end gap-2">
                <a
                  v-if="!c.es_anonimo"
                  :href="enlaceFicha(c)"
                  title="Ver Ficha"
                  class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors cursor-pointer"
                >
                  <Eye class="w-3.5 h-3.5" />
                  <span>Ver Ficha</span>
                </a>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Sin candidatos asignados -->
    <div v-else class="py-10 text-center text-dark-500" data-testid="asignados-vacio">
      <div class="w-12 h-12 bg-dark-50 rounded-2xl flex items-center justify-center mx-auto mb-3 text-dark-400">
        <Users class="w-6 h-6" />
      </div>
      <p class="text-sm font-semibold text-dark-800">No hay candidatos asignados a esta búsqueda todavía</p>
      <p class="text-xs text-dark-400 mt-1">Podés asignar candidatos desde la pantalla de Candidatos o desde Gestión de Búsquedas.</p>
    </div>
  </div>
</template>
