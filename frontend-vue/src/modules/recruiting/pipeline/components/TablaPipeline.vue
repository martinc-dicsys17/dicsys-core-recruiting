<script setup lang="ts">
import { ArrowRight, CheckCircle, Clock, Phone, RotateCcw, RotateCw, UserPlus, Users, UserX } from '@lucide/vue'
import { computed } from 'vue'

import { casoDeFila, estiloEtapa, normalizarEtapaNombre } from '../etapas'
import { idCandidato } from '../movimientos'
import { iniciales } from '../presentacion'
import type { CandidatoPipeline } from '../types'

/**
 * «Seguimiento de Candidatos en Proceso»: la tabla del Pipeline de una búsqueda con las acciones de cada candidato
 * (Mover Etapa, Ver Detalles, Descartar o Reingresar) y sus estados vacíos.
 */
const props = defineProps<{
  busquedaId: string
  candidatos: CandidatoPipeline[]
  filtrados: CandidatoPipeline[]
  etapaFiltro: string
  ganada: boolean
  puedeMoverDescartar: boolean
  puedeAsignarCandidatos: boolean
  /** «volver» (ya codificado) para la ficha del candidato: la dirección de esta pantalla sin el filtro de etapa. */
  volverCandidato: string
  /** «volver» (ya codificado) para Agregar Candidato: la dirección de esta pantalla. */
  volverActual: string
}>()

const emit = defineEmits<{
  mover: [candidato: CandidatoPipeline]
  descartar: [candidato: CandidatoPipeline]
  reingresar: [candidato: CandidatoPipeline]
  verTodas: []
}>()

const enlaceCandidato = (c: CandidatoPipeline) => `/recruiting/candidatos/${c.id}?volver=${props.volverCandidato}`
const enlaceDetalle = (c: CandidatoPipeline) =>
  `/recruiting/oportunidades/${props.busquedaId}/candidatos/${idCandidato(c)}/detalle?origen=pipeline`
const enlaceAgregar = computed(() => `/recruiting/oportunidades/${props.busquedaId}/agregar-candidato?volver=${props.volverActual}`)

const tituloMover = computed(() =>
  props.ganada
    ? 'La búsqueda está Ganada y cerrada'
    : props.puedeMoverDescartar
      ? 'Avanzar a la siguiente etapa del embudo'
      : 'No tenés permiso para mover de etapa',
)
const tituloDescartar = computed(() =>
  props.ganada
    ? 'La búsqueda está Ganada y cerrada'
    : props.puedeMoverDescartar
      ? 'Descartar candidato de la búsqueda'
      : 'No tenés permiso para descartar',
)
const SIN_ACCION = 'opacity-50 cursor-not-allowed pointer-events-none'
const BOTON_DETALLES =
  'inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-dark-700 bg-dark-50 hover:bg-dark-100 border border-dark-200 rounded-lg transition-colors cursor-pointer'
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft overflow-hidden">
    <!-- Encabezado de la sección -->
    <div class="px-5 py-4 border-b border-dark-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-dark-50/50">
      <div>
        <h3 class="text-base font-bold text-dark-900 flex items-center gap-2">
          <Users class="w-4 h-4 text-primary-600" />
          <span>Seguimiento de Candidatos en Proceso</span>
        </h3>
      </div>
      <div class="text-xs text-dark-500 font-medium sm:text-right pr-1" data-testid="indicador-candidatos">
        Mostrando <strong class="text-dark-800">{{ filtrados.length }}</strong> de <span>{{ candidatos.length }}</span> candidatos
      </div>
    </div>

    <!-- Tabla -->
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm" data-testid="tabla-pipeline">
        <thead>
          <tr class="bg-dark-50 text-dark-500 font-semibold text-xs uppercase tracking-wider border-b border-dark-100">
            <th class="py-3 px-4">Candidato</th>
            <th class="py-3 px-4">Seniority</th>
            <th class="py-3 px-4">Teléfono / Contacto</th>
            <th class="py-3 px-4">Etapa Actual</th>
            <th class="py-3 px-4 text-right">Acción</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-dark-100">
          <tr v-for="cand in filtrados" :key="cand.id" class="hover:bg-dark-50/60 transition-colors" data-testid="fila-candidato">
            <!-- Nombre / Email -->
            <td class="py-3.5 px-4">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 rounded-xl bg-primary-100 text-primary-700 flex items-center justify-center font-bold text-xs flex-shrink-0">
                  {{ iniciales(cand.nombre) }}
                </div>
                <div>
                  <a
                    v-show="!cand.es_anonimo"
                    :href="enlaceCandidato(cand)"
                    class="font-semibold text-dark-900 hover:text-primary-600 transition-colors block"
                    >{{ cand.nombre }}</a
                  >
                  <span v-show="cand.es_anonimo" class="font-semibold text-dark-900 block">{{ cand.nombre }}</span>
                  <span class="text-xs text-dark-400 block">{{ cand.es_anonimo ? 'Oculto' : cand.email }}</span>
                  <!-- leading-5: el alto de línea (20px) que estos textos heredaban de text-sm en Tailwind 3 -->
                  <span class="text-[10px] leading-5 font-bold uppercase tracking-wide" :class="cand.es_externo ? 'text-indigo-600' : 'text-dark-400'">{{
                    cand.es_externo ? 'Externo' : 'Interno'
                  }}</span>
                  <span v-if="!cand.es_anonimo" class="text-[11px] leading-5 text-dark-500 block">{{
                    'Presentado por: ' + (cand.presentado_por || 'Sin identificar')
                  }}</span>
                </div>
              </div>
            </td>

            <!-- Seniority -->
            <td class="py-3.5 px-4">
              <span class="px-2.5 py-1 text-xs font-semibold rounded-lg bg-dark-100 text-dark-700">{{ cand.seniority || 'No especificado' }}</span>
            </td>

            <!-- Teléfono -->
            <td class="py-3.5 px-4">
              <div class="flex items-center gap-1.5 text-dark-600">
                <Phone class="w-3.5 h-3.5 text-dark-400" />
                <span class="text-xs font-mono">{{ cand.es_anonimo ? 'Oculto' : cand.telefono || 'Sin teléfono' }}</span>
              </div>
            </td>

            <!-- Etapa Actual -->
            <td class="py-3.5 px-4">
              <div class="flex flex-col">
                <span
                  class="inline-flex items-center gap-1.5 text-xs font-semibold rounded-full border px-2.5 py-1 w-fit"
                  :class="estiloEtapa(cand.etapa_actual, cand.estado).badge"
                  data-testid="etapa-actual"
                >
                  <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" :class="estiloEtapa(cand.etapa_actual, cand.estado).dot"></span>
                  <span>{{ normalizarEtapaNombre(cand.etapa_actual) }}</span>
                </span>
                <span v-if="cand.motivo_descarte" class="text-[11px] leading-5 text-rose-600 italic mt-1 line-clamp-1" :title="cand.motivo_descarte">{{
                  'Motivo: ' + cand.motivo_descarte
                }}</span>
              </div>
            </td>

            <td class="py-3.5 px-4 text-right whitespace-nowrap">
              <!-- Caso 1: Candidato activo en el embudo (no terminal, no descartado) -->
              <div v-if="casoDeFila(cand) === 'activo'" class="inline-flex items-center gap-1.5 justify-end">
                <!-- Botón Primario: Mover Etapa -->
                <button
                  type="button"
                  data-testid="mover-etapa"
                  :disabled="cand.es_anonimo || !puedeMoverDescartar"
                  :aria-disabled="puedeMoverDescartar ? undefined : 'true'"
                  :title="tituloMover"
                  class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg shadow-soft transition-colors cursor-pointer"
                  :class="[cand.es_anonimo ? SIN_ACCION : '', puedeMoverDescartar ? '' : SIN_ACCION]"
                  @click="emit('mover', cand)"
                >
                  <ArrowRight class="w-3.5 h-3.5" />
                  <span>Mover Etapa</span>
                </button>

                <!-- Botón Ver Detalles -->
                <a v-show="!cand.es_anonimo" :href="enlaceDetalle(cand)" title="Ver historial de estados y fechas del candidato" :class="BOTON_DETALLES">
                  <Clock class="w-3.5 h-3.5" />
                  <span>Ver Detalles</span>
                </a>

                <!-- Botón Secundario / Alerta: Descartar -->
                <button
                  type="button"
                  data-testid="descartar"
                  :disabled="cand.es_anonimo || !puedeMoverDescartar"
                  :aria-disabled="puedeMoverDescartar ? undefined : 'true'"
                  :title="tituloDescartar"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition-colors cursor-pointer"
                  :class="[cand.es_anonimo ? SIN_ACCION : '', puedeMoverDescartar ? '' : SIN_ACCION]"
                  @click="emit('descartar', cand)"
                >
                  <UserX class="w-3.5 h-3.5" />
                  <span>Descartar</span>
                </button>
              </div>

              <!-- Caso 2: Candidato en etapa terminal Ingreso (sin mutaciones, solo Ver Detalles) -->
              <div v-else-if="casoDeFila(cand) === 'ingreso'" class="inline-flex items-center gap-1.5 justify-end">
                <span class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold rounded-lg bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <CheckCircle class="w-3.5 h-3.5" />
                  <span>Ingreso Confirmado</span>
                </span>
                <a v-show="!cand.es_anonimo" :href="enlaceDetalle(cand)" title="Ver historial de estados y fechas del candidato" :class="BOTON_DETALLES">
                  <Clock class="w-3.5 h-3.5" />
                  <span>Ver Detalles</span>
                </a>
              </div>

              <!-- Caso 3: Candidatos descartados (Permite Ver Detalles y Reingresar por cambio de perfil) -->
              <div v-else class="inline-flex items-center gap-1.5 justify-end">
                <!-- Botón Excepcional: Reingresar al Proceso (no disponible en una búsqueda Ganada) -->
                <button
                  v-if="!ganada"
                  type="button"
                  data-testid="reingresar"
                  :disabled="cand.es_anonimo"
                  title="Reingresar al proceso por cambio de perfil/requerimientos (inicia en Entrevista RRHH)"
                  class="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-300 rounded-lg transition-colors cursor-pointer"
                  :class="cand.es_anonimo ? SIN_ACCION : ''"
                  @click="emit('reingresar', cand)"
                >
                  <RotateCw class="w-3.5 h-3.5 text-amber-600" />
                  <span>Reingresar al Proceso</span>
                </button>

                <a
                  v-show="!cand.es_anonimo"
                  :href="enlaceDetalle(cand)"
                  title="Ver historial de estados y motivo de descarte del candidato"
                  :class="BOTON_DETALLES"
                >
                  <Clock class="w-3.5 h-3.5" />
                  <span>Ver Detalles</span>
                </a>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Estado vacío cuando no hay candidatos asignados o con el filtro seleccionado -->
    <div v-if="filtrados.length === 0" class="py-12 px-4 flex flex-col items-center justify-center text-center" data-testid="pipeline-vacio">
      <div class="w-14 h-14 bg-dark-50 rounded-2xl flex items-center justify-center mb-3.5 text-dark-400">
        <Users class="w-7 h-7" />
      </div>
      <!-- Caso 1: Búsqueda sin ningún candidato asignado -->
      <div v-if="candidatos.length === 0" class="flex flex-col items-center justify-center max-w-md">
        <h3 class="text-base font-bold text-dark-900 mb-1">No hay candidatos asignados a esta búsqueda todavía</h3>
        <p class="text-xs text-dark-500 mb-5">
          Comenzá asignando candidatos desde el banco de talento o desde el detalle de la búsqueda para gestionar su
          proceso en el embudo.
        </p>
        <div class="flex items-center justify-center gap-3">
          <a
            v-if="puedeAsignarCandidatos"
            :href="enlaceAgregar"
            class="inline-flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 text-white font-semibold text-xs rounded-xl shadow-soft transition-all cursor-pointer"
          >
            <UserPlus class="w-4 h-4" />
            <span>Agregar Candidato a esta Búsqueda</span>
          </a>
        </div>
      </div>

      <!-- Caso 2: Hay candidatos en la búsqueda pero ninguno en la etapa filtrada -->
      <div v-else class="flex flex-col items-center justify-center max-w-md">
        <h3 class="text-base font-bold text-dark-800 mb-1">No se encontraron candidatos</h3>
        <p v-show="etapaFiltro !== 'Todas'" class="text-xs text-dark-500 mb-4">
          No hay candidatos en la etapa '<span>{{ etapaFiltro }}</span>'.
        </p>
        <div class="flex items-center justify-center gap-3">
          <button
            type="button"
            class="px-4 py-2 bg-dark-100 hover:bg-dark-200 text-dark-700 text-xs font-semibold rounded-xl transition-colors cursor-pointer inline-flex items-center gap-1.5"
            @click="emit('verTodas')"
          >
            <RotateCcw class="w-3.5 h-3.5" />
            <span>Ver todas las etapas</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
