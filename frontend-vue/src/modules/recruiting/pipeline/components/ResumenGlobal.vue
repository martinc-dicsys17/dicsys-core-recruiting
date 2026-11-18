<script setup lang="ts">
import { Briefcase, Loader2, Plus, Table2, X } from '@lucide/vue'
import { computed, nextTick, onBeforeUnmount, reactive, ref } from 'vue'

import { useCandidatosColumna } from '../composables/useVistaGlobal'
import {
  esMaximo,
  estiloCelda,
  estiloHead,
  filtrarFilas,
  formatoMoneda,
  inicialesPopup,
  tituloColumna,
  urlColumna,
  urlPipeline,
} from '../presentacion'
import type { AlcanceCandidatos, CandidatoColumna, ColumnaGlobal, FilaResumen } from '../types'

/**
 * Vista global del Pipeline: una fila por búsqueda Abierta y una columna por etapa, con búsqueda por texto y el
 * detalle de candidatos al pasar el mouse sobre una cifra.
 */
const props = defineProps<{
  columnas: ColumnaGlobal[]
  filas: FilaResumen[]
  cargando: boolean
  alcance: AlcanceCandidatos
  puedeCrearBusquedas: boolean
  enlaceNuevaBusqueda: string
}>()

const filtroTexto = ref('')
const filasFiltradas = computed(() => filtrarFilas(props.filas, filtroTexto.value))

// ---- Popup de candidatos al pasar el mouse sobre una cifra ----
const columna = useCandidatosColumna()
const popup = reactive({
  abierto: false,
  fila: null as FilaResumen | null,
  col: null as ColumnaGlobal | null,
  cargando: false,
  error: '',
  candidatos: [] as CandidatoColumna[],
})
const tarjeta = ref<HTMLElement | null>(null)
const lista = ref<HTMLElement | null>(null)
let temporizador: ReturnType<typeof setTimeout> | undefined
let pedido = 0
let ancla: HTMLElement | null = null

function abrirPopup(evento: Event, fila: FilaResumen, col: ColumnaGlobal): void {
  clearTimeout(temporizador)
  const mismo = popup.abierto && popup.fila?.id === fila.id && popup.col?.clave === col.clave
  posicionarPopup(evento.currentTarget as HTMLElement)
  if (mismo) return
  Object.assign(popup, { abierto: true, fila, col, error: '' })
  void nextTick(() => posicionarPopup())
  const req = ++pedido
  const enCache = columna.enCache(fila.id, col.clave, props.alcance)
  if (enCache) {
    Object.assign(popup, { candidatos: enCache, cargando: false })
    return
  }
  Object.assign(popup, { candidatos: [], cargando: true })
  columna
    .pedir(fila.id, col.clave, props.alcance)
    .then((datos) => {
      if (req !== pedido) return
      Object.assign(popup, { candidatos: datos, cargando: false })
      void nextTick(() => posicionarPopup())
    })
    .catch((e: unknown) => {
      if (req !== pedido) return
      Object.assign(popup, { error: (e instanceof Error && e.message) || 'Error al cargar los candidatos', cargando: false })
    })
}

function programarCierrePopup(): void {
  clearTimeout(temporizador)
  temporizador = setTimeout(cerrarPopup, 180)
}

const mantenerPopup = () => clearTimeout(temporizador)

function cerrarPopup(): void {
  clearTimeout(temporizador)
  pedido++
  Object.assign(popup, { abierto: false, cargando: false, candidatos: [], error: '' })
  ancla = null
}

/** Ubica el popup junto a la cifra sin salirse de la ventana (mismo cálculo que la pantalla anterior). */
function posicionarPopup(nuevaAncla?: HTMLElement): void {
  if (nuevaAncla) ancla = nuevaAncla
  if (!ancla || !ancla.isConnected) return
  const r = ancla.getBoundingClientRect()
  const el = tarjeta.value
  const l = lista.value
  if (l) l.style.maxHeight = ''
  const w = Math.min(el ? el.offsetWidth : 360, window.innerWidth - 16)
  const h = el ? el.offsetHeight : 200
  const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 8))
  // Siempre debajo de la cifra (4px de separación); si no entra, se acota el scroll interno del listado.
  // Solo si el espacio de abajo es muy chico se abre arriba, nunca encima de la cifra.
  const separacion = 4
  const margen = 8
  const altoMinLista = 96
  const chrome = l ? h - l.offsetHeight : 0
  const espacioAbajo = window.innerHeight - r.bottom - separacion - margen
  const espacioArriba = r.top - separacion - margen
  const abajo = espacioAbajo >= chrome + altoMinLista || espacioAbajo >= espacioArriba
  const espacio = abajo ? espacioAbajo : espacioArriba
  if (l && h > espacio) l.style.maxHeight = `${Math.max(altoMinLista, espacio - chrome)}px`
  const hFinal = el ? el.offsetHeight : h
  const top = abajo ? r.bottom + separacion : Math.max(margen, r.top - separacion - hFinal)
  if (el) {
    el.style.left = `${left}px`
    el.style.top = `${top}px`
  }
}

onBeforeUnmount(() => clearTimeout(temporizador))
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft overflow-hidden">
    <div class="px-5 py-4 border-b border-dark-100 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-dark-50/50">
      <div>
        <h2 class="text-base font-bold text-dark-900 flex items-center gap-2">
          <Table2 class="w-4 h-4 text-primary-600" />
          <span>Pipeline total de búsquedas</span>
        </h2>
        <p class="text-xs text-dark-500 mt-0.5">
          Candidatos por etapa. Hacé clic en una búsqueda o en una cifra para abrir su pipeline individual.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="filtroTexto"
          type="search"
          placeholder="Buscar por búsqueda o cliente"
          data-testid="buscar-busqueda"
          class="w-full sm:w-72 px-3.5 py-2 bg-white border border-dark-200 rounded-xl text-xs text-dark-800 focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>
    </div>

    <div v-if="cargando" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
      <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando pipeline...</span>
    </div>

    <template v-else>
      <div v-if="filas.length > 0" class="overflow-auto max-h-[70vh]">
        <table class="w-full text-left border-collapse text-sm" data-testid="tabla-pipeline-global">
          <thead>
            <tr class="text-xs uppercase tracking-wider font-semibold">
              <th class="sticky top-0 left-0 z-30 bg-dark-50 text-dark-500 py-3 px-4 min-w-[240px] border-b border-dark-100">Búsqueda</th>
              <th
                class="sticky top-0 z-20 bg-dark-50 text-dark-500 py-3 px-3 text-center border-b border-dark-100 w-20"
                title="Candidatos activos en las cinco columnas (no incluye descartados)"
              >
                Total
              </th>
              <th
                v-for="col in columnas"
                :key="col.clave"
                class="sticky top-0 z-20 py-3 px-3 text-center border-b border-dark-100 min-w-[110px]"
                :class="estiloHead(col.clave)"
                :title="tituloColumna(col)"
              >
                {{ col.nombre }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-dark-100">
            <tr v-for="fila in filasFiltradas" :key="fila.id" class="hover:bg-dark-50/60 transition-colors">
              <td class="sticky left-0 z-10 bg-white py-3 px-4">
                <a
                  :href="urlPipeline(fila.id, alcance)"
                  class="font-semibold text-dark-900 hover:text-primary-600 transition-colors block leading-tight"
                  title="Abrir pipeline individual"
                  >{{ fila.titulo || 'Sin título' }}</a
                >
                <span class="text-xs text-dark-400 block mt-0.5">
                  <span>{{ fila.cliente }}</span>
                  <span v-if="fila.id_busqueda">{{ ' · #' + fila.id_busqueda }}</span>
                  <span v-if="fila.estado && fila.estado !== 'Abierta'">{{ ' · ' + fila.estado }}</span>
                  <span>{{ fila.es_externa ? ' · Externa' : ' · Interna' }}</span>
                </span>
              </td>
              <td
                class="py-3 px-3 text-center font-bold text-dark-800"
                :title="fila.sin_clasificar ? fila.sin_clasificar + ' candidato(s) en etapas no clasificadas' : ''"
              >
                <a :href="urlPipeline(fila.id, alcance)" class="hover:text-primary-600">{{ fila.total }}</a>
              </td>
              <td v-for="col in columnas" :key="col.clave" class="py-3 px-3 text-center">
                <a
                  v-if="(fila.columnas[col.clave] || 0) > 0"
                  :href="urlColumna(fila, col, alcance)"
                  class="inline-flex items-center justify-center min-w-[2.25rem] px-2.5 py-1 rounded-lg border text-sm transition-colors"
                  :class="estiloCelda(col.clave) + (esMaximo(fila, col.clave) ? ' font-extrabold ring-2 ring-offset-1 ring-dark-300' : ' font-semibold')"
                  :title="tituloColumna(col)"
                  data-testid="cifra-columna"
                  @mouseenter="abrirPopup($event, fila, col)"
                  @mouseleave="programarCierrePopup"
                  @focus="abrirPopup($event, fila, col)"
                  @blur="programarCierrePopup"
                  @keydown.escape="cerrarPopup"
                  >{{ fila.columnas[col.clave] }}</a
                >
                <span v-else class="text-dark-300">–</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Sin resultados para el filtro de texto -->
      <div v-if="filas.length > 0 && filasFiltradas.length === 0" class="py-10 px-4 text-center">
        <p class="text-sm font-semibold text-dark-800 mb-1">No se encontraron búsquedas</p>
        <button
          type="button"
          class="mt-2 px-4 py-2 bg-dark-100 hover:bg-dark-200 text-dark-700 text-xs font-semibold rounded-xl transition-colors cursor-pointer"
          @click="filtroTexto = ''"
        >
          Limpiar búsqueda
        </button>
      </div>

      <!-- Estado vacío: sin búsquedas para el estado seleccionado -->
      <div v-if="filas.length === 0" class="p-12 text-center" data-testid="pipeline-global-vacio">
        <div class="w-16 h-16 bg-amber-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <Briefcase class="w-8 h-8 text-amber-400" />
        </div>
        <p class="text-dark-700 font-semibold text-lg mb-1">No hay búsquedas para mostrar</p>
        <p class="text-dark-400 text-sm mb-4">No hay búsquedas en estado <strong>Abierta</strong> visibles para tu usuario.</p>
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
  </div>

  <!-- Popup de candidatos de la cifra bajo el cursor -->
  <div
    ref="tarjeta"
    :class="popup.abierto ? '' : 'hidden'"
    role="dialog"
    aria-live="polite"
    data-testid="popup-columna"
    class="fixed z-50 w-[22rem] max-w-[calc(100vw-1rem)] bg-white rounded-xl border border-dark-100 shadow-[0_8px_30px_rgba(0,0,0,0.12)] p-4"
    @mouseenter="mantenerPopup"
    @mouseleave="programarCierrePopup"
  >
    <div class="flex items-start justify-between gap-3 mb-3">
      <h3 class="text-sm font-semibold text-dark-900 leading-snug">
        {{ popup.col && popup.fila ? `Candidatos en ${popup.col.nombre} (${popup.fila.titulo || 'Sin título'})` : '' }}
      </h3>
      <button type="button" class="text-dark-400 hover:text-dark-700 cursor-pointer" aria-label="Cerrar" @click="cerrarPopup">
        <X class="w-4 h-4" />
      </button>
    </div>
    <div ref="lista" class="max-h-[55vh] overflow-y-auto flex flex-col gap-2.5">
      <p v-show="popup.cargando" class="text-xs text-dark-500 py-4 text-center">Cargando candidatos…</p>
      <p v-show="popup.error" class="text-xs text-red-600 py-2">{{ popup.error }}</p>
      <div
        v-for="c in popup.candidatos"
        :key="c.candidato_id"
        class="flex items-center gap-3 p-3 rounded-lg border border-dark-100 bg-white"
      >
        <span class="w-10 h-10 rounded-full bg-primary-50 text-primary-700 text-xs font-bold flex items-center justify-center flex-shrink-0">{{
          inicialesPopup(c.nombre)
        }}</span>
        <div class="flex-1 min-w-0 text-xs text-dark-600 leading-relaxed">
          <p><span class="font-bold text-dark-900">Nombre:</span> <span>{{ c.nombre || '—' }}</span></p>
          <p><span class="font-bold text-dark-900">Pretensión:</span> <span>{{ c.es_anonimo ? 'Oculto' : formatoMoneda(c.pretension_salarial_bruta_ars) }}</span></p>
          <p><span class="font-bold text-dark-900">Rol Actual:</span> <span>{{ c.es_anonimo ? 'Oculto' : c.rol_actual || '—' }}</span></p>
          <p><span class="font-bold text-dark-900">Seniority:</span> <span>{{ c.seniority || '—' }}</span></p>
          <p v-if="!c.es_anonimo">
            <span class="font-bold text-dark-900">Presentado por:</span> <span>{{ c.presentado_por || 'Sin identificar' }}</span>
          </p>
          <p><span class="font-bold text-dark-900">Reclutador:</span> <span>{{ c.es_anonimo ? 'Oculto' : c.reclutador || 'Sin asignar' }}</span></p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Tailwind 3 (pantalla anterior) pintaba el placeholder en gris-400; Tailwind 4 lo reinicia distinto. */
input::placeholder {
  color: #9ca3af;
}
</style>
