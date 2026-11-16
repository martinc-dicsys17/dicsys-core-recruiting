<script setup lang="ts">
import { AlertCircle, Archive, ClipboardCheck, FileArchive, FileText, FolderArchive, Info, Trash2, UploadCloud } from '@lucide/vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { ref } from 'vue'
import { CLASE_BOTON_CANCELAR, CLASE_BOTON_PRIMARIO, PT_DIALOGO } from '../estilos'

import { tamanoLegible } from '../../candidato-nuevo/validacion'
import type { useCargaMasiva } from '../composables/useCargaMasiva'
import {
  cantidadIndividuales,
  categoriasResumen,
  detalleNoCreados,
  esComprimido,
  etiquetaResultado,
  MAX_CVS_INDIVIDUALES,
  textoProgreso,
  tituloProgreso,
} from '../cv'

/** Carga masiva de CV (sueltos, .zip o .rar) con su avance real, y el resumen final del lote. */
const props = defineProps<{ carga: ReturnType<typeof useCargaMasiva> }>()
const c = props.carga

const entrada = ref<HTMLInputElement | null>(null)
const arrastrando = ref(false)

function agregar(lista: FileList | null | undefined): void {
  if (lista?.length) c.agregar(Array.from(lista))
  if (entrada.value) entrada.value.value = ''
}
</script>

<template>
  <Dialog
    :pt="PT_DIALOGO"
    :visible="c.abierto.value"
    modal
    :draggable="false"
    :closable="!c.procesando.value"
    :close-on-escape="!c.procesando.value"
    style="width: 36rem"
    data-testid="modal-carga-masiva"
    @update:visible="(abierto: boolean) => !abierto && c.cerrar()"
  >
    <template #header>
      <div class="flex items-center gap-2.5">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
          <FolderArchive class="h-5 w-5" />
        </div>
        <div>
          <h3 class="text-base font-bold text-dark-900">Carga Masiva de CVs</h3>
          <p class="text-xs font-normal text-dark-400">
            Procesamiento por lote de CVs individuales o paquetes comprimidos (.ZIP o .RAR)
          </p>
        </div>
      </div>
    </template>

    <div v-if="c.error.value" role="alert" data-testid="error-carga-masiva" class="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
      <AlertCircle class="h-4 w-4 shrink-0 text-red-600" /><span>{{ c.error.value }}</span>
    </div>

    <input ref="entrada" type="file" multiple accept=".pdf,.doc,.docx,.zip,.rar" class="hidden" data-testid="cv-masivo-input" @change="agregar(($event.target as HTMLInputElement).files)" />
    <div
      v-show="!c.procesando.value"
      class="cursor-pointer rounded-2xl border-2 border-dashed p-6 text-center transition-colors"
      :class="arrastrando ? 'border-primary-500 bg-primary-50/30' : 'border-dark-200 bg-dark-50/40 hover:border-primary-400'"
      @dragover.prevent="arrastrando = true"
      @dragleave.prevent="arrastrando = false"
      @drop.prevent="((arrastrando = false), agregar($event.dataTransfer?.files))"
      @click="entrada?.click()"
    >
      <div class="space-y-2" :class="c.archivos.value.length ? 'mb-3' : ''">
        <div v-if="!c.archivos.value.length" class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-dark-100 bg-white text-primary-600 shadow-xs">
          <Archive class="h-6 w-6" />
        </div>
        <div class="text-xs text-dark-600">
          <span class="font-bold text-primary-600 hover:underline">Hacé click para buscar</span> o arrastrá CVs
          individuales o paquetes ZIP/RAR acá
        </div>
        <p class="text-[11px] text-dark-400">
          CVs en PDF, DOC o DOCX (hasta 100 CVs individuales) o archivos comprimidos .ZIP / .RAR (hasta 500 MB)
        </p>
      </div>
      <div v-if="c.archivos.value.length" class="custom-scrollbar max-h-48 space-y-1.5 overflow-y-auto pr-1" data-testid="lista-archivos-masivo">
        <p class="text-left text-[11px] font-semibold text-dark-600">
          {{ c.archivos.value.length }} archivo(s) seleccionado(s) - CVs individuales:
          {{ cantidadIndividuales(c.archivos.value) }} de {{ MAX_CVS_INDIVIDUALES }}
        </p>
        <div v-for="(f, i) in c.archivos.value" :key="`${i}|${f.name}`" class="flex items-center justify-between rounded-xl border border-dark-200 bg-white p-2 text-left">
          <div class="flex min-w-0 items-center gap-3">
            <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
              <FileArchive v-if="esComprimido(f)" class="h-4 w-4" /><FileText v-else class="h-4 w-4" />
            </div>
            <div class="truncate">
              <p class="truncate text-xs font-semibold text-dark-800">{{ f.name }}</p>
              <p class="text-[10px] text-dark-400">{{ tamanoLegible(f.size) }}</p>
            </div>
          </div>
          <button type="button" aria-label="Quitar archivo" class="rounded-lg p-1 text-dark-400 hover:bg-dark-50 hover:text-red-600" @click.stop="c.quitar(i)">
            <Trash2 class="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>

    <p class="mt-2 text-center text-[11px] text-dark-400" data-testid="info-limite-masivo">Máximo 100 CVs individuales por carga.</p>

    <!-- Avance real del lote: procesados / total informado por el backend -->
    <div v-if="c.procesando.value || c.estado.value === 'cancelado'" data-testid="progreso-carga-masiva" class="mt-3 space-y-3 rounded-2xl border border-primary-100 bg-primary-50/40 p-4">
      <div class="flex items-center justify-between gap-3">
        <p class="text-sm font-bold text-dark-800" data-testid="titulo-progreso-masivo">{{ tituloProgreso(c.estado.value, c.cancelando.value) }}</p>
        <span class="text-sm font-bold text-primary-700 tabular-nums" data-testid="porcentaje-carga-masiva">{{ c.porcentaje.value }}%</span>
      </div>
      <div class="h-3 w-full overflow-hidden rounded-full bg-dark-100" role="progressbar" aria-label="Progreso de la carga masiva" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="c.porcentaje.value">
        <div class="h-full rounded-full transition-[width] duration-300 ease-out motion-reduce:transition-none" :class="c.estado.value === 'cancelado' ? 'bg-dark-400' : 'bg-primary-600'" :style="{ width: `${c.porcentaje.value}%` }"></div>
      </div>
      <p class="text-xs text-dark-500" data-testid="texto-progreso-carga-masiva">
        {{ textoProgreso(c.estado.value, c.progreso.value.procesados, c.progreso.value.total) }}
      </p>
    </div>

    <!-- Aviso discreto: la selección superaba los 100 CVs individuales (no es un error de procesamiento) -->
    <p v-if="!c.procesando.value && c.advertenciaLimite.value" class="mt-3 text-xs text-red-600" data-testid="advertencia-limite-masivo">
      {{ c.advertenciaLimite.value }}
    </p>

    <div class="mt-4 flex items-start gap-2 rounded-xl border border-primary-100/60 bg-primary-50/50 p-3 text-[11.5px] text-primary-800">
      <Info class="mt-0.5 h-4 w-4 shrink-0 text-primary-600" />
      <span>
        El sistema ignorará carpetas del sistema y procesará cada CV de forma aislada. Si algún archivo contiene
        errores o formato no legible, se reportará sin interrumpir el resto.
      </span>
    </div>

    <template #footer>
      <Button
        :label="c.cancelando.value ? 'Cancelando...' : 'Cancelar'"
        unstyled
        :class="CLASE_BOTON_CANCELAR"
        :disabled="c.cancelando.value"
        data-testid="cancelar-carga-masiva"
        @click="c.procesando.value ? c.cancelar() : c.cerrar()"
      />
      <Button unstyled :class="CLASE_BOTON_PRIMARIO" :disabled="!c.archivos.value.length || c.procesando.value" data-testid="iniciar-carga-masiva" @click="c.iniciar()">
        <UploadCloud v-if="!c.procesando.value" class="h-4 w-4" />
        <span>Iniciar Carga Masiva</span>
      </Button>
    </template>
  </Dialog>

  <!-- Resultados: se muestran una sola vez, al terminar todo el lote -->
  <Dialog
    :pt="PT_DIALOGO"
    :visible="c.resumenAbierto.value"
    modal
    :draggable="false"
    :closable="false"
    :close-on-escape="false"
    style="width: 36rem"
    data-testid="modal-resumen-carga-masiva"
  >
    <template #header>
      <div class="flex items-center gap-2.5">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
          <ClipboardCheck class="h-5 w-5" />
        </div>
        <div>
          <h3 class="text-base font-bold text-dark-900">Carga masiva finalizada</h3>
          <p v-if="c.reporteFinal.value?.resumen" class="text-xs font-normal text-dark-400" data-testid="resumen-masivo-total">
            Total de archivos recibidos: {{ c.reporteFinal.value.resumen.total_archivos }}
          </p>
        </div>
      </div>
    </template>

    <div class="space-y-1.5" data-testid="resumen-masivo-categorias">
      <div
        v-for="cat in categoriasResumen(c.reporteFinal.value)"
        :key="cat.clave"
        class="flex items-center justify-between rounded-xl border px-3 py-2 text-xs font-semibold"
        :class="cat.clase"
        :data-testid="`resumen-masivo-${cat.clave}`"
      >
        <span class="flex flex-col">
          <span>{{ cat.etiqueta }}</span>
          <span v-if="cat.ayuda" class="text-[10px] font-normal opacity-80">{{ cat.ayuda }}</span>
        </span>
        <span class="text-sm font-bold">{{ cat.valor }}</span>
      </div>
    </div>

    <div v-if="detalleNoCreados(c.reporteFinal.value).length" class="mt-4 border-t border-dark-100 pt-3">
      <p class="mb-1.5 text-[11px] font-semibold text-dark-700">
        Archivos que no generaron un candidato nuevo ({{ detalleNoCreados(c.reporteFinal.value).length }}):
      </p>
      <div class="custom-scrollbar max-h-44 space-y-1 overflow-y-auto pr-1" data-testid="resumen-masivo-detalle">
        <div v-for="(item, i) in detalleNoCreados(c.reporteFinal.value)" :key="i" class="flex flex-col gap-0.5 rounded-lg border border-dark-100 bg-dark-50 p-1.5 text-[10.5px] text-dark-700">
          <span class="font-semibold break-all">{{ item.archivo }}</span>
          <span class="text-[10px] text-dark-500">{{ etiquetaResultado(item.resultado) }}: {{ item.mensaje }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <Button label="Aceptar" unstyled :class="CLASE_BOTON_PRIMARIO" data-testid="resumen-masivo-aceptar" @click="c.aceptarResumen()" />
    </template>
  </Dialog>
</template>
