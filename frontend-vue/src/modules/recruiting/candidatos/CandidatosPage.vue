<script setup lang="ts">
import { AlertCircle, FileUp, Loader2, Plus, Trash2, Upload } from '@lucide/vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CLASE_BOTON_CANCELAR, CLASE_BOTON_PELIGRO, PT_DIALOGO } from './estilos'

import { candidatosRepository } from './api/candidatos.repository'
import AsignarBusquedaDialog from './components/AsignarBusquedaDialog.vue'
import CargaCvIndividualDialog from './components/CargaCvIndividualDialog.vue'
import CargaMasivaDialog from './components/CargaMasivaDialog.vue'
import FiltrosCandidatos from './components/FiltrosCandidatos.vue'
import PaginacionCandidatos from './components/PaginacionCandidatos.vue'
import TablaCandidatos from './components/TablaCandidatos.vue'
import { useCargaMasiva } from './composables/useCargaMasiva'
import { useEliminarCandidato, useListadoCandidatos } from './composables/useListadoCandidatos'
import { useOpcionesFiltros } from './composables/useOpcionesFiltros'
import { usePermisosCandidatos } from './composables/usePermisosCandidatos'
import { filtrosDesdeQuery, filtrosVacios, queryDesdeFiltros, urlDeVuelta } from './filtros'
import type { CandidatoListado, FiltrosListado } from './types'

const ruta = useRoute()
const router = useRouter()
const toast = useToast()

// Los filtros y la página viven en la URL (mismos nombres que la pantalla anterior): se pueden compartir,
// recargar y volver con «Atrás».
const filtros = computed(() => filtrosDesdeQuery(ruta.query))

const { permisos, consulta: consultaPermisos } = usePermisosCandidatos()
const opciones = useOpcionesFiltros()
const skillsDeLaCategoria = computed(() => opciones.data.value?.skillsPorCategoria[filtros.value.categoria] ?? [])
const listado = useListadoCandidatos(filtros, skillsDeLaCategoria, computed(() => opciones.isFetched.value))

const candidatos = computed(() => listado.data.value?.items ?? [])
const total = computed(() => listado.data.value?.total ?? 0)
const totalPaginas = computed(() => listado.data.value?.total_paginas ?? 1)
const cargando = computed(() => !opciones.isFetched.value || listado.isFetching.value)

function irA(nuevos: FiltrosListado): void {
  void router.push({ query: queryDesdeFiltros(nuevos) })
}
/** Cualquier cambio de filtro o de tamaño de página vuelve a la primera página. */
// El texto del buscador se aplica con Enter, pero la pantalla anterior también lo enviaba con cualquier otro cambio de
// filtro, de página o de tamaño: por eso se mantiene acá y se incluye siempre (lo que se ve = URL = consulta).
const textoBusqueda = ref(filtros.value.busqueda)
watch(
  () => filtros.value.busqueda,
  (nuevo) => (textoBusqueda.value = nuevo),
)
const conTexto = (): FiltrosListado => ({ ...filtros.value, busqueda: textoBusqueda.value.trim() })
const cambiar = (parcial: Partial<FiltrosListado>) => irA({ ...conTexto(), ...parcial, pagina: 1 })
const irAPagina = (pagina: number) => {
  if (pagina >= 1 && pagina <= totalPaginas.value) irA({ ...conTexto(), pagina })
}
const limpiarFiltros = () => {
  textoBusqueda.value = ''
  irA(filtrosVacios(filtros.value.limite))
}

// ---- Navegación a otras pantallas (mismos enlaces que la pantalla anterior) ----
const enlaceFicha = (id: string) => `/recruiting/candidatos/${id}`
const enlaceNuevo = '/recruiting/candidatos/nuevo'

/** «Ver detalles»: abre la primera postulación del candidato y vuelve a esta grilla con sus filtros. */
async function verDetalles(c: CandidatoListado): Promise<void> {
  try {
    const oportunidad = await candidatosRepository.primeraPostulacion(c.id)
    if (oportunidad) {
      const volver = encodeURIComponent(urlDeVuelta(filtros.value))
      window.location.assign(`/recruiting/oportunidades/${oportunidad}/candidatos/${c.id}/detalle?volver=${volver}`)
    }
  } catch (e) {
    // Como la pantalla anterior: si no se pueden obtener las postulaciones, no pasa nada.
    console.error('Error obteniendo pipelines del candidato:', e)
  }
}

// ---- Asignar a búsqueda ----
const aAsignar = ref<CandidatoListado | null>(null)

// ---- Eliminar (con confirmación) ----
const eliminar = useEliminarCandidato()
const aEliminar = ref<CandidatoListado | null>(null)
const nombreAEliminar = computed(() => `${aEliminar.value?.nombre ?? ''} ${aEliminar.value?.apellido ?? ''}`.trim())

async function confirmarEliminar(): Promise<void> {
  const c = aEliminar.value
  if (!c || eliminar.isPending.value) return
  try {
    await eliminar.mutateAsync(c.id)
    toast.add({ severity: 'success', summary: 'Candidato eliminado correctamente', life: 5000 })
    aEliminar.value = null
  } catch (e) {
    aEliminar.value = null
    toast.add({ severity: 'error', summary: e instanceof Error ? e.message : 'Error al eliminar el candidato.', life: 8000 })
  }
}

// ---- Carga de CV ----
const cargaIndividualAbierta = ref(false)
const cargaMasiva = useCargaMasiva((tipo, mensaje) =>
  toast.add({ severity: tipo === 'error' ? 'error' : 'warn', summary: mensaje, life: 8000 }),
)

// El Dashboard enlaza con ?accion=cargar-cv: se abre la carga individual (si el usuario puede) y se limpia la URL.
watch(
  () => [ruta.query.accion, consultaPermisos.isFetched.value] as const,
  ([accion, listos]) => {
    if (accion !== 'cargar-cv' || !listos) return
    if (permisos.value.puede_cargar_cv_general) cargaIndividualAbierta.value = true
    const { accion: _accion, ...resto } = ruta.query
    void router.replace({ query: resto })
  },
  { immediate: true },
)

const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }
const BOTON_CARGA =
  'group inline-flex cursor-pointer items-center gap-2.5 rounded-xl border border-dark-200 bg-white px-3.5 py-2 text-left text-dark-700 shadow-soft transition-all duration-150 hover:border-primary-400 hover:bg-primary-50/30'
const ICONO_CARGA =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600 transition-colors group-hover:bg-primary-100'
</script>

<template>
  <div class="animate-fade-in">
    <!-- Encabezado con acciones principales -->
    <div class="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div class="flex items-center gap-3">
        <h1 class="text-3xl font-bold text-dark-900">Candidatos</h1>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <template v-if="permisos.puede_cargar_cv_general">
          <button type="button" :class="BOTON_CARGA" title="Subí un CV para crear un candidato." data-testid="abrir-carga-individual" @click="cargaIndividualAbierta = true">
            <span :class="ICONO_CARGA"><FileUp class="h-4 w-4" /></span>
            <span>
              <span class="block text-xs leading-tight font-bold text-dark-800">Cargar CV Individual</span>
              <span class="mt-0.5 block text-[11px] leading-tight font-normal text-dark-400">Subí un CV para crear un candidato.</span>
            </span>
          </button>
          <button type="button" :class="BOTON_CARGA" title="Subí múltiples CVs para procesarlos en lote." data-testid="abrir-carga-masiva" @click="cargaMasiva.abrir()">
            <span :class="ICONO_CARGA"><Upload class="h-4 w-4" /></span>
            <span>
              <span class="block text-xs leading-tight font-bold text-dark-800">Cargar CVs Masivos</span>
              <span class="mt-0.5 block text-[11px] leading-tight font-normal text-dark-400">Subí múltiples CVs para procesarlos en lote.</span>
            </span>
          </button>
        </template>
        <!-- Nuevo Candidato: la ruta de Flask valida el permiso y lleva a la pantalla Vue del alta -->
        <a
          :href="enlaceNuevo"
          data-testid="nuevo-candidato"
          class="inline-flex cursor-pointer items-center justify-center gap-2 self-stretch rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700"
        >
          <Plus class="h-4 w-4" /><span>Nuevo Candidato</span>
        </a>
      </div>
    </div>

    <div
      v-if="listado.isError.value"
      data-testid="candidatos-error"
      class="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800"
    >
      <AlertCircle class="h-5 w-5 shrink-0" />
      <span class="flex-1">{{ listado.error.value?.message || 'No se pudo cargar el listado de candidatos.' }}</span>
      <Button label="Reintentar" size="small" severity="secondary" outlined @click="listado.refetch()" />
    </div>

    <FiltrosCandidatos v-model:texto="textoBusqueda" :filtros="filtros" :opciones="opciones.data.value" @cambiar="cambiar" @limpiar="limpiarFiltros" />

    <!-- La tarjeta ocupa el ancho disponible sin ensanchar la página; la tabla se desplaza dentro de ella -->
    <div class="relative w-0 min-w-full overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
      <TablaCandidatos
        :candidatos="candidatos"
        :cargando="cargando"
        :permisos="permisos"
        :puede-cargar-cv="permisos.puede_cargar_cv_general"
        :enlace-ficha="enlaceFicha"
        :eliminando-id="eliminar.isPending.value ? (aEliminar?.id ?? null) : null"
        @asignar="aAsignar = $event"
        @detalles="verDetalles"
        @eliminar="aEliminar = $event"
      />
      <PaginacionCandidatos
        :pagina="filtros.pagina"
        :limite="filtros.limite"
        :total="total"
        :total-paginas="totalPaginas"
        @pagina="irAPagina"
        @limite="cambiar({ limite: $event })"
      />
    </div>

    <CargaCvIndividualDialog v-model="cargaIndividualAbierta" />
    <CargaMasivaDialog :carga="cargaMasiva" />
    <AsignarBusquedaDialog v-model:candidato="aAsignar" />

    <!-- Confirmación previa a eliminar: la acción no se puede deshacer -->
    <Dialog
    :pt="PT_DIALOGO"
      :visible="aEliminar !== null"
      modal
      :draggable="false"
      :closable="!eliminar.isPending.value"
      style="width: 28rem"
      @update:visible="(abierto: boolean) => !abierto && !eliminar.isPending.value && (aEliminar = null)"
    >
      <template #header>
        <div class="flex items-center gap-2.5">
          <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-red-50 text-red-600"><Trash2 class="h-5 w-5" /></div>
          <h3 class="text-base font-bold text-dark-900">Eliminar candidato</h3>
        </div>
      </template>
      <p class="text-sm text-dark-700" data-testid="texto-eliminar">
        ¿Estás seguro de que deseas eliminar permanentemente a "{{ nombreAEliminar }}" de la base de datos? Esta
        acción no se puede deshacer.
      </p>
      <template #footer>
        <Button label="Cancelar" unstyled :class="CLASE_BOTON_CANCELAR" :disabled="eliminar.isPending.value" @click="aEliminar = null" />
        <Button unstyled :class="CLASE_BOTON_PELIGRO" :disabled="eliminar.isPending.value" data-testid="confirmar-eliminar" @click="confirmarEliminar">
          <Loader2 v-if="eliminar.isPending.value" class="h-4 w-4 animate-spin" />
          <span>Eliminar</span>
        </Button>
      </template>
    </Dialog>

    <Toast position="top-right" :pt="ESTILOS_TOAST" />
  </div>
</template>
