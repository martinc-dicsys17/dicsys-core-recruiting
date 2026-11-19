<script setup lang="ts">
import { AlertCircle, Check, Edit3, Loader2, Plus, Power, Search, SearchX, Trash2, X, type LucideIcon } from '@lucide/vue'
import { computed, nextTick, ref, watch } from 'vue'

import { ErrorApi } from '../api/parametros.repository'
import { useAbm } from '../composables/useAbm'
import { useAviso } from '../composables/useAviso'
import type { ColumnaAbm, ConfigAbm, Provincia, RegistroAbm } from '../types'
import AvisoFlotante from './AvisoFlotante.vue'

const props = defineProps<{
  config: ConfigAbm
  icono: LucideIcon
  /** Provincias para el filtro y el formulario (solo Ciudades). */
  provincias?: Provincia[]
  /** Muestra el filtro por provincia y recarga el listado al cambiarlo (solo Ciudades). */
  filtroProvincia?: boolean
}>()

const emit = defineEmits<{ total: [cantidad: number] }>()

/** Provincia elegida en el filtro de Ciudades. */
const provinciaId = defineModel<string>('provinciaId', { default: '' })

const parametros = computed(() =>
  props.filtroProvincia && provinciaId.value ? `provincia_id=${encodeURIComponent(provinciaId.value)}` : '',
)
const { listado, crear, actualizar, desactivar, eliminar } = useAbm(props.config.ruta, parametros)
const { mensaje, tipo, notificar } = useAviso()

const filas = computed(() => listado.data.value ?? [])
// Solo la primera carga de cada listado muestra el spinner: al refrescar después de guardar, activar o dar de baja, la
// tabla queda a la vista y se actualiza en el lugar, como en la pantalla anterior.
const cargando = computed(() => listado.isPending.value)

watch(
  () => filas.value.length,
  (cantidad) => emit('total', cantidad),
  { immediate: true },
)

watch(
  () => listado.error.value,
  (error) => {
    if (error) notificar(textoDeError(error, props.config.errorCargar), 'error')
  },
)

const filtro = ref('')
const filtradas = computed(() => {
  const consulta = filtro.value.trim().toLowerCase()
  if (!consulta) return filas.value
  return filas.value.filter((registro) =>
    props.config.camposBusqueda.some((clave) => textoDe(registro, clave).toLowerCase().includes(consulta)),
  )
})

const hayFiltros = computed(() => Boolean(filtro.value.trim()) || Boolean(props.filtroProvincia && provinciaId.value))
const sinProvincias = computed(() => (props.provincias?.length ?? 0) === 0)

function textoDe(registro: RegistroAbm, clave: string): string {
  const valor = registro[clave]
  return valor === null || valor === undefined ? '' : String(valor)
}

function numeroDe(registro: RegistroAbm, clave: string): number {
  const valor = registro[clave]
  return typeof valor === 'number' ? valor : Number(valor ?? 0)
}

function activoDe(registro: RegistroAbm): boolean {
  return Boolean(registro.activo)
}

function idDe(registro: RegistroAbm): string | number | null {
  const valor = registro[props.config.claveId]
  return typeof valor === 'string' || typeof valor === 'number' ? valor : null
}

function claseAlineacion(columna: ColumnaAbm): string {
  if (columna.alineacion === 'centro') return 'text-center'
  if (columna.alineacion === 'derecha') return 'text-right'
  return ''
}

/** Texto del chip vacío. Con `vacio` propio (Ciudades: «—») el chip conserva su estilo, como en la pantalla anterior. */
function vacioDe(columna: ColumnaAbm): string {
  return columna.vacio ?? 'Sin categoría'
}

function textoDeError(error: unknown, porDefecto: string): string {
  if (error instanceof ErrorApi) {
    return error.estado === 0 ? porDefecto : error.message
  }
  if (error instanceof Error && error.message) return error.message
  return porDefecto
}

function errorDeFormulario(error: unknown): string {
  return textoDeError(error, props.config.errorConexion ?? 'Error de conexión con el servidor.')
}

/** Error de las acciones de la tabla (estado y baja): sin conexión, la pantalla anterior decía «Error de conexión.». */
function errorDeAccion(error: unknown): string {
  return textoDeError(error, 'Error de conexión.')
}

// ---- Alta y edición -----------------------------------------------------------------------------------------------

const modalAbierto = ref(false)
const esEdicion = ref(false)
const guardando = ref(false)
const errorForm = ref('')
const idEdicion = ref<string | number | null>(null)
const formulario = ref<Record<string, string | number | null>>({})
const contenidoModal = ref<HTMLElement | null>(null)

/** Como la pantalla anterior, al abrir el modal el cursor queda en el primer campo de texto (el nombre). */
function enfocarPrimerCampo(): void {
  void nextTick(() => contenidoModal.value?.querySelector<HTMLInputElement>('input[type="text"]')?.focus())
}

const opcionesProvincia = computed(() =>
  (props.provincias ?? []).map((provincia) => ({ valor: provincia.provincia_id, texto: provincia.nombre })),
)

function abrirNuevo(): void {
  if (props.filtroProvincia && sinProvincias.value) return
  esEdicion.value = false
  idEdicion.value = null
  errorForm.value = ''
  const valores: Record<string, string | number | null> = {}
  for (const campo of props.config.campos) {
    if (campo.tipo === 'select') {
      valores[campo.clave] = provinciaId.value ? Number(provinciaId.value) : (props.provincias?.[0]?.provincia_id ?? '')
    } else {
      valores[campo.clave] = ''
    }
  }
  formulario.value = valores
  modalAbierto.value = true
  enfocarPrimerCampo()
}

function abrirEditar(registro: RegistroAbm): void {
  esEdicion.value = true
  idEdicion.value = idDe(registro)
  errorForm.value = ''
  const valores: Record<string, string | number | null> = {}
  for (const campo of props.config.campos) {
    const valor = registro[campo.clave]
    valores[campo.clave] = typeof valor === 'string' || typeof valor === 'number' ? valor : ''
  }
  formulario.value = valores
  modalAbierto.value = true
  enfocarPrimerCampo()
}

/** Escape, el fondo y la X cierran siempre, aun guardando (como antes); el botón Cancelar se deshabilita al guardar. */
function cerrarModal(): void {
  modalAbierto.value = false
}

async function guardar(): Promise<void> {
  if (guardando.value) return
  const falta = props.config.campos.some(
    (campo) => campo.requerido && campo.tipo !== 'select' && !String(formulario.value[campo.clave] ?? '').trim(),
  )
  if (falta) {
    errorForm.value = props.config.errorRequerido
    return
  }
  const faltaSeleccion = props.config.campos.some(
    (campo) => campo.requerido && campo.tipo === 'select' && String(formulario.value[campo.clave] ?? '').trim() === '',
  )
  if (faltaSeleccion) {
    errorForm.value = props.config.errorRequeridoSelect ?? props.config.errorRequerido
    return
  }

  const datos: Record<string, unknown> = {}
  for (const campo of props.config.campos) {
    if (campo.tipo === 'select') {
      datos[campo.clave] = Number(formulario.value[campo.clave])
    } else {
      const limpio = String(formulario.value[campo.clave] ?? '').trim()
      datos[campo.clave] = limpio === '' && campo.clave === 'categoria' ? null : limpio
    }
  }
  if (!esEdicion.value && props.config.baja === 'logica') datos.activo = true

  guardando.value = true
  errorForm.value = ''
  try {
    if (esEdicion.value && idEdicion.value !== null) {
      await actualizar.mutateAsync({ id: idEdicion.value, datos })
      notificar(props.config.textoActualizado)
    } else {
      await crear.mutateAsync(datos)
      notificar(props.config.textoCreado)
    }
    modalAbierto.value = false
  } catch (error) {
    errorForm.value = errorDeFormulario(error)
  } finally {
    guardando.value = false
  }
}

// ---- Estado y baja ------------------------------------------------------------------------------------------------

async function cambiarEstado(registro: RegistroAbm): Promise<void> {
  const nuevoEstado = !activoDe(registro)
  const id = idDe(registro)
  if (id === null) return
  try {
    await actualizar.mutateAsync({ id, datos: { activo: nuevoEstado } })
    notificar(props.config.textoEstado?.(registro, nuevoEstado) ?? 'Estado actualizado.')
  } catch (error) {
    notificar(errorDeAccion(error), 'error')
  }
}

async function darDeBaja(registro: RegistroAbm): Promise<void> {
  if (!window.confirm(props.config.textoBaja(registro))) return
  const id = idDe(registro)
  if (id === null) return
  try {
    if (props.config.baja === 'logica') {
      await desactivar.mutateAsync(id)
    } else {
      await eliminar.mutateAsync(id)
    }
    notificar(props.config.textoBajaExitosa(registro))
  } catch (error) {
    notificar(errorDeAccion(error), 'error')
  }
}
</script>

<template>
  <AvisoFlotante :mensaje="mensaje" :tipo="tipo" />

  <div class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
    <div
      class="flex flex-col gap-4 border-b border-dark-100 p-6"
      :class="
        filtroProvincia
          ? 'lg:flex-row lg:items-center lg:justify-between'
          : 'md:flex-row md:items-center md:justify-between'
      "
    >
      <div class="flex items-center gap-3">
        <span class="rounded-xl bg-primary-50 p-2.5 text-primary-600">
          <component :is="icono" class="h-5 w-5" />
        </span>
        <div>
          <h2 class="text-base font-bold text-dark-900">{{ config.titulo }}</h2>
          <p class="mt-0.5 text-xs text-dark-400">{{ config.subtitulo }}</p>
        </div>
      </div>

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <!-- Ciudades: el filtro por provincia va antes del buscador, como en la pantalla anterior -->
        <select
          v-if="filtroProvincia"
          v-model="provinciaId"
          class="w-full rounded-xl border border-dark-200 bg-white px-3 py-2 text-xs focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none sm:w-52"
          aria-label="Filtrar por provincia"
        >
          <option value="">Todas las provincias</option>
          <option v-for="provincia in provincias" :key="provincia.provincia_id" :value="String(provincia.provincia_id)">
            {{ provincia.nombre }}
          </option>
        </select>

        <div v-if="config.buscarPlaceholder" class="relative w-full" :class="config.buscadorAncho ?? 'sm:w-64'">
          <Search class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-dark-400" />
          <input
            v-model="filtro"
            type="text"
            :placeholder="config.buscarPlaceholder"
            class="w-full rounded-xl border border-dark-200 bg-white py-2 pr-8 pl-9 text-xs focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
          />
          <button
            v-if="filtro"
            type="button"
            class="absolute top-1/2 right-2.5 -translate-y-1/2 text-dark-400 hover:text-dark-600 focus:outline-none"
            aria-label="Limpiar búsqueda"
            @click="filtro = ''"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>

        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-xs font-semibold whitespace-nowrap text-white shadow-soft transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="filtroProvincia && sinProvincias"
          @click="abrirNuevo"
        >
          <Plus class="h-4 w-4" />
          <span>{{ config.nuevo }}</span>
        </button>
      </div>
    </div>

    <div class="overflow-x-auto">
      <table class="w-full border-collapse text-left">
        <thead>
          <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold tracking-wider text-dark-500 uppercase">
            <th
              v-for="columna in config.columnas"
              :key="columna.clave"
              class="px-6 py-3.5 whitespace-nowrap"
              :class="claseAlineacion(columna)"
            >
              {{ columna.etiqueta }}
            </th>
            <th class="px-6 py-3.5 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-dark-100 text-sm">
          <tr v-if="cargando">
            <td :colspan="config.columnas.length + 1" class="px-6 py-12 text-center text-dark-400">
              <div class="inline-flex items-center gap-2 text-xs">
                <Loader2 class="h-4 w-4 animate-spin text-primary-600" />
                <span>{{ config.cargando }}</span>
              </div>
            </td>
          </tr>

          <template v-else-if="filtradas.length > 0">
            <tr v-for="registro in filtradas" :key="String(idDe(registro))" class="transition-colors hover:bg-dark-50/50">
              <td
                v-for="(columna, indice) in config.columnas"
                :key="columna.clave"
                class="px-6 py-3.5"
                :class="[
                  claseAlineacion(columna),
                  indice === 0 ? 'font-semibold text-dark-800' : 'text-dark-600',
                  columna.tipo === 'chip' ? 'text-xs' : '',
                ]"
              >
                <template v-if="columna.tipo === 'estado'">
                  <button
                    type="button"
                    class="inline-flex cursor-pointer items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-colors"
                    :class="
                      activoDe(registro)
                        ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                        : 'bg-dark-100 text-dark-500 hover:bg-dark-200'
                    "
                    :title="activoDe(registro) ? 'Click para desactivar' : 'Click para activar'"
                    @click="cambiarEstado(registro)"
                  >
                    <span class="h-1.5 w-1.5 rounded-full" :class="activoDe(registro) ? 'bg-emerald-500' : 'bg-dark-400'" />
                    <span>{{ activoDe(registro) ? 'Activo' : 'Inactivo' }}</span>
                  </button>
                </template>

                <template v-else-if="columna.tipo === 'chip'">
                  <span
                    class="inline-flex items-center rounded-md px-2.5 py-0.5 font-medium"
                    :class="
                      textoDe(registro, columna.clave) || columna.vacio !== undefined
                        ? 'bg-dark-100 text-dark-700'
                        : 'text-dark-400 italic'
                    "
                  >
                    {{ textoDe(registro, columna.clave) || vacioDe(columna) }}
                  </span>
                </template>

                <template v-else-if="columna.tipo === 'contador'">
                  {{ numeroDe(registro, columna.clave) }}
                </template>

                <template v-else>{{ textoDe(registro, columna.clave) }}</template>
              </td>

              <td class="space-x-1.5 px-6 py-3.5 text-right whitespace-nowrap">
                <button
                  type="button"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-lg bg-primary-50 px-2.5 py-1 text-xs font-medium text-primary-600 transition-colors hover:bg-primary-100"
                  :title="config.tituloBotonEditar ?? 'Editar'"
                  @click="abrirEditar(registro)"
                >
                  <Edit3 class="h-3.5 w-3.5" />
                  <span>Editar</span>
                </button>
                <button
                  v-if="config.baja === 'logica' ? activoDe(registro) : true"
                  type="button"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors"
                  :class="
                    config.baja === 'logica'
                      ? 'bg-amber-50 text-amber-700 hover:bg-amber-100'
                      : 'bg-rose-50 text-rose-700 hover:bg-rose-100'
                  "
                  :title="config.baja === 'logica' ? 'Desactivar (Baja lógica)' : (config.tituloBotonEliminar ?? 'Eliminar')"
                  @click="darDeBaja(registro)"
                >
                  <Power v-if="config.baja === 'logica'" class="h-3.5 w-3.5" />
                  <Trash2 v-else class="h-3.5 w-3.5" />
                  <span>{{ config.baja === 'logica' ? 'Desactivar' : 'Eliminar' }}</span>
                </button>
              </td>
            </tr>
          </template>

          <tr v-else>
            <td :colspan="config.columnas.length + 1" class="px-6 py-10 text-center">
              <p v-if="config.vacioSimple" class="text-xs text-dark-400">{{ config.vacioSinFiltro }}</p>
              <template v-else-if="config.vacioSinIcono">
                <p class="text-sm font-semibold text-dark-800">{{ config.vacioTitulo }}</p>
                <p class="mt-0.5 text-xs text-dark-400">{{ hayFiltros ? config.vacioConFiltro : config.vacioSinFiltro }}</p>
              </template>
              <div v-else class="mx-auto flex max-w-sm flex-col items-center justify-center">
                <div class="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-dark-100 text-dark-400">
                  <SearchX class="h-5 w-5" />
                </div>
                <p class="text-sm font-semibold text-dark-800">{{ config.vacioTitulo }}</p>
                <p class="mt-0.5 text-xs text-dark-400">
                  {{ hayFiltros ? config.vacioConFiltro : config.vacioSinFiltro }}
                </p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Alta / edición -->
  <div
    v-if="modalAbierto"
    class="fixed inset-0 z-50 overflow-y-auto"
    role="dialog"
    aria-modal="true"
    @keydown.escape.window="cerrarModal"
  >
    <div class="fixed inset-0 bg-dark-900/40 backdrop-blur-sm transition-opacity" @click="cerrarModal" />

    <div class="flex min-h-full items-center justify-center p-4 text-center">
      <div
        ref="contenidoModal"
        class="relative w-full max-w-md transform overflow-hidden rounded-2xl border border-dark-100 bg-white p-6 text-left shadow-2xl transition-all"
        @click.stop
      >
        <div class="flex items-center justify-between border-b border-dark-100 pb-4">
          <div class="flex items-center gap-2.5">
            <span class="rounded-xl bg-primary-50 p-2 text-primary-600">
              <component :is="icono" class="h-5 w-5" />
            </span>
            <h3 class="text-base font-bold text-dark-900">{{ esEdicion ? config.tituloEditar : config.tituloCrear }}</h3>
          </div>
          <button
            type="button"
            class="rounded-lg p-1 text-dark-400 transition-colors hover:bg-dark-100 hover:text-dark-600 focus:outline-none"
            aria-label="Cerrar"
            @click="cerrarModal"
          >
            <X class="h-5 w-5" />
          </button>
        </div>

        <form class="space-y-4 pt-4" @submit.prevent="guardar">
          <div
            v-if="errorForm"
            class="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700"
          >
            <AlertCircle class="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>{{ errorForm }}</span>
          </div>

          <div v-for="campo in config.campos" :key="campo.clave">
            <label class="mb-1 block text-xs font-semibold text-dark-700">
              {{ campo.etiqueta }} <span v-if="campo.requerido" class="text-rose-500">*</span>
            </label>

            <select
              v-if="campo.tipo === 'select'"
              v-model="formulario[campo.clave]"
              class="w-full rounded-xl border border-dark-200 bg-white px-3.5 py-2 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
            >
              <option value="" disabled>Seleccioná una provincia</option>
              <option v-for="opcion in opcionesProvincia" :key="opcion.valor" :value="opcion.valor">{{ opcion.texto }}</option>
            </select>

            <template v-else>
              <input
                v-model="formulario[campo.clave]"
                type="text"
                :required="campo.requerido"
                :maxlength="campo.maxlength"
                :placeholder="campo.placeholder"
                :list="campo.datalist ? `abm-${config.ruta}-${campo.clave}` : undefined"
                class="w-full rounded-xl border border-dark-200 px-3.5 py-2 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
              />
              <datalist v-if="campo.datalist" :id="`abm-${config.ruta}-${campo.clave}`">
                <option v-for="opcion in campo.datalist" :key="opcion" :value="opcion" />
              </datalist>
            </template>

            <p v-if="campo.ayuda" class="mt-1 text-[11px] text-dark-400">{{ campo.ayuda }}</p>
          </div>

          <div class="flex justify-end gap-2.5 border-t border-dark-100 pt-4">
            <button
              type="button"
              :disabled="guardando"
              class="cursor-pointer rounded-xl px-4 py-2 text-xs font-semibold text-dark-600 transition-colors hover:bg-dark-100"
              @click="cerrarModal"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="guardando"
              class="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-5 py-2 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-primary-700 disabled:opacity-50"
            >
              <Check v-if="!guardando" class="h-4 w-4" />
              <Loader2 v-else class="h-4 w-4 animate-spin" />
              <span>{{ guardando ? 'Guardando...' : esEdicion ? 'Guardar Cambios' : config.botonCrear }}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>
