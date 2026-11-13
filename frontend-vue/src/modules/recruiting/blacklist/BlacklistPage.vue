<script setup lang="ts">
import { Search, ShieldBan } from '@lucide/vue'
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import BlacklistTable from './components/BlacklistTable.vue'
import { useBlacklist } from './composables/useBlacklist'
import { coincidePorDigitos, normalizarTexto } from './busqueda'
import { useMotivosBlacklist } from './composables/useMotivosBlacklist'
import { ESTILO_MOTIVO } from './presentacion'
import type { PersonaBlacklist } from './types'

// Lazy loading del componente modal de detalle: solo se descarga en el navegador
// cuando el usuario hace clic por primera vez en una persona del listado.
const BlacklistDetailDialog = defineAsyncComponent(
  () => import('./components/BlacklistDetailDialog.vue'),
)

const { listado, reactivar } = useBlacklist()
const toast = useToast()
const personas = computed(() => listado.data.value ?? [])

const busqueda = ref('')
const TODOS = 'todos'
// 'todos' o el texto del motivo (el que viene del catálogo y el que guarda cada persona)
const filtroMotivo = ref<string>(TODOS)
const primeraFila = ref(0)
const enDetalle = ref<PersonaBlacklist | null>(null)
const detalleCargado = ref(false)

// Activa la carga diferida del diálogo cuando se selecciona una persona
watch(enDetalle, (nueva) => {
  if (nueva) detalleCargado.value = true
})

interface OpcionMotivo {
  valor: string
  etiqueta: string
}
// Las opciones salen del catálogo de la base (GET /recruiting/blacklist/motivos), sin textos fijos.
const { motivos } = useMotivosBlacklist()
const opcionesMotivo = computed<OpcionMotivo[]>(() => [
  { valor: TODOS, etiqueta: 'Todos los motivos' },
  ...(motivos.data.value ?? []).map((m) => ({ valor: m.motivo, etiqueta: m.motivo })),
])

const filtradas = computed(() => {
  const termino = normalizarTexto(busqueda.value.trim())
  return personas.value.filter(
    (p) =>
      (!filtroMotivo.value || filtroMotivo.value === TODOS || p.motivo === filtroMotivo.value) &&
      (!termino ||
        normalizarTexto(
          `${p.nombre} ${p.apellido} ${p.documento} ${p.email} ${p.observacion}`,
        ).includes(termino) ||
        coincidePorDigitos(termino, p.documento, p.telefono)),
  )
})

const hayFiltros = computed(() => Boolean(busqueda.value.trim() || (filtroMotivo.value && filtroMotivo.value !== TODOS)))

watch([busqueda, filtroMotivo], () => (primeraFila.value = 0))
// Si al quitar una persona la página actual queda vacía, se vuelve a la primera.
watch(
  () => filtradas.value.length,
  (total) => {
    if (primeraFila.value >= total) primeraFila.value = 0
  },
)

function limpiarFiltros(): void {
  busqueda.value = ''
  filtroMotivo.value = TODOS
}

function reactivarPersona(persona: PersonaBlacklist): void {
  enDetalle.value = null
  reactivar.mutate(persona, {
    onSuccess: () =>
      toast.add({
        severity: 'success',
        summary: `${persona.nombre} ${persona.apellido}`,
        detail: 'Persona reactivada correctamente. Se quitó de Blacklist',
        life: 5000,
      }),
    onError: (error) =>
      toast.add({
        severity: 'error',
        summary: 'No se pudo reactivar',
        detail: error instanceof Error ? error.message : 'Intentá nuevamente.',
        life: 8000,
      }),
  })
}

// El Toast queda ubicado debajo del encabezado general, con visibilidad y destaque óptimos.
const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }
</script>

<template>
  <div class="relative isolate -m-6 min-h-[calc(100vh-68px)] bg-slate-50/70 p-6 text-dark-900">
    <div class="animate-fade-in">
      <header class="mb-7 flex flex-wrap items-center gap-4">
        <span
          class="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-bordo-700 to-dark-900 text-white shadow-sm ring-1 ring-dark-900/10"
        >
          <ShieldBan class="h-6 w-6 text-white" />
        </span>
        <div>
          <h1 class="text-3xl font-extrabold tracking-tight text-dark-900">Blacklist</h1>
          <p class="text-xs text-dark-400 mt-0.5">Gestión y consulta de personas no entrevistables</p>
        </div>
      </header>

      <section class="overflow-hidden rounded-2xl bg-white shadow-xs border border-dark-200">
        <!-- Búsqueda y filtro, integrados en la cabecera blanca de la grilla -->
        <div class="flex flex-col gap-3 p-5 border-b border-dark-100 md:flex-row md:items-center bg-white">
          <IconField class="flex-1">
            <InputIcon><Search class="h-4 w-4 text-dark-400" /></InputIcon>
            <InputText
              v-model="busqueda"
              type="search"
              fluid
              placeholder="Buscar por nombre, DNI, correo o teléfono..."
              aria-label="Buscar en la Blacklist"
              class="bg-white!"
            />
          </IconField>
          <Select
            v-model="filtroMotivo"
            :options="opcionesMotivo"
            option-label="etiqueta"
            option-value="valor"
            scroll-height="28rem"
            :pt="{ listContainer: { style: 'max-height: min(28rem, calc(100vh - 8rem))' } }"
            class="md:w-80 bg-white!"
            aria-label="Filtrar por motivo"
          >
            <template #value="{ value }">
              <span class="flex items-center gap-2.5">
                <span class="h-2 w-2 rounded-full" :class="ESTILO_MOTIVO.punto"></span>
                <span class="text-dark-800">
                  {{ value && value !== TODOS ? value : 'Todos los motivos' }}
                </span>
              </span>
            </template>
            <template #option="{ option }: { option: OpcionMotivo }">
              <span class="flex items-center gap-2.5">
                <span class="h-2 w-2 rounded-full" :class="ESTILO_MOTIVO.punto"></span>
                <span :class="option.valor === TODOS ? 'text-dark-900 font-medium' : 'text-dark-700'">
                  {{ option.etiqueta }}
                </span>
              </span>
            </template>
          </Select>
        </div>

        <div v-if="listado.isError.value" class="border-t border-dark-100 px-6 py-16 text-center">
          <p class="mb-3 text-sm text-dark-600">No se pudo cargar la Blacklist.</p>
          <Button label="Reintentar" size="small" @click="listado.refetch()" />
        </div>

        <BlacklistTable
          v-else
          v-model:seleccionada="enDetalle"
          v-model:primera="primeraFila"
          :personas="filtradas"
          :cargando="listado.isPending.value"
          :hay-filtros="hayFiltros"
          @limpiar-filtros="limpiarFiltros"
        />
      </section>
    </div>

    <!-- Componente modal con carga diferida (solo se descarga al requerirse) -->
    <BlacklistDetailDialog
      v-if="detalleCargado"
      v-model:persona="enDetalle"
      @reactivar="reactivarPersona"
    />
    <Toast position="top-right" :pt="ESTILOS_TOAST" />
  </div>
</template>
