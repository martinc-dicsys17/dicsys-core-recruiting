<script setup lang="ts">
import { AlertCircle, Plus } from '@lucide/vue'
import Button from 'primevue/button'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { tomarAviso } from './aviso'
import ExternoDialog from './components/ExternoDialog.vue'
import FiltrosBusquedas from './components/FiltrosBusquedas.vue'
import PaginacionBusquedas from './components/PaginacionBusquedas.vue'
import TablaBusquedas from './components/TablaBusquedas.vue'
import {
  useCancelarBusqueda,
  useExternosDisponibles,
  useListadoBusquedas,
} from './composables/useListadoBusquedas'
import { usePermisosBusquedas } from './composables/usePermisosBusquedas'
import { filtrosDesdeQuery, queryDesdeFiltros } from './filtros'
import type { Busqueda, FiltrosBusquedas as Filtros } from './types'

const ruta = useRoute()
const router = useRouter()
const toast = useToast()

// Los filtros y la página viven en la URL (mismos nombres que la pantalla anterior): se pueden compartir,
// recargar y volver con «Atrás».
const filtros = computed(() => filtrosDesdeQuery(ruta.query))

const { permisos, consulta: consultaPermisos } = usePermisosBusquedas()
const puedeVerTipo = computed(() => permisos.value.puede_ver_lider_tipo_fecha_busqueda)
const listado = useListadoBusquedas(filtros, puedeVerTipo, computed(() => consultaPermisos.isFetched.value))
const externos = useExternosDisponibles(computed(() => permisos.value.puede_administrar_externos))

const busquedas = computed(() => listado.data.value?.items ?? [])
const total = computed(() => listado.data.value?.total ?? 0)
const totalPaginas = computed(() => listado.data.value?.total_paginas ?? 1)
const cargando = computed(() => !consultaPermisos.isFetched.value || listado.isFetching.value)

function irA(nuevos: Filtros): void {
  void router.push({ query: queryDesdeFiltros(nuevos) })
}

// Como el formulario anterior: el texto se aplica con Enter y viaja con cualquier cambio de un combo.
const textoBusqueda = ref(filtros.value.busqueda)
watch(
  () => filtros.value.busqueda,
  (nuevo) => (textoBusqueda.value = nuevo),
)
const conTexto = (): Filtros => ({ ...filtros.value, busqueda: textoBusqueda.value.trim() })
const cambiar = (parcial: Partial<Filtros>) => irA({ ...conTexto(), ...parcial, pagina: 1 })
const buscar = () => irA({ ...conTexto(), pagina: 1 })
// La página y el tamaño se cambian sobre los filtros de la URL, como los enlaces de la pantalla anterior.
const irAPagina = (pagina: number) => {
  if (pagina >= 1 && pagina <= totalPaginas.value) irA({ ...filtros.value, pagina })
}
const cambiarLimite = (limite: number) => irA({ ...filtros.value, limite, pagina: 1 })
const limpiarFiltros = () => {
  textoBusqueda.value = ''
  void router.push({ query: {} })
}

// Aviso pendiente de la pantalla anterior (por ejemplo, una búsqueda que no se pudo abrir), como el «flash» de Flask.
onMounted(() => {
  const aviso = tomarAviso()
  if (aviso) toast.add({ severity: aviso.tipo, summary: aviso.mensaje, life: 8000 })
})

// ---- Usuario externo ----
const conExterno = ref<Busqueda | null>(null)

// ---- Cancelar búsqueda (confirmación nativa del navegador, como la pantalla anterior) ----
const cancelar = useCancelarBusqueda()
const cancelandoId = ref<string | null>(null)

async function cancelarBusqueda(b: Busqueda): Promise<void> {
  if (cancelar.isPending.value) return
  if (!window.confirm(`¿Estás seguro de que querés cancelar la búsqueda "${b.titulo}"? Pasará al estado Cancelada; no se eliminan sus candidatos, historial ni asignaciones.`)) return
  cancelandoId.value = b.id
  try {
    await cancelar.mutateAsync(b.id)
    toast.add({ severity: 'success', summary: 'Búsqueda cancelada correctamente.', life: 5000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: e instanceof Error ? e.message : 'Error de conexión al cancelar la búsqueda.', life: 8000 })
  } finally {
    cancelandoId.value = null
  }
}

const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }
</script>

<template>
  <div class="animate-fade-in">
    <!-- Header simple y minimalista -->
    <div class="mb-6 flex items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <h1 class="mb-1 text-3xl font-bold text-dark-900">Búsquedas</h1>
      </div>
      <div>
        <a
          v-if="permisos.puede_crear_busquedas"
          href="/recruiting/oportunidades/nueva"
          data-testid="nueva-busqueda"
          class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700"
        >
          <Plus class="h-4 w-4" /><span>Búsqueda</span>
        </a>
      </div>
    </div>

    <div
      v-if="listado.isError.value"
      data-testid="oportunidades-error"
      class="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800"
    >
      <AlertCircle class="h-5 w-5 shrink-0" />
      <span class="flex-1">{{ listado.error.value?.message || 'No se pudo cargar el listado de búsquedas.' }}</span>
      <Button label="Reintentar" size="small" severity="secondary" outlined @click="listado.refetch()" />
    </div>

    <FiltrosBusquedas
      v-model:texto="textoBusqueda"
      :filtros="filtros"
      :puede-ver-tipo="puedeVerTipo"
      @cambiar="cambiar"
      @buscar="buscar"
      @limpiar="limpiarFiltros"
    />

    <div class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
      <TablaBusquedas
        :busquedas="busquedas"
        :cargando="cargando"
        :ver-lider="puedeVerTipo"
        :puede-administrar-externos="permisos.puede_administrar_externos"
        :puede-cancelar="permisos.puede_eliminar_busquedas"
        :cancelando-id="cancelandoId"
        @externo="conExterno = $event"
        @cancelar="cancelarBusqueda"
      />
      <PaginacionBusquedas
        :pagina="filtros.pagina"
        :limite="filtros.limite"
        :total="total"
        :total-paginas="totalPaginas"
        :cargando="cargando"
        @pagina="irAPagina"
        @limite="cambiarLimite"
      />
    </div>

    <ExternoDialog v-if="permisos.puede_administrar_externos" v-model:busqueda="conExterno" :externos="externos.data.value ?? []" />

    <Toast position="top-right" :pt="ESTILOS_TOAST" />
  </div>
</template>
