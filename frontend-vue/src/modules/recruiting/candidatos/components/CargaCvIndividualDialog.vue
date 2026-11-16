<script setup lang="ts">
import { AlertCircle, Cpu, ExternalLink, FileCheck, FileUp, FileX, Files, Loader2, Sparkles, Trash2, UploadCloud, X } from '@lucide/vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { onBeforeUnmount, ref, watch } from 'vue'
import { CLASE_BOTON_CANCELAR, CLASE_BOTON_PRIMARIO, PT_DIALOGO } from '../estilos'

import { previsualizarWord, urlCv } from '../api/candidatos.repository'
import { useCargaCv } from '../composables/useCargaCv'
import { errorArchivoIndividual, extension, mensajeEmailExistente } from '../cv'
import { tamanoLegible } from '../../candidato-nuevo/validacion'
import type { ComparacionCv } from '../types'

/**
 * Carga individual de un CV: el sistema extrae los datos y crea el candidato. Si el email ya existe con otro CV
 * se abre la comparación (CV actual contra CV nuevo) para elegir con cuál quedarse.
 */
const visible = defineModel<boolean>({ required: true })

const toast = useToast()
const carga = useCargaCv()

const entrada = ref<HTMLInputElement | null>(null)
const arrastrando = ref(false)
const archivo = ref<File | null>(null)
const error = ref('')
const comparacion = ref<ComparacionCv | null>(null)

interface Visor {
  /** Dirección que se muestra en el iframe ('' si no hay vista previa). */
  url: string
  descarga: string
  nombre: string
  cargando: boolean
  /** URL de objeto creada para la vista previa (se libera al cerrar). */
  blob: string
}
const visores = ref<{ actual: Visor; nuevo: Visor } | null>(null)

const esPdf = (nombre: string) => extension(nombre) === 'pdf'
const esWord = (nombre: string) => ['doc', 'docx'].includes(extension(nombre))

function liberarVisores(): void {
  const v = visores.value
  if (v) {
    if (v.nuevo.descarga.startsWith('blob:')) URL.revokeObjectURL(v.nuevo.descarga)
    for (const visor of [v.actual, v.nuevo]) if (visor.blob) URL.revokeObjectURL(visor.blob)
  }
  visores.value = null
}
onBeforeUnmount(liberarVisores)

function quitarArchivo(): void {
  archivo.value = null
  if (entrada.value) entrada.value.value = ''
}

// Al abrir se parte de cero, salvo al volver de una actualización fallida (se conservan el archivo y el motivo).
let reabriendo = false
watch(visible, (abierto) => {
  if (abierto && !reabriendo) {
    error.value = ''
    quitarArchivo()
  }
  reabriendo = false
})

function elegir(nuevo: File | undefined): void {
  error.value = ''
  if (!nuevo) return
  const problema = errorArchivoIndividual(nuevo)
  if (problema) {
    error.value = problema
    quitarArchivo()
    return
  }
  archivo.value = nuevo
}

const cerrar = () => {
  if (!carga.isPending.value) visible.value = false
}

/** Vista previa de los dos CV: PDF directo; Word convertido a PDF por el backend (si falla, queda la descarga). */
function prepararVisores(nuevo: File, actual: ComparacionCv['actual']): void {
  liberarVisores()
  const clave = actual.cv_url ?? ''
  const urlActual = clave ? urlCv(clave) : ''
  const urlNuevo = URL.createObjectURL(nuevo)
  const vista = {
    actual: { url: esPdf(clave) ? urlActual : '', descarga: urlActual, nombre: actual.archivo ?? '', cargando: esWord(clave), blob: '' },
    nuevo: { url: esPdf(nuevo.name) ? urlNuevo : '', descarga: urlNuevo, nombre: nuevo.name, cargando: esWord(nuevo.name), blob: '' },
  }
  visores.value = vista
  const convertir = async (columna: 'actual' | 'nuevo', origen: { clave: string } | { archivo: File }) => {
    const blob = (await previsualizarWord(origen)) ?? ''
    if (visores.value !== vista) {
      if (blob) URL.revokeObjectURL(blob)
      return
    }
    vista[columna].blob = blob
    vista[columna].url = blob
    vista[columna].cargando = false
  }
  if (esWord(clave)) void convertir('actual', { clave })
  if (esWord(nuevo.name)) void convertir('nuevo', { archivo: nuevo })
}

async function procesar(): Promise<void> {
  if (!archivo.value || carga.isPending.value) return
  error.value = ''
  try {
    const resultado = await carga.mutateAsync({ archivo: archivo.value, confirmar: false })
    if (resultado.tipo === 'ok') {
      toast.add({ severity: 'success', summary: 'Candidato creado y CV procesado exitosamente.', life: 5000 })
      visible.value = false
      return
    }
    comparacion.value = resultado.comparacion
    prepararVisores(archivo.value, resultado.comparacion.actual)
    visible.value = false
  } catch (e) {
    const mensaje = e instanceof Error ? e.message : 'Error al procesar el archivo'
    const estado = (e as { estado?: number }).estado ?? 0
    error.value = mensajeEmailExistente(mensaje, estado) ?? mensaje
    if (estado === 422) toast.add({ severity: 'warn', summary: mensaje, life: 8000 })
  }
}

// ---- Comparación: conservar el CV actual o actualizar la ficha con el nuevo ----
function cerrarComparacion(): void {
  if (carga.isPending.value) return
  comparacion.value = null
  liberarVisores()
  quitarArchivo()
}

async function actualizarConNuevo(): Promise<void> {
  if (!archivo.value || carga.isPending.value) return
  try {
    await carga.mutateAsync({ archivo: archivo.value, confirmar: true })
    toast.add({ severity: 'success', summary: 'Candidato actualizado con el nuevo CV.', life: 5000 })
    cerrarComparacion()
  } catch (e) {
    // Vuelve al primer diálogo con el motivo, conservando el archivo elegido.
    comparacion.value = null
    liberarVisores()
    error.value = e instanceof Error ? e.message : 'No se pudo actualizar el candidato.'
    reabriendo = true
    visible.value = true
  }
}

const columnas = [
  { titulo: 'CV actual', clave: 'actual' },
  { titulo: 'CV nuevo', clave: 'nuevo' },
] as const
</script>

<template>
  <Dialog
    :pt="PT_DIALOGO"
    :visible="visible"
    modal
    dismissable-mask
    :draggable="false"
    :closable="!carga.isPending.value"
    :close-on-escape="!carga.isPending.value"
    style="width: 32rem"
    @update:visible="(abierto: boolean) => !(!abierto && carga.isPending.value) && (visible = abierto)"
  >
    <template #header>
      <div class="flex items-center gap-2.5">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
          <FileUp class="h-5 w-5" />
        </div>
        <div>
          <h3 class="text-base font-bold text-dark-900">Carga Individual de CV</h3>
          <p class="text-xs font-normal text-dark-400">Extracción inteligente de datos y alta automática</p>
        </div>
      </div>
    </template>

    <div
      v-if="error"
      role="alert"
      data-testid="error-carga-cv"
      class="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700"
    >
      <AlertCircle class="h-4 w-4 shrink-0 text-red-600" />
      <span class="flex-1">{{ error }}</span>
      <button type="button" title="Cerrar aviso" aria-label="Cerrar aviso" class="rounded-lg p-1 text-red-400 hover:bg-red-100 hover:text-red-600" @click="error = ''">
        <X class="h-3.5 w-3.5" />
      </button>
    </div>

    <input
      ref="entrada"
      type="file"
      accept=".pdf,.doc,.docx"
      class="hidden"
      data-testid="cv-individual-input"
      @change="elegir(($event.target as HTMLInputElement).files?.[0])"
    />
    <div
      class="cursor-pointer rounded-2xl border-2 border-dashed p-6 text-center transition-colors"
      :class="arrastrando ? 'border-primary-500 bg-primary-50/30' : 'border-dark-200 bg-dark-50/40 hover:border-primary-400'"
      @dragover.prevent="arrastrando = true"
      @dragleave.prevent="arrastrando = false"
      @drop.prevent="((arrastrando = false), elegir($event.dataTransfer?.files[0]))"
      @click="entrada?.click()"
    >
      <div v-if="!archivo" class="space-y-2">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-dark-100 bg-white text-primary-600 shadow-xs">
          <UploadCloud class="h-6 w-6" />
        </div>
        <div class="text-xs text-dark-600">
          <span class="font-bold text-primary-600 hover:underline">Hacé click para buscar</span> o arrastrá el CV acá
        </div>
        <p class="text-[11px] text-dark-400">Archivos PDF, DOC o DOCX (hasta 5 MB)</p>
      </div>
      <div v-else class="flex items-center justify-between rounded-xl border border-dark-200 bg-white p-3 text-left">
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
            <FileCheck class="h-4 w-4" />
          </div>
          <div class="truncate">
            <p class="truncate text-xs font-semibold text-dark-800">{{ archivo.name }}</p>
            <p class="text-[10px] text-dark-400">{{ tamanoLegible(archivo.size) }}</p>
          </div>
        </div>
        <button type="button" aria-label="Quitar archivo" class="rounded-lg p-1 text-dark-400 hover:bg-dark-50 hover:text-red-600" @click.stop="quitarArchivo">
          <Trash2 class="h-4 w-4" />
        </button>
      </div>
    </div>

    <div class="mt-4 flex items-start gap-2 rounded-xl border border-primary-100/60 bg-primary-50/50 p-3 text-[11.5px] text-primary-800">
      <Sparkles class="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
      <span>
        El sistema analizará el archivo para identificar nombre, apellido, email, teléfono, seniority, puesto y
        habilidades, creando el candidato y vinculando su CV en la base de talentos.
      </span>
    </div>

    <template #footer>
      <Button label="Cancelar" unstyled :class="CLASE_BOTON_CANCELAR" :disabled="carga.isPending.value" @click="cerrar" />
      <Button
        unstyled
        :class="CLASE_BOTON_PRIMARIO"
        :disabled="!archivo || carga.isPending.value"
        data-testid="procesar-cv-individual"
        @click="procesar"
      >
        <Loader2 v-if="carga.isPending.value" class="h-4 w-4 animate-spin" />
        <Cpu v-else class="h-4 w-4" />
        <span>{{ carga.isPending.value ? 'Extrayendo y creando...' : 'Procesar y Guardar' }}</span>
      </Button>
    </template>
  </Dialog>

  <!-- Comparación: el candidato ya existe (mismo email) con un CV distinto -->
  <Dialog
    :pt="{ ...PT_DIALOGO, content: { class: 'flex min-h-0 flex-1 flex-col px-6 pt-4 pb-0' } }"
    :visible="comparacion !== null"
    modal
    :draggable="false"
    :closable="!carga.isPending.value"
    :close-on-escape="!carga.isPending.value"
    @update:visible="(abierto: boolean) => !abierto && cerrarComparacion()"
    style="width: min(80rem, 96vw); height: 95vh"
  >
    <template #header>
      <div class="flex items-center gap-3">
        <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-600"><Files class="h-5 w-5" /></div>
        <div>
          <h3 class="text-base font-bold text-dark-900">El candidato ya existe con otro CV</h3>
          <p class="text-xs font-normal text-dark-500">Elegí con cuál CV te querés quedar.</p>
        </div>
      </div>
    </template>
    <div v-if="visores" class="grid min-h-0 flex-1 grid-cols-1 grid-rows-2 gap-4 text-xs md:grid-cols-2 md:grid-rows-1">
      <div v-for="col in columnas" :key="col.clave" class="flex min-h-0 min-w-0 flex-col">
        <div class="mb-2 flex items-center justify-between gap-2">
          <h4 class="text-sm font-bold text-dark-900">{{ col.titulo }}</h4>
          <a
            v-if="visores[col.clave].url"
            :href="visores[col.clave].url"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-2 rounded-lg border-2 border-primary-500 bg-white px-3.5 py-1.5 text-sm font-semibold text-primary-700 hover:bg-primary-50"
          >
            <ExternalLink class="h-4 w-4" /><span>VER CV</span>
          </a>
        </div>
        <iframe
          v-if="visores[col.clave].url"
          :src="`${visores[col.clave].url}#view=FitH&navpanes=0&pagemode=none`"
          :title="col.titulo"
          class="min-h-0 w-full flex-1 rounded-xl border border-dark-100 bg-dark-50"
        ></iframe>
        <div v-else-if="visores[col.clave].cargando" class="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-dark-200 bg-dark-50 p-4 text-center text-dark-500" role="status">
          <Loader2 class="h-6 w-6 animate-spin" /><span>Generando vista previa...</span>
        </div>
        <div v-else class="flex min-h-0 w-full flex-1 flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-dark-200 bg-dark-50 p-4 text-center text-dark-500">
          <FileX class="h-6 w-6" />
          <span>Vista previa no disponible para este archivo.</span>
          <a v-if="visores[col.clave].descarga" :href="visores[col.clave].descarga" :download="visores[col.clave].nombre" target="_blank" class="font-semibold text-primary-600 hover:underline">
            Descargar {{ visores[col.clave].nombre || 'archivo' }}
          </a>
        </div>
      </div>
    </div>
    <template #footer>
      <Button label="Conservar actual" unstyled :class="CLASE_BOTON_CANCELAR" :disabled="carga.isPending.value" data-testid="conservar-cv" @click="cerrarComparacion" />
      <Button unstyled :class="CLASE_BOTON_PRIMARIO" :disabled="carga.isPending.value" data-testid="actualizar-cv" @click="actualizarConNuevo">
        <span>{{ carga.isPending.value ? 'Actualizando...' : 'Actualizar con el nuevo' }}</span>
      </Button>
    </template>
  </Dialog>
</template>
