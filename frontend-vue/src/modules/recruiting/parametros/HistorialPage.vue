<script setup lang="ts">
import { History, X } from '@lucide/vue'
import { computed, ref } from 'vue'

import { ErrorApi, parametrosRepository } from './api/parametros.repository'
import ParametrosLayout from './components/ParametrosLayout.vue'
import { useHistorial } from './composables/useHistorial'
import {
  formatearFechaHistorial,
  resultadoArchivo,
  resultadoCarga,
  textoTipoCarga,
} from './presentacion'
import type { HistorialCargaCvDetalle, HistorialCargaCvItem } from './types'

const POR_PAGINA = 20

interface Filtros {
  fecha_desde: string
  fecha_hasta: string
  usuario: string
  tipo_carga: string
  resultado: string
}

function filtrosVacios(): Filtros {
  return { fecha_desde: '', fecha_hasta: '', usuario: '', tipo_carga: '', resultado: '' }
}

const filtros = ref<Filtros>(filtrosVacios())
const aplicados = ref<Filtros>(filtrosVacios())
const pagina = ref(1)

const parametros = computed(() => {
  const valores = new URLSearchParams({ pagina: String(pagina.value), por_pagina: String(POR_PAGINA) })
  for (const [clave, valor] of Object.entries(aplicados.value)) {
    if (valor) valores.set(clave, valor)
  }
  return valores.toString()
})

const consulta = useHistorial(parametros)
const items = computed(() => consulta.data.value?.items ?? [])
const total = computed(() => consulta.data.value?.total ?? 0)
const totalPaginas = computed(() => consulta.data.value?.total_paginas ?? 1)
const paginaActual = computed(() => consulta.data.value?.pagina ?? pagina.value)
const cargando = computed(() => consulta.isPending.value || consulta.isFetching.value)
const error = computed(() =>
  consulta.error.value
    ? consulta.error.value instanceof ErrorApi && consulta.error.value.estado === 0
      ? 'Error de conexión con el servidor.'
      : consulta.error.value.message
    : '',
)
const desde = computed(() => (total.value === 0 ? 0 : (paginaActual.value - 1) * POR_PAGINA + 1))
const hasta = computed(() => Math.min(paginaActual.value * POR_PAGINA, total.value))

function aplicar(): void {
  aplicados.value = { ...filtros.value }
  pagina.value = 1
}

function limpiar(): void {
  filtros.value = filtrosVacios()
  aplicados.value = filtrosVacios()
  pagina.value = 1
}

function irAPagina(nueva: number): void {
  if (nueva < 1 || nueva > totalPaginas.value) return
  pagina.value = nueva
}

// ---- Detalle de la operación --------------------------------------------------------------------------------------

const detalle = ref<HistorialCargaCvDetalle | null>(null)
const operacion = ref<HistorialCargaCvItem | null>(null)
const cargandoDetalle = ref(false)
const errorDetalle = ref('')

async function verDetalle(item: HistorialCargaCvItem): Promise<void> {
  operacion.value = item
  detalle.value = null
  errorDetalle.value = ''
  cargandoDetalle.value = true
  try {
    detalle.value = await parametrosRepository.historial.detalle(item.id)
  } catch (atrapado) {
    errorDetalle.value = mensajeDetalle(atrapado)
  } finally {
    cargandoDetalle.value = false
  }
}

function mensajeDetalle(atrapado: unknown): string {
  if (atrapado instanceof ErrorApi) {
    return atrapado.estado === 0 ? 'Error de conexión con el servidor.' : atrapado.message
  }
  if (atrapado instanceof Error && atrapado.message) return atrapado.message
  return 'No se pudo consultar el detalle.'
}

function cerrarDetalle(): void {
  detalle.value = null
  operacion.value = null
  errorDetalle.value = ''
}
</script>

<template>
  <ParametrosLayout activa="historial">
    <div class="flex items-center gap-3">
      <span class="rounded-xl bg-primary-50 p-2.5 text-primary-600"><History class="h-5 w-5" /></span>
      <div>
        <h2 class="text-base font-bold text-dark-900">Historial de cargas de CV</h2>
        <p class="mt-0.5 text-xs text-dark-400">
          Consulta de las operaciones de carga individual y masiva (solo lectura)
        </p>
      </div>
    </div>

    <form
      class="grid grid-cols-1 items-end gap-3 rounded-2xl border border-dark-100 bg-white p-4 shadow-soft sm:grid-cols-2 lg:grid-cols-6"
      data-testid="historial-filtros"
      @submit.prevent="aplicar"
    >
      <label class="text-xs font-semibold text-dark-600">
        Desde
        <input
          v-model="filtros.fecha_desde"
          type="date"
          data-testid="historial-filtro-desde"
          class="mt-1 w-full rounded-lg border border-dark-200 px-3 py-2 text-sm font-normal"
        />
      </label>
      <label class="text-xs font-semibold text-dark-600">
        Hasta
        <input
          v-model="filtros.fecha_hasta"
          type="date"
          data-testid="historial-filtro-hasta"
          class="mt-1 w-full rounded-lg border border-dark-200 px-3 py-2 text-sm font-normal"
        />
      </label>
      <label class="text-xs font-semibold text-dark-600">
        Usuario
        <input
          v-model="filtros.usuario"
          type="text"
          maxlength="100"
          placeholder="Nombre"
          data-testid="historial-filtro-usuario"
          class="mt-1 w-full rounded-lg border border-dark-200 px-3 py-2 text-sm font-normal"
        />
      </label>
      <label class="text-xs font-semibold text-dark-600">
        Tipo de carga
        <select
          v-model="filtros.tipo_carga"
          data-testid="historial-filtro-tipo"
          class="mt-1 w-full rounded-lg border border-dark-200 bg-white px-3 py-2 text-sm font-normal"
        >
          <option value="">Todos</option>
          <option value="individual">Individual</option>
          <option value="masiva">Masiva</option>
        </select>
      </label>
      <label class="text-xs font-semibold text-dark-600">
        Resultado
        <select
          v-model="filtros.resultado"
          data-testid="historial-filtro-resultado"
          class="mt-1 w-full rounded-lg border border-dark-200 bg-white px-3 py-2 text-sm font-normal"
        >
          <option value="">Todos</option>
          <option value="completada">Completada</option>
          <option value="parcial">Parcial</option>
          <option value="fallida">Fallida</option>
          <option value="cancelada">Cancelada</option>
        </select>
      </label>
      <div class="flex gap-2">
        <button
          type="submit"
          data-testid="historial-filtrar"
          class="flex-1 cursor-pointer rounded-lg bg-primary-600 px-3 py-2 text-sm font-semibold text-white hover:bg-primary-700"
        >
          Filtrar
        </button>
        <button
          type="button"
          data-testid="historial-limpiar"
          class="cursor-pointer rounded-lg border border-dark-200 bg-white px-3 py-2 text-sm font-semibold text-dark-700 hover:bg-dark-50"
          @click="limpiar"
        >
          Limpiar
        </button>
      </div>
    </form>

    <div
      v-if="error"
      class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
      data-testid="historial-error"
    >
      {{ error }}
    </div>

    <div class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
      <div class="overflow-x-auto" data-testid="historial-tabla">
        <table class="w-full border-collapse text-left">
          <thead>
            <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold tracking-wider text-dark-500 uppercase">
              <th class="px-4 py-3.5 whitespace-nowrap">Fecha y hora</th>
              <th class="px-4 py-3.5">Usuario</th>
              <th class="px-4 py-3.5">Tipo</th>
              <th class="px-4 py-3.5 text-right">Total</th>
              <th class="px-4 py-3.5 text-right">Creados</th>
              <th class="px-4 py-3.5 text-right">Duplicados</th>
              <th class="px-4 py-3.5 text-right">Sin email</th>
              <th class="px-4 py-3.5 text-right">Rechazados</th>
              <th class="px-4 py-3.5">Resultado</th>
              <th class="px-4 py-3.5 text-right">Acción</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-dark-100 text-sm">
            <tr v-if="cargando">
              <td colspan="10" class="px-6 py-12 text-center text-xs text-dark-400">Consultando el historial...</td>
            </tr>
            <tr v-else-if="!error && items.length === 0" data-testid="historial-vacio">
              <td colspan="10" class="px-6 py-12 text-center text-sm text-dark-500">
                No hay operaciones de carga para los filtros seleccionados.
              </td>
            </tr>
            <tr
              v-for="item in items"
              :key="item.id"
              class="transition-colors hover:bg-dark-50/50"
              data-testid="historial-fila"
            >
              <td class="px-4 py-3.5 whitespace-nowrap text-dark-700">{{ formatearFechaHistorial(item.fecha_operacion) }}</td>
              <td class="px-4 py-3.5 font-medium text-dark-800">{{ item.usuario_nombre }}</td>
              <td class="px-4 py-3.5 text-dark-600">{{ textoTipoCarga(item.tipo_carga) }}</td>
              <td class="px-4 py-3.5 text-right font-semibold text-dark-800">{{ item.total_archivos }}</td>
              <td class="px-4 py-3.5 text-right text-emerald-700">{{ item.candidatos_creados }}</td>
              <td class="px-4 py-3.5 text-right text-amber-700">{{ item.duplicados }}</td>
              <td class="px-4 py-3.5 text-right text-orange-700">{{ item.sin_email }}</td>
              <td class="px-4 py-3.5 text-right text-rose-700">{{ item.rechazados }}</td>
              <td class="px-4 py-3.5">
                <span
                  class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold"
                  :class="resultadoCarga(item.resultado).clase"
                  data-testid="historial-resultado"
                >
                  <component :is="resultadoCarga(item.resultado).icono" class="h-3 w-3" />
                  <span>{{ resultadoCarga(item.resultado).texto }}</span>
                </span>
              </td>
              <td class="px-4 py-3.5 text-right">
                <button
                  type="button"
                  data-testid="historial-ver-detalle"
                  class="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-semibold text-primary-600 hover:bg-primary-50"
                  @click="verDetalle(item)"
                >
                  Ver detalle
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="total > 0"
        class="flex flex-col gap-3 border-t border-dark-100 px-6 py-4 text-xs text-dark-500 sm:flex-row sm:items-center sm:justify-between"
        data-testid="historial-paginacion"
      >
        <span>Mostrando <span>{{ desde }}</span>-<span>{{ hasta }}</span> de <span>{{ total }}</span> operaciones</span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            data-testid="historial-anterior"
            :disabled="paginaActual <= 1 || cargando"
            class="cursor-pointer rounded-lg border border-dark-200 bg-white px-3 py-1.5 font-semibold text-dark-700 hover:bg-dark-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="irAPagina(paginaActual - 1)"
          >
            Anterior
          </button>
          <span class="font-semibold whitespace-nowrap text-dark-700">
            Página <span>{{ paginaActual }}</span> de <span>{{ totalPaginas }}</span>
          </span>
          <button
            type="button"
            data-testid="historial-siguiente"
            :disabled="paginaActual >= totalPaginas || cargando"
            class="cursor-pointer rounded-lg border border-dark-200 bg-white px-3 py-1.5 font-semibold text-dark-700 hover:bg-dark-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="irAPagina(paginaActual + 1)"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>

    <!-- Detalle -->
    <div
      v-if="operacion"
      class="fixed inset-0 z-50 flex items-center justify-center bg-dark-900/40 p-4"
      role="dialog"
      aria-modal="true"
      data-testid="historial-detalle"
      @keydown.escape.window="cerrarDetalle"
      @click="cerrarDetalle"
    >
      <div class="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl bg-white shadow-lg" @click.stop>
        <div class="flex items-start justify-between gap-3 border-b border-dark-100 px-6 py-4">
          <div>
            <h3 class="text-base font-bold text-dark-900">Detalle de la carga</h3>
            <p class="mt-0.5 text-xs text-dark-500">
              <span>{{ formatearFechaHistorial(operacion.fecha_operacion) }}</span> ·
              <span>{{ operacion.usuario_nombre }}</span> ·
              <span>{{ textoTipoCarga(operacion.tipo_carga) }}</span>
            </p>
          </div>
          <button
            type="button"
            aria-label="Cerrar"
            data-testid="historial-detalle-cerrar"
            class="cursor-pointer rounded-lg p-2 text-dark-500 hover:bg-dark-50"
            @click="cerrarDetalle"
          >
            <X class="h-4 w-4" />
          </button>
        </div>
        <div class="overflow-auto">
          <div
            v-if="errorDetalle"
            class="m-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
          >
            {{ errorDetalle }}
          </div>
          <p v-if="cargandoDetalle" class="px-6 py-10 text-center text-xs text-dark-400">Consultando el detalle...</p>
          <table v-else-if="!errorDetalle" class="w-full border-collapse text-left">
            <thead>
              <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold tracking-wider text-dark-500 uppercase">
                <th class="px-4 py-3">Archivo</th>
                <th class="px-4 py-3">Resultado</th>
                <th class="px-4 py-3">Motivo</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-dark-100 text-sm">
              <tr v-if="detalle && detalle.archivos.length === 0">
                <td colspan="3" class="px-6 py-8 text-center text-xs text-dark-400">
                  Esta operación no tiene archivos registrados.
                </td>
              </tr>
              <tr
                v-for="archivo in detalle?.archivos ?? []"
                :key="`${archivo.orden}${archivo.nombre_archivo}`"
                data-testid="historial-detalle-fila"
              >
                <td class="px-4 py-3 font-medium break-all text-dark-800">{{ archivo.nombre_archivo }}</td>
                <td class="px-4 py-3">
                  <span
                    class="inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold"
                    :class="resultadoArchivo(archivo.resultado).clase"
                  >
                    {{ resultadoArchivo(archivo.resultado).texto }}
                  </span>
                </td>
                <td
                  class="px-4 py-3 text-xs text-dark-600"
                  :class="archivo.motivo ? '' : 'text-dark-400 italic'"
                >
                  {{ archivo.motivo || (archivo.resultado === 'creado' ? '-' : 'Sin motivo registrado') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </ParametrosLayout>
</template>
