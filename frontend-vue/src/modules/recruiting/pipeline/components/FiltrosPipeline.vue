<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { alcanceDesdeQuery, queryDeAlcance, queryDeVista, RUTA_GESTION } from '../presentacion'
import type { AlcanceCandidatos } from '../types'

/**
 * Filtro de candidatos (Todos / Propios) y selector de Vista (global / Pipeline individual), compartidos por la
 * pantalla Pipeline y el Pipeline de una búsqueda (antes _pipeline_filtros_tipo.html y _pipeline_vista_selector.html).
 * El filtro conserva el resto de los parámetros de la URL; el cambio de vista conserva el filtro.
 */
defineProps<{ vistaActual: 'global' | 'individual' }>()

const ruta = useRoute()
const router = useRouter()
const alcance = computed(() => alcanceDesdeQuery(ruta.query))

const CLASE_COMBO =
  'px-3 py-2.5 bg-white border border-dark-200 rounded-xl text-xs font-semibold text-dark-700 shadow-soft focus:outline-none focus:ring-2 focus:ring-primary-500 cursor-pointer'

function cambiarAlcance(evento: Event): void {
  const valor = (evento.target as HTMLSelectElement).value as AlcanceCandidatos
  void router.push({ query: queryDeAlcance(valor, ruta.query) })
}

function cambiarVista(evento: Event): void {
  const vista = (evento.target as HTMLSelectElement).value === 'individual' ? 'individual' : 'global'
  void router.push({ path: RUTA_GESTION, query: queryDeVista(vista, ruta.query) })
}
</script>

<template>
  <div id="pipeline-filtros-tipo" class="flex flex-wrap items-center gap-2">
    <label for="filtro-origen-candidato" class="text-xs font-semibold text-dark-500">Candidatos</label>
    <select id="filtro-origen-candidato" :value="alcance" :class="CLASE_COMBO" @change="cambiarAlcance">
      <option value="">Todos</option>
      <option value="propios">Propios</option>
    </select>
  </div>
  <div class="flex items-center gap-2">
    <label for="pipeline-vista" class="text-xs font-semibold text-dark-500">Vista</label>
    <select id="pipeline-vista" :value="vistaActual" :class="CLASE_COMBO" @change="cambiarVista">
      <option value="global">Vista global</option>
      <option value="individual">Pipeline individual</option>
    </select>
  </div>
</template>
