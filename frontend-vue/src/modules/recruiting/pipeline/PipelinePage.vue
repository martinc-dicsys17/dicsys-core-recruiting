<script setup lang="ts">
import { AlertCircle, Briefcase, Layers } from '@lucide/vue'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import { tomarAviso } from '../busquedas/aviso'
import FiltrosPipeline from './components/FiltrosPipeline.vue'
import ResumenGlobal from './components/ResumenGlobal.vue'
import SeleccionIndividual from './components/SeleccionIndividual.vue'
import { usePermisosPipeline } from './composables/usePermisosPipeline'
import { useVistaGlobal } from './composables/useVistaGlobal'
import { alcanceDesdeQuery, ERROR_PIPELINE, RUTA_BUSQUEDAS, RUTA_NUEVA_BUSQUEDA, volverA, vistaDesdeQuery } from './presentacion'

/**
 * Pipeline (ítem «gestion_busquedas»): vista global (todas las búsquedas Abiertas con sus candidatos por columna) o
 * Pipeline individual (elegir la búsqueda a gestionar). La vista y el filtro de candidatos viven en la URL con los
 * nombres de la pantalla anterior (`vista`, `alcance_candidatos`).
 */
const ruta = useRoute()
const toast = useToast()

const vista = computed(() => vistaDesdeQuery(ruta.query))
const alcance = computed(() => alcanceDesdeQuery(ruta.query))

const { permisos, listos } = usePermisosPipeline()
const { resumen, abiertas } = useVistaGlobal(vista, alcance)

const consultaActiva = computed(() => (vista.value === 'global' ? resumen : abiertas))
const cargando = computed(() => !listos.value || consultaActiva.value.isPending.value)
const error = computed(() =>
  consultaActiva.value.isError.value ? consultaActiva.value.error.value?.message || ERROR_PIPELINE : null,
)

// «Crear nueva búsqueda» deja como «volver» la dirección de siempre de esta pantalla (sin el prefijo /v2).
const enlaceNuevaBusqueda = computed(
  () => `${RUTA_NUEVA_BUSQUEDA}?volver=${volverA(ruta.path, window.location.search)}`,
)

// Aviso pendiente de otra pantalla (por ejemplo, un Pipeline de una búsqueda sin acceso), como el «flash» de Flask.
onMounted(() => {
  const aviso = tomarAviso()
  if (aviso) toast.add({ severity: aviso.tipo, summary: aviso.mensaje, life: 8000 })
})

const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }
</script>

<template>
  <div class="animate-fade-in">
    <div
      v-if="error"
      class="mb-6 p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 flex items-center gap-3"
      data-testid="pipeline-error"
    >
      <AlertCircle class="w-5 h-5 flex-shrink-0" />
      <span>{{ error }}</span>
    </div>

    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
      <div>
        <div class="flex items-center gap-3 mb-1">
          <span class="p-2.5 bg-primary-50 text-primary-600 rounded-xl">
            <Layers class="w-6 h-6" />
          </span>
          <h1 class="text-3xl font-bold text-dark-900">Pipeline</h1>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <FiltrosPipeline :vista-actual="vista" />
        <a
          :href="RUTA_BUSQUEDAS"
          class="inline-flex items-center gap-2 px-4 py-2.5 bg-white hover:bg-dark-50 text-dark-700 text-xs font-semibold rounded-xl border border-dark-100 shadow-soft"
        >
          <Briefcase class="w-4 h-4 text-dark-400" />
          <span>Ver todas las búsquedas</span>
        </a>
      </div>
    </div>

    <!-- Vista global: una fila por búsqueda, una columna por etapa -->
    <ResumenGlobal
      v-if="vista === 'global'"
      :columnas="resumen.data.value?.columnas ?? []"
      :filas="resumen.data.value?.items ?? []"
      :cargando="cargando"
      :alcance="alcance"
      :puede-crear-busquedas="permisos.puede_crear_busquedas"
      :enlace-nueva-busqueda="enlaceNuevaBusqueda"
    />

    <!-- Pipeline individual: selección de la búsqueda a gestionar -->
    <SeleccionIndividual
      v-else
      :busquedas="abiertas.data.value ?? []"
      :cargando="cargando"
      :alcance="alcance"
      :puede-crear-busquedas="permisos.puede_crear_busquedas"
      :enlace-nueva-busqueda="enlaceNuevaBusqueda"
    />

    <Toast position="top-right" :pt="ESTILOS_TOAST" />
  </div>
</template>
