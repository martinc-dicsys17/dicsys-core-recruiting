<script setup lang="ts">
import {
  AlertTriangle,
  Archive,
  CheckCircle,
  DatabaseBackup,
  DatabaseZap,
  Download,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  Search,
  Trash2,
} from '@lucide/vue'
import { useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref, watch } from 'vue'

import { useSessionStore } from '@/core/stores/session'

import { ErrorApi, parametrosRepository } from './api/parametros.repository'
import AvisoFlotante from './components/AvisoFlotante.vue'
import ParametrosLayout from './components/ParametrosLayout.vue'
import { useCarpetasCv, useDetalleCarpeta } from './composables/useArchivos'
import { useAviso } from './composables/useAviso'
import {
  etiquetaArchivo,
  etiquetaRegistro,
  formatearFechaHora,
  metaCarpeta,
} from './presentacion'
import type { BackupEstado, ImportacionEstado, LimpiezaResumen } from './types'

const POR_PAGINA = 20

const sesion = useSessionStore()
const cliente = useQueryClient()
const { mensaje, tipo, notificar } = useAviso()

// ---- Carpetas y archivos ------------------------------------------------------------------------------------------

const resumen = useCarpetasCv()
const carpetas = computed(() => (resumen.data.value ?? []).filter((carpeta) => carpeta.carpeta !== 'cv_duplicados'))
const cargandoResumen = computed(() => resumen.isPending.value || resumen.isFetching.value)
const errorResumen = computed(() =>
  resumen.error.value
    ? mensajeError(
        resumen.error.value,
        'Error de conexión al consultar las carpetas de CV.',
        'No se pudieron consultar las carpetas de CV.',
      )
    : '',
)

const seleccionada = ref<string | null>(null)
const filtro = ref('')
const busqueda = ref('')
const pagina = ref(1)
let temporizadorBusqueda: number | undefined

watch(
  carpetas,
  (lista) => {
    if (!seleccionada.value && lista.length > 0) seleccionada.value = lista[0]!.carpeta
  },
  { immediate: true },
)

const parametros = computed(() => {
  const valores = new URLSearchParams({ pagina: String(pagina.value), por_pagina: String(POR_PAGINA) })
  if (busqueda.value.trim()) valores.set('buscar', busqueda.value.trim())
  return valores.toString()
})

const consultaDetalle = useDetalleCarpeta(seleccionada, parametros)
const detalle = computed(() => {
  const datos = consultaDetalle.data.value
  return datos && datos.carpeta === seleccionada.value ? datos : null
})
const cargandoDetalle = computed(() => consultaDetalle.isFetching.value)
const errorDetalle = computed(() =>
  consultaDetalle.error.value
    ? mensajeError(
        consultaDetalle.error.value,
        'Error de conexión al consultar la carpeta.',
        'No se pudo consultar el contenido de la carpeta.',
      )
    : '',
)

const archivos = computed(() => detalle.value?.archivos ?? [])
const totalPaginas = computed(() => detalle.value?.total_paginas ?? 1)
const totalFiltrado = computed(() => detalle.value?.total_filtrado ?? 0)
const desde = computed(() => (totalFiltrado.value === 0 ? 0 : (pagina.value - 1) * POR_PAGINA + 1))
const hasta = computed(() => Math.min(pagina.value * POR_PAGINA, totalFiltrado.value))
const esCarpetaErrores = computed(() => seleccionada.value === 'cv_errores')
const columnas = computed(() => (esCarpetaErrores.value ? 5 : 4))

function mensajeError(error: unknown, conexion: string, porDefecto: string): string {
  if (error instanceof ErrorApi) {
    return error.estado === 0 ? conexion : error.message
  }
  if (error instanceof Error && error.message) return error.message
  return porDefecto
}

function seleccionar(carpeta: string): void {
  seleccionada.value = carpeta
  filtro.value = ''
  busqueda.value = ''
  pagina.value = 1
}

function buscar(): void {
  window.clearTimeout(temporizadorBusqueda)
  temporizadorBusqueda = window.setTimeout(() => {
    busqueda.value = filtro.value
    pagina.value = 1
  }, 300)
}

function irAPagina(nueva: number): void {
  if (nueva < 1 || nueva > totalPaginas.value || nueva === pagina.value || cargandoDetalle.value) return
  pagina.value = nueva
}

function urlDescarga(nombre: string): string {
  return parametrosRepository.archivos.urlDescargar(seleccionada.value ?? '', nombre)
}

function urlDescargaTodos(): string {
  return parametrosRepository.archivos.urlDescargarTodos(seleccionada.value ?? '')
}

function avisarDescarga(nombre: string): void {
  notificar(`Descargando «${nombre}» de ${seleccionada.value}.`, 'exito', 4000)
}

function avisarDescargaTodos(): void {
  const datos = detalle.value
  if (!datos) return
  notificar(
    `Descargando todos los CV de ${seleccionada.value} en un ZIP (${datos.cantidad_archivos} archivo${datos.cantidad_archivos === 1 ? '' : 's'}, ${datos.tamano_total}).`,
    'exito',
    4000,
  )
}

// ---- Backup (solo administradores; el backend valida el usuario) ---------------------------------------------------

const modalBackup = ref(false)
const backup = ref<BackupEstado | null>(null)
const backupIniciando = ref(false)
const errorBackup = ref('')
let temporizadorBackup: number | undefined
let fallosBackup = 0

const FASES_BACKUP: Record<string, string> = {
  base_de_datos: 'Exportando la base de datos',
  archivos: 'Copiando los CV',
  verificando: 'Verificando la integridad',
}

const backupEnCurso = computed(
  () => Boolean(backup.value && ['preparando', 'generando', 'verificando'].includes(backup.value.estado)),
)
const backupFinalizado = computed(() => backup.value?.estado === 'finalizado')
const backupConError = computed(() => backup.value?.estado === 'error')
const porcentajeBackup = computed(() => Math.max(0, Math.min(100, backup.value?.porcentaje ?? 0)))
const urlDescargaBackup = computed(() =>
  backup.value ? parametrosRepository.archivos.descargarBackup(backup.value.backup_id) : '#',
)
const tituloBackup = computed(() => {
  if (!backup.value) return 'Backup de Recruiting'
  if (backupFinalizado.value) return 'Backup completado'
  if (backupConError.value) return 'No se pudo generar el backup'
  return (backup.value.fase ? FASES_BACKUP[backup.value.fase] : undefined) ?? 'Preparando el backup'
})

function abrirBackup(): void {
  errorBackup.value = ''
  if (backupConError.value) backup.value = null
  modalBackup.value = true
}

function cerrarBackup(): void {
  modalBackup.value = false
}

function seguirBackup(): void {
  window.clearTimeout(temporizadorBackup)
  temporizadorBackup = window.setTimeout(() => void consultarBackup(), 1000)
}

async function iniciarBackup(): Promise<void> {
  if (backupIniciando.value || backupEnCurso.value) return
  backupIniciando.value = true
  errorBackup.value = ''
  backup.value = null
  try {
    backup.value = await parametrosRepository.archivos.iniciarBackup()
    fallosBackup = 0
    seguirBackup()
  } catch (error) {
    errorBackup.value = mensajeError(error, 'Error de conexión al iniciar el backup.', 'No se pudo iniciar el backup.')
  } finally {
    backupIniciando.value = false
  }
}

async function consultarBackup(): Promise<void> {
  const actual = backup.value
  if (!actual || !backupEnCurso.value) return
  try {
    backup.value = await parametrosRepository.archivos.estadoBackup(actual.backup_id)
    fallosBackup = 0
    if (!backupEnCurso.value) {
      if (backupFinalizado.value) notificar('Backup de Recruiting completado.', 'exito', 4000)
      else notificar('No se pudo generar el backup.', 'error', 4000)
      return
    }
  } catch {
    fallosBackup += 1
    if (fallosBackup >= 5) {
      errorBackup.value =
        'Se perdió la conexión con el servidor. El backup puede seguir generándose: volvé a abrir esta ventana en unos minutos.'
      backup.value = null
      return
    }
  }
  seguirBackup()
}

// ---- Importar backup (solo administradores; el backend valida el usuario) ------------------------------------------

const modalImportar = ref(false)
const importacion = ref<ImportacionEstado | null>(null)
const importSubiendo = ref(false)
const subidaPct = ref(0)
const errorImportar = ref('')
const pasoImportar = ref<'vista_previa' | 'confirmar'>('vista_previa')
const textoConfirmacion = ref('')
const aceptaLimitaciones = ref(false)
const confirmandoImportar = ref(false)
const recargarAlCerrarImportar = ref(false)
let temporizadorImportar: number | undefined
let fallosImportar = 0
const archivoImportar = ref<HTMLInputElement | null>(null)

const FASES_IMPORTAR: Record<string, string> = {
  comprobando: 'Comprobando el entorno',
  respaldo_seguridad: 'Generando backup de seguridad',
  preparando_archivos: 'Preparando los CV',
  base_de_datos: 'Restaurando la base de datos',
  reemplazando_archivos: 'Reemplazando los CV',
}

const importEnCurso = computed(
  () => Boolean(importacion.value && ['validando', 'restaurando'].includes(importacion.value.estado)),
)
const importRestaurando = computed(() => importacion.value?.estado === 'restaurando')
const importValidado = computed(() => importacion.value?.estado === 'validado')
const importFinalizado = computed(() => importacion.value?.estado === 'finalizado')
const importConError = computed(
  () => Boolean(importacion.value && ['rechazado', 'error'].includes(importacion.value.estado)),
)
const porcentajeImportar = computed(() =>
  importSubiendo.value
    ? subidaPct.value
    : Math.max(0, Math.min(100, importacion.value?.porcentaje ?? 0)),
)
const puedeConfirmarImportar = computed(() => {
  if (!importValidado.value || confirmandoImportar.value) return false
  if ((importacion.value?.limitaciones.length ?? 0) > 0 && !aceptaLimitaciones.value) return false
  return textoConfirmacion.value.trim() === 'REEMPLAZAR'
})
const backupSeguridad = computed(
  () => importacion.value?.backup_seguridad ?? importacion.value?.resultado?.backup_seguridad ?? null,
)
const urlBackupSeguridad = computed(() =>
  backupSeguridad.value ? parametrosRepository.archivos.descargarBackup(backupSeguridad.value.backup_id) : '#',
)
const tituloImportar = computed(() => {
  if (importSubiendo.value) return 'Subiendo el backup'
  if (!importacion.value) return 'Importar backup de Recruiting'
  const estado = importacion.value.estado
  if (estado === 'validando') return 'Validando el backup'
  if (estado === 'validado') {
    return pasoImportar.value === 'confirmar' ? 'Confirmar restauración' : 'Vista previa del backup'
  }
  if (estado === 'rechazado') return 'Backup no válido'
  if (estado === 'restaurando') {
    return (importacion.value.fase ? FASES_IMPORTAR[importacion.value.fase] : undefined) ?? 'Restaurando'
  }
  if (estado === 'finalizado') return 'Restauración completada'
  return 'No se pudo restaurar'
})

function abrirImportar(): void {
  errorImportar.value = ''
  if (importacion.value && (importEnCurso.value || importValidado.value || importFinalizado.value)) {
    modalImportar.value = true
    return
  }
  if (archivoImportar.value) {
    archivoImportar.value.value = ''
    archivoImportar.value.click()
  }
}

function refrescarTrasImportar(): void {
  const cuentas = importacion.value?.resultado?.usuarios_sin_credenciales ?? []
  if (cuentas.length > 0) {
    recargarAlCerrarImportar.value = true
    return
  }
  window.setTimeout(() => window.location.reload(), 1200)
}

function cerrarImportar(): void {
  modalImportar.value = false
  if (recargarAlCerrarImportar.value) window.location.reload()
  if (importConError.value) importacion.value = null
}

function elegirOtroBackup(): void {
  importacion.value = null
  errorImportar.value = ''
  if (archivoImportar.value) {
    archivoImportar.value.value = ''
    archivoImportar.value.click()
  }
}

async function subirImportacion(evento: Event): Promise<void> {
  const entrada = evento.target as HTMLInputElement
  const archivo = entrada.files?.[0]
  if (!archivo) return
  errorImportar.value = ''
  importacion.value = null
  if (!archivo.name.toLowerCase().endsWith('.zip')) {
    errorImportar.value = 'Seleccioná un backup en formato .zip generado por RECLUIT.'
    modalImportar.value = true
    return
  }
  pasoImportar.value = 'vista_previa'
  textoConfirmacion.value = ''
  aceptaLimitaciones.value = false
  importSubiendo.value = true
  subidaPct.value = 0
  modalImportar.value = true
  try {
    importacion.value = await parametrosRepository.archivos.subirImportacion(archivo, (pct) => {
      subidaPct.value = pct
    })
    fallosImportar = 0
    seguirImportar()
  } catch (error) {
    errorImportar.value = mensajeError(error, 'Error de conexión al subir el backup.', 'No se pudo subir el backup.')
  } finally {
    importSubiendo.value = false
  }
}

function seguirImportar(): void {
  window.clearTimeout(temporizadorImportar)
  temporizadorImportar = window.setTimeout(() => void consultarImportar(), 1000)
}

async function consultarImportar(): Promise<void> {
  const actual = importacion.value
  if (!actual || !importEnCurso.value) return
  try {
    importacion.value = await parametrosRepository.archivos.estadoImportacion(actual.importacion_id)
    fallosImportar = 0
    if (!importEnCurso.value) {
      if (importFinalizado.value) notificar('Restauración de Recruiting completada.', 'exito', 4000)
      else notificar('La importación no pudo completarse.', 'error', 4000)
      modalImportar.value = true
      if (importFinalizado.value) refrescarTrasImportar()
      return
    }
  } catch {
    fallosImportar += 1
    if (fallosImportar >= 5) {
      errorImportar.value =
        'Se perdió la conexión con el servidor. El proceso puede seguir en curso: volvé a abrir esta ventana en unos minutos.'
      return
    }
  }
  seguirImportar()
}

async function confirmarImportar(): Promise<void> {
  const actual = importacion.value
  if (!actual || !puedeConfirmarImportar.value) return
  confirmandoImportar.value = true
  errorImportar.value = ''
  try {
    importacion.value = await parametrosRepository.archivos.confirmarImportacion(
      actual.importacion_id,
      textoConfirmacion.value.trim(),
      aceptaLimitaciones.value,
    )
    fallosImportar = 0
    seguirImportar()
  } catch (error) {
    errorImportar.value = mensajeError(
      error,
      'Error de conexión al iniciar la restauración.',
      'No se pudo iniciar la restauración.',
    )
  } finally {
    confirmandoImportar.value = false
  }
}

async function descartarImportar(): Promise<void> {
  const actual = importacion.value
  modalImportar.value = false
  importacion.value = null
  if (actual && !importEnCurso.value) {
    try {
      await parametrosRepository.archivos.descartarImportacion(actual.importacion_id)
    } catch {
      // la importación se limpia sola a las 24 h
    }
  }
}

// ---- Limpiar BD (solo administradores; el backend valida el usuario) -----------------------------------------------

const modalLimpiar = ref(false)
const limpiando = ref(false)
const errorLimpieza = ref('')
const resumenLimpieza = ref<LimpiezaResumen | null>(null)

function abrirLimpieza(): void {
  errorLimpieza.value = ''
  resumenLimpieza.value = null
  modalLimpiar.value = true
}

function cerrarLimpieza(): void {
  if (limpiando.value) return
  modalLimpiar.value = false
}

async function confirmarLimpieza(): Promise<void> {
  if (limpiando.value) return
  limpiando.value = true
  errorLimpieza.value = ''
  try {
    resumenLimpieza.value = await parametrosRepository.archivos.limpiar()
    filtro.value = ''
    busqueda.value = ''
    await cliente.invalidateQueries({ queryKey: ['recruiting', 'parametros', 'archivos-cv'] })
    const lista = carpetas.value
    const destino = lista.some((carpeta) => carpeta.carpeta === seleccionada.value)
      ? seleccionada.value
      : (lista[0]?.carpeta ?? null)
    if (destino) seleccionar(destino)
  } catch (error) {
    errorLimpieza.value = mensajeError(error, 'Error de conexión al ejecutar la limpieza.', 'No se pudo completar la limpieza.')
  } finally {
    limpiando.value = false
  }
}

onScopeDispose(() => {
  window.clearTimeout(temporizadorBusqueda)
  window.clearTimeout(temporizadorBackup)
  window.clearTimeout(temporizadorImportar)
})
</script>

<template>
  <ParametrosLayout activa="archivos">
    <AvisoFlotante :mensaje="mensaje" :tipo="tipo" />

    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex items-center gap-3">
        <span class="rounded-xl bg-primary-50 p-2.5 text-primary-600">
          <Archive class="h-5 w-5" />
        </span>
        <div>
          <h2 class="text-base font-bold text-dark-900">Archivos de CV</h2>
          <p class="mt-0.5 text-xs text-dark-400">
            Originales archivados por la carga individual y masiva. Solo consulta y descarga.
          </p>
        </div>
      </div>

      <div v-if="sesion.esAdmin" class="flex items-center gap-2">
        <button
          type="button"
          data-testid="archivos-cv-backup"
          class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-blue-700"
          @click="abrirBackup"
        >
          <DatabaseBackup class="h-4 w-4" />
          <span>{{ backupEnCurso ? `Backup ${porcentajeBackup}%` : 'Backup' }}</span>
        </button>
        <button
          type="button"
          data-testid="archivos-cv-importar"
          class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-violet-700"
          @click="abrirImportar"
        >
          <DatabaseZap class="h-4 w-4" />
          <span>{{
            importEnCurso ? `${importRestaurando ? 'Restaurando' : 'Validando'} ${porcentajeImportar}%` : 'Importar'
          }}</span>
        </button>
        <input
          ref="archivoImportar"
          type="file"
          accept=".zip,application/zip"
          class="hidden"
          data-testid="archivos-cv-importar-archivo"
          @change="subirImportacion"
        />
        <button
          type="button"
          data-testid="archivos-cv-limpiar-bd"
          class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white shadow-soft transition-colors hover:bg-rose-700"
          @click="abrirLimpieza"
        >
          <Trash2 class="h-4 w-4" />
          <span>Limpiar BD</span>
        </button>
      </div>
    </div>

    <div
      v-if="errorResumen"
      class="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
      data-testid="archivos-cv-error"
    >
      {{ errorResumen }}
    </div>

    <!-- Tarjetas: una por carpeta -->
    <div class="grid grid-cols-1 gap-4 md:grid-cols-3" data-testid="archivos-cv-tarjetas">
      <div
        v-if="cargandoResumen && carpetas.length === 0"
        class="rounded-2xl border border-dark-100 bg-white p-8 text-center text-dark-400 shadow-soft md:col-span-3"
      >
        <div class="inline-flex items-center gap-2 text-xs">
          <Loader2 class="h-4 w-4 animate-spin text-primary-600" />
          <span>Consultando el almacenamiento...</span>
        </div>
      </div>
      <button
        v-for="carpeta in carpetas"
        :key="carpeta.carpeta"
        type="button"
        :data-testid="`archivos-cv-tarjeta-${carpeta.carpeta}`"
        :aria-pressed="seleccionada === carpeta.carpeta ? 'true' : 'false'"
        class="cursor-pointer rounded-2xl border p-5 text-left shadow-soft transition-all focus:outline-none"
        :class="seleccionada === carpeta.carpeta ? metaCarpeta(carpeta.carpeta).activa : metaCarpeta(carpeta.carpeta).tarjeta"
        @click="seleccionar(carpeta.carpeta)"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex min-w-0 items-center gap-3">
            <span class="shrink-0 rounded-xl p-2.5" :class="metaCarpeta(carpeta.carpeta).icono_caja">
              <component :is="metaCarpeta(carpeta.carpeta).icono" class="h-5 w-5" />
            </span>
            <div class="min-w-0">
              <p class="text-sm font-bold text-dark-900">{{ metaCarpeta(carpeta.carpeta).titulo }}</p>
              <p class="flex min-w-0 items-center gap-1 font-mono text-xs text-dark-500">
                <Folder class="h-3.5 w-3.5 shrink-0" />
                <span class="truncate" data-testid="archivos-cv-nombre-carpeta">{{ carpeta.carpeta }}</span>
              </p>
            </div>
          </div>
        </div>
        <div class="mt-4 flex items-end justify-between gap-3">
          <div>
            <p class="text-3xl font-bold" :class="metaCarpeta(carpeta.carpeta).cifra" data-testid="archivos-cv-cantidad">
              {{ carpeta.cantidad_archivos }}
            </p>
            <p class="text-xs text-dark-500">{{ carpeta.cantidad_archivos === 1 ? 'archivo' : 'archivos' }}</p>
          </div>
          <div class="text-right">
            <p class="text-lg font-bold text-dark-800" data-testid="archivos-cv-espacio">{{ carpeta.tamano_total }}</p>
            <p class="text-xs text-dark-500">espacio ocupado</p>
          </div>
        </div>
        <p class="mt-3 text-xs text-dark-400">{{ metaCarpeta(carpeta.carpeta).detalle }}</p>
      </button>
    </div>

    <!-- Contenido de la carpeta seleccionada -->
    <div
      v-if="seleccionada"
      class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft"
      data-testid="archivos-cv-detalle"
    >
      <div class="flex flex-col gap-4 border-b border-dark-100 p-5 sm:p-6 lg:flex-row lg:items-center lg:justify-between">
        <div class="min-w-0">
          <p class="text-xs font-semibold tracking-wider text-dark-400 uppercase">Carpeta seleccionada</p>
          <h3 class="flex flex-wrap items-center gap-2 text-base font-bold text-dark-900">
            <span>{{ metaCarpeta(seleccionada).titulo }}</span>
            <span
              class="inline-flex items-center gap-1 rounded-lg bg-dark-100 px-2 py-0.5 font-mono text-xs font-medium text-dark-600"
            >
              <Folder class="h-3.5 w-3.5 shrink-0" />
              <span data-testid="archivos-cv-carpeta-seleccionada">{{ seleccionada }}</span>
            </span>
          </h3>
          <p class="mt-1 text-xs text-dark-500">
            <span>{{ detalle?.cantidad_archivos ?? 0 }}</span> archivo(s) ·
            <span>{{ detalle?.tamano_total ?? '0 MB' }}</span> ocupados
          </p>
        </div>

        <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div v-if="detalle && detalle.cantidad_archivos > 0" class="relative w-full sm:w-64">
            <Search class="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-dark-400" />
            <input
              v-model="filtro"
              type="text"
              placeholder="Buscar por nombre..."
              data-testid="archivos-cv-buscar"
              class="w-full rounded-xl border border-dark-200 bg-white py-2 pr-3 pl-9 text-xs focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
              @input="buscar"
            />
          </div>

          <a
            v-if="detalle && detalle.cantidad_archivos > 0"
            :href="urlDescargaTodos()"
            download
            data-testid="archivos-cv-descargar-todos"
            :title="`Descargar en un ZIP los ${detalle.cantidad_archivos} archivos de ${seleccionada}`"
            class="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold whitespace-nowrap text-white shadow-soft transition-colors"
            :class="metaCarpeta(seleccionada).boton"
            @click="avisarDescargaTodos"
          >
            <Download class="h-4 w-4" />
            <span>Descargar todos (ZIP)</span>
          </a>
          <button
            v-else-if="detalle && detalle.cantidad_archivos === 0"
            type="button"
            disabled
            data-testid="archivos-cv-descargar-todos-deshabilitado"
            title="No hay archivos para descargar en esta carpeta"
            class="inline-flex cursor-not-allowed items-center justify-center gap-2 rounded-xl bg-dark-100 px-4 py-2 text-xs font-semibold whitespace-nowrap text-dark-400"
          >
            <Download class="h-4 w-4" />
            <span>Descargar todos (ZIP)</span>
          </button>
        </div>
      </div>

      <div
        v-if="errorDetalle"
        class="m-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
      >
        {{ errorDetalle }}
      </div>

      <div class="overflow-x-auto" data-testid="archivos-cv-tabla">
        <table class="w-full border-collapse text-left">
          <thead>
            <tr class="border-b border-dark-100 bg-dark-50/60 text-xs font-semibold tracking-wider text-dark-500 uppercase">
              <th class="px-6 py-3.5">Nombre</th>
              <th class="px-6 py-3.5 whitespace-nowrap">Tamaño</th>
              <th class="px-6 py-3.5 whitespace-nowrap">Última modificación</th>
              <th v-if="esCarpetaErrores" class="px-6 py-3.5" data-testid="archivos-cv-th-motivo">Motivo del error</th>
              <th class="px-6 py-3.5 text-right">Descargar</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-dark-100 text-sm">
            <tr v-if="cargandoDetalle">
              <td :colspan="columnas" class="px-6 py-12 text-center text-dark-400">
                <div class="inline-flex items-center gap-2 text-xs">
                  <Loader2 class="h-4 w-4 animate-spin text-primary-600" />
                  <span>Consultando la carpeta...</span>
                </div>
              </td>
            </tr>

            <tr v-else-if="detalle && detalle.cantidad_archivos === 0" data-testid="archivos-cv-vacia">
              <td :colspan="columnas" class="px-6 py-14 text-center">
                <div class="inline-flex flex-col items-center gap-2 text-dark-400">
                  <FolderOpen class="h-8 w-8" />
                  <p class="text-sm font-semibold text-dark-600">Esta carpeta no tiene archivos</p>
                  <p class="text-xs">
                    Espacio ocupado: <span>{{ detalle.tamano_total }}</span>. No hay archivos para descargar.
                  </p>
                </div>
              </td>
            </tr>

            <tr v-else-if="detalle && detalle.cantidad_archivos > 0 && totalFiltrado === 0">
              <td :colspan="columnas" class="px-6 py-10 text-center text-xs text-dark-400">
                Ningún archivo coincide con la búsqueda.
              </td>
            </tr>

            <template v-else>
              <tr
                v-for="archivo in archivos"
                :key="archivo.nombre"
                class="transition-colors hover:bg-dark-50/50"
                data-testid="archivos-cv-fila"
              >
                <td class="min-w-[14rem] px-6 py-3.5">
                  <div class="flex min-w-0 items-center gap-2.5">
                    <FileText class="h-4 w-4 shrink-0 text-dark-400" />
                    <span class="font-medium break-all text-dark-800">{{ archivo.nombre }}</span>
                  </div>
                </td>
                <td class="px-6 py-3.5 whitespace-nowrap text-dark-600">{{ archivo.tamano }}</td>
                <td class="px-6 py-3.5 whitespace-nowrap text-dark-600">{{ formatearFechaHora(archivo.modificado) }}</td>
                <td v-if="esCarpetaErrores" class="max-w-xs px-6 py-3.5 text-dark-700">
                  <span
                    class="block truncate text-xs"
                    :class="archivo.motivo_error ? '' : 'text-dark-400 italic'"
                    :title="archivo.motivo_detalle || archivo.motivo_error || 'Motivo no disponible'"
                    data-testid="archivos-cv-motivo"
                  >
                    {{ archivo.motivo_error || 'Motivo no disponible' }}
                  </span>
                </td>
                <td class="px-6 py-3.5 text-right">
                  <a
                    :href="urlDescarga(archivo.nombre)"
                    download
                    :title="`Descargar ${archivo.nombre}`"
                    :aria-label="`Descargar ${archivo.nombre}`"
                    data-testid="archivos-cv-descargar"
                    class="inline-flex cursor-pointer items-center justify-center rounded-lg p-2 text-primary-600 transition-colors hover:bg-primary-50"
                    @click="avisarDescarga(archivo.nombre)"
                  >
                    <Download class="h-4 w-4" />
                  </a>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div
        v-if="detalle && totalFiltrado > 0"
        class="flex flex-col gap-3 border-t border-dark-100 px-6 py-4 text-xs text-dark-500 sm:flex-row sm:items-center sm:justify-between"
        data-testid="archivos-cv-paginacion"
      >
        <span data-testid="archivos-cv-rango">
          Mostrando <span>{{ desde }}</span>-<span>{{ hasta }}</span> de <span>{{ totalFiltrado }}</span> archivos
        </span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            data-testid="archivos-cv-anterior"
            :disabled="pagina <= 1 || cargandoDetalle"
            class="cursor-pointer rounded-lg border border-dark-200 bg-white px-3 py-1.5 font-semibold text-dark-700 hover:bg-dark-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="irAPagina(pagina - 1)"
          >
            Anterior
          </button>
          <span class="font-semibold whitespace-nowrap text-dark-700" data-testid="archivos-cv-pagina">
            Página <span>{{ pagina }}</span> de <span>{{ totalPaginas }}</span>
          </span>
          <button
            type="button"
            data-testid="archivos-cv-siguiente"
            :disabled="pagina >= totalPaginas || cargandoDetalle"
            class="cursor-pointer rounded-lg border border-dark-200 bg-white px-3 py-1.5 font-semibold text-dark-700 hover:bg-dark-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="irAPagina(pagina + 1)"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>

    <template v-if="sesion.esAdmin">
      <!-- Backup -->
      <div
        v-if="modalBackup"
        class="fixed inset-0 z-50 overflow-y-auto"
        role="dialog"
        aria-modal="true"
        data-testid="modal-backup"
        @keydown.escape.window="cerrarBackup"
      >
        <div class="fixed inset-0 bg-dark-900/40 backdrop-blur-sm" @click="cerrarBackup" />
        <div class="flex min-h-full items-center justify-center p-4 text-center">
          <div
            class="relative w-full max-w-md overflow-hidden rounded-2xl border border-dark-100 bg-white p-6 text-left shadow-2xl"
            @click.stop
          >
            <div class="flex items-center gap-2.5 border-b border-dark-100 pb-4">
              <span
                class="rounded-xl p-2"
                :class="backupConError ? 'bg-rose-50 text-rose-600' : backupFinalizado ? 'bg-emerald-50 text-emerald-600' : 'bg-blue-50 text-blue-600'"
              >
                <AlertTriangle v-if="backupConError" class="h-5 w-5" />
                <CheckCircle v-else-if="backupFinalizado" class="h-5 w-5" />
                <DatabaseBackup v-else class="h-5 w-5" />
              </span>
              <h3 class="text-base font-bold text-dark-900" data-testid="backup-titulo">{{ tituloBackup }}</h3>
            </div>

            <div v-if="!backup">
              <p class="mt-4 text-sm text-dark-600">
                Se generará un único archivo ZIP con <strong>toda la información de Recruiting</strong>: la base de datos
                (candidatos, búsquedas, pipeline, historiales, catálogos y demás tablas del módulo) y todos los CV de las
                carpetas <span class="font-mono text-xs">cv_procesados_ok</span>,
                <span class="font-mono text-xs">cv_duplicados</span> y
                <span class="font-mono text-xs">cv_errores</span>.
              </p>
              <p class="mt-2 text-xs text-dark-500">
                Es una copia de solo lectura: no modifica ni elimina ningún dato. Puede demorar varios minutos y podés
                cerrar esta ventana mientras se genera.
              </p>
              <p
                v-if="errorBackup"
                class="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
                data-testid="backup-error"
              >
                {{ errorBackup }}
              </p>
              <div class="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  data-testid="backup-cancelar"
                  class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50"
                  @click="cerrarBackup"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  data-testid="backup-generar"
                  :disabled="backupIniciando"
                  class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
                  @click="iniciarBackup"
                >
                  <span>{{ backupIniciando ? 'Iniciando...' : 'Generar backup' }}</span>
                </button>
              </div>
            </div>

            <div v-else data-testid="backup-estado" :data-estado="backup.estado">
              <p class="mt-4 text-sm text-dark-700" data-testid="backup-mensaje">{{ backup.mensaje }}</p>
              <div
                class="mt-3 h-3 w-full overflow-hidden rounded-full bg-dark-100"
                role="progressbar"
                aria-label="Progreso del backup"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="porcentajeBackup"
                data-testid="backup-barra"
              >
                <div
                  class="h-full rounded-full"
                  :class="backupConError ? 'bg-rose-500' : backupFinalizado ? 'bg-emerald-500' : 'bg-blue-600'"
                  :style="`width:${porcentajeBackup}%`"
                  data-testid="backup-barra-relleno"
                />
              </div>
              <p class="mt-1 text-xs text-dark-500" data-testid="backup-porcentaje">{{ porcentajeBackup }}%</p>
              <div
                v-if="backupFinalizado"
                class="mt-4 space-y-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
                data-testid="backup-resumen"
              >
                <p>Archivo: <span class="font-mono">{{ backup.nombre_archivo }}</span></p>
                <p>Tamaño: <strong>{{ backup.tamano }}</strong></p>
                <p class="break-all">SHA-256: <span class="font-mono">{{ backup.sha256 }}</span></p>
                <p>Integridad verificada. El archivo permanece disponible para descargar durante 24 horas.</p>
              </div>
              <p
                v-if="backupConError"
                class="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
                data-testid="backup-error-generacion"
              >
                No se generó ningún archivo. Podés intentarlo nuevamente.
              </p>
              <div class="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  data-testid="backup-cerrar"
                  class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50"
                  @click="cerrarBackup"
                >
                  Cerrar
                </button>
                <button
                  v-if="backupConError"
                  type="button"
                  data-testid="backup-reintentar"
                  class="cursor-pointer rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700"
                  @click="backup = null"
                >
                  Reintentar
                </button>
                <a
                  v-if="backupFinalizado"
                  :href="urlDescargaBackup"
                  download
                  data-testid="backup-descargar"
                  class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700"
                >
                  <Download class="h-4 w-4" /><span>Descargar backup</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Importar -->
      <div
        v-if="modalImportar"
        class="fixed inset-0 z-50 overflow-y-auto"
        role="dialog"
        aria-modal="true"
        data-testid="modal-importar"
        @keydown.escape.window="cerrarImportar"
      >
        <div class="fixed inset-0 bg-dark-900/40 backdrop-blur-sm" @click="cerrarImportar" />
        <div class="flex min-h-full items-center justify-center p-4 text-center">
          <div
            class="relative w-full max-w-2xl overflow-hidden rounded-2xl border border-dark-100 bg-white p-6 text-left shadow-2xl"
            @click.stop
          >
            <div class="flex items-center gap-2.5 border-b border-dark-100 pb-4">
              <span
                class="rounded-xl p-2"
                :class="importConError || errorImportar ? 'bg-rose-50 text-rose-600' : importFinalizado ? 'bg-emerald-50 text-emerald-600' : 'bg-violet-50 text-violet-600'"
              >
                <AlertTriangle v-if="importConError || errorImportar" class="h-5 w-5" />
                <CheckCircle v-else-if="importFinalizado" class="h-5 w-5" />
                <DatabaseZap v-else class="h-5 w-5" />
              </span>
              <h3 class="text-base font-bold text-dark-900" data-testid="importar-titulo">{{ tituloImportar }}</h3>
            </div>

            <p
              v-if="errorImportar"
              class="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
              data-testid="importar-error"
            >
              {{ errorImportar }}
            </p>

            <div v-if="importSubiendo || importEnCurso" data-testid="importar-progreso">
              <p class="mt-4 text-sm text-dark-700" data-testid="importar-mensaje">
                {{ importSubiendo ? 'Subiendo el archivo al servidor...' : importacion?.mensaje }}
              </p>
              <div
                class="mt-3 h-3 w-full overflow-hidden rounded-full bg-dark-100"
                role="progressbar"
                aria-label="Progreso de la importación"
                aria-valuemin="0"
                aria-valuemax="100"
                :aria-valuenow="porcentajeImportar"
                data-testid="importar-barra"
              >
                <div class="h-full rounded-full bg-violet-600" :style="`width:${porcentajeImportar}%`" />
              </div>
              <p class="mt-1 text-xs text-dark-500">{{ porcentajeImportar }}%</p>
              <p
                v-if="importRestaurando"
                class="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"
              >
                La restauración está en curso: no realices cargas de CV hasta que termine. Podés cerrar esta ventana; el
                proceso continúa en el servidor.
              </p>
            </div>

            <div v-if="importConError" data-testid="importar-rechazo">
              <p class="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                {{ importacion?.mensaje }}
              </p>
              <p v-if="importacion?.estado === 'error' && importacion.revertido" class="mt-2 text-xs text-dark-600">
                Se recuperó el estado anterior de Recruiting: no quedaron datos ni archivos a medio restaurar.
              </p>
              <p v-if="importacion?.backup_seguridad" class="mt-2 text-xs text-dark-600">
                Backup de seguridad disponible:
                <a :href="urlBackupSeguridad" download class="font-mono text-blue-700 underline">{{
                  importacion.backup_seguridad.nombre_archivo
                }}</a>
              </p>
            </div>

            <div v-if="importValidado && pasoImportar === 'vista_previa'" data-testid="importar-vista-previa">
              <template v-if="importacion?.preview">
                <div
                  class="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"
                  data-testid="importar-integridad"
                >
                  <strong>Integridad: verificada.</strong> <span>{{ importacion.preview.integridad.detalle }}</span>
                </div>
                <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-dark-700">
                  <dt class="text-dark-500">Fecha del backup (UTC)</dt>
                  <dd data-testid="importar-fecha">{{ importacion.preview.generado_utc }}</dd>
                  <dt class="text-dark-500">Versión del formato</dt>
                  <dd>{{ importacion.preview.version_backup }}</dd>
                  <dt class="text-dark-500">Generado por</dt>
                  <dd>{{ importacion.preview.generado_por || '-' }}</dd>
                  <dt class="text-dark-500">Tamaño total</dt>
                  <dd data-testid="importar-tamano">
                    {{ importacion.preview.tamano_total }} (ZIP: {{ importacion.preview.tamano_zip }})
                  </dd>
                  <dt class="text-dark-500">Registros</dt>
                  <dd>{{ importacion.preview.total_registros }} en {{ importacion.preview.total_tablas }} tablas</dd>
                </dl>
                <h4 class="mt-4 text-xs font-bold text-dark-800">CV por carpeta</h4>
                <ul class="mt-1 space-y-0.5 text-xs text-dark-700" data-testid="importar-carpetas">
                  <li v-for="carpeta in importacion.preview.carpetas" :key="carpeta.carpeta">
                    <span class="font-mono">{{ carpeta.carpeta }}</span>: <strong>{{ carpeta.cantidad }}</strong> archivos
                    ({{ carpeta.tamano }})
                  </li>
                </ul>
                <h4 class="mt-4 text-xs font-bold text-dark-800">Registros por tabla</h4>
                <div
                  class="mt-1 max-h-40 overflow-y-auto rounded-xl border border-dark-100 p-2"
                  data-testid="importar-tablas"
                >
                  <table class="w-full text-xs text-dark-700">
                    <tbody>
                      <tr v-for="tabla in importacion.preview.tablas" :key="tabla.tabla">
                        <td class="py-0.5 font-mono">{{ tabla.tabla }}</td>
                        <td class="text-right">{{ tabla.registros }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div
                  v-if="importacion.limitaciones.length"
                  class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"
                  data-testid="importar-limitaciones"
                >
                  <p class="font-bold">Limitaciones de este backup</p>
                  <ul class="mt-1 list-disc space-y-0.5 pl-4">
                    <li v-for="limitacion in importacion.limitaciones" :key="limitacion">{{ limitacion }}</li>
                  </ul>
                </div>
                <div
                  v-if="importacion.avisos.length"
                  class="mt-3 rounded-xl border border-dark-100 bg-dark-50 p-3 text-xs text-dark-700"
                  data-testid="importar-avisos"
                >
                  <ul class="list-disc space-y-0.5 pl-4">
                    <li v-for="aviso in importacion.avisos" :key="aviso">{{ aviso }}</li>
                  </ul>
                </div>
                <div class="mt-6 flex justify-end gap-2">
                  <button
                    type="button"
                    data-testid="importar-cancelar"
                    class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50"
                    @click="descartarImportar"
                  >
                    Cancelar
                  </button>
                  <button
                    type="button"
                    data-testid="importar-continuar"
                    class="cursor-pointer rounded-xl bg-violet-600 px-4 py-2 text-xs font-semibold text-white hover:bg-violet-700"
                    @click="pasoImportar = 'confirmar'"
                  >
                    Continuar
                  </button>
                </div>
              </template>
            </div>

            <div v-if="importValidado && pasoImportar === 'confirmar'" data-testid="importar-confirmacion">
              <p class="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm font-semibold text-rose-800">
                Atención: se reemplazará TODA la información actual de Recruiting (candidatos, búsquedas, pipeline,
                historiales, parámetros y los CV de las tres carpetas) por la del backup. No se mezclan ni se duplican
                datos.
              </p>
              <ul class="mt-3 list-disc space-y-0.5 pl-4 text-xs text-dark-600">
                <li>
                  Antes de empezar se genera automáticamente un backup de seguridad del estado actual; si no puede
                  generarse, no se restaura nada.
                </li>
                <li>Si ocurre un error, se recupera el estado anterior.</li>
                <li>No se modifican usuarios, contraseñas ni otros módulos.</li>
              </ul>
              <label
                v-if="importacion && importacion.limitaciones.length"
                class="mt-4 flex items-start gap-2 text-xs text-dark-700"
              >
                <input v-model="aceptaLimitaciones" type="checkbox" data-testid="importar-acepta-limitaciones" class="mt-0.5" />
                <span>Entiendo y acepto las limitaciones de este backup.</span>
              </label>
              <label class="mt-4 block text-xs font-semibold text-dark-700">
                Para confirmar escribí <span class="font-mono">REEMPLAZAR</span>
                <input
                  v-model="textoConfirmacion"
                  type="text"
                  autocomplete="off"
                  data-testid="importar-texto-confirmacion"
                  class="mt-1 w-full rounded-xl border border-dark-200 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500/30 focus:outline-none"
                />
              </label>
              <div class="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  data-testid="importar-volver"
                  class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50"
                  @click="pasoImportar = 'vista_previa'; textoConfirmacion = ''"
                >
                  Volver
                </button>
                <button
                  type="button"
                  data-testid="importar-confirmar"
                  :disabled="!puedeConfirmarImportar"
                  class="cursor-pointer rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
                  @click="confirmarImportar"
                >
                  <span>{{ confirmandoImportar ? 'Iniciando...' : 'Importar y reemplazar' }}</span>
                </button>
              </div>
            </div>

            <div v-if="importFinalizado" data-testid="importar-resultado">
              <template v-if="importacion?.resultado">
                <div class="mt-4 space-y-1 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
                  <p>
                    <strong>{{ importacion.resultado.total_registros }}</strong> registros restaurados y
                    <strong>{{ importacion.resultado.total_archivos }}</strong> CV recuperados.
                  </p>
                  <p v-if="importacion.resultado.backup_seguridad">
                    Backup de seguridad del estado anterior:
                    <a :href="urlBackupSeguridad" download class="font-mono underline">{{
                      importacion.resultado.backup_seguridad.nombre_archivo
                    }}</a>
                    ({{ importacion.resultado.backup_seguridad.tamano }}, disponible 24 horas).
                  </p>
                  <p v-if="importacion.resultado.archivos_storage">
                    <strong>{{ importacion.resultado.archivos_storage }}</strong> archivos del almacenamiento (CV
                    vinculados y adjuntos) recuperados.
                  </p>
                  <div
                    v-if="importacion.resultado.usuarios_sin_credenciales.length"
                    class="rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-900"
                    data-testid="importar-usuarios-sin-credenciales"
                  >
                    <p class="font-bold">Cuentas creadas sin contraseña: deben restablecerla</p>
                    <p>
                      No se restauran contraseñas ni secretos. Estas cuentas no existían en este servidor: ingresan con
                      «Olvidé mi contraseña» o un administrador les genera un enlace de acceso.
                    </p>
                    <ul class="mt-1 list-disc pl-4">
                      <li
                        v-for="usuario in importacion.resultado.usuarios_sin_credenciales"
                        :key="usuario.id"
                        class="font-mono"
                      >
                        {{ usuario.email }}
                      </li>
                    </ul>
                  </div>
                </div>
              </template>
            </div>

            <div v-if="!importValidado && !importSubiendo" class="mt-6 flex justify-end gap-2">
              <button
                v-if="importConError || errorImportar"
                type="button"
                data-testid="importar-otro"
                class="cursor-pointer rounded-xl bg-violet-600 px-4 py-2 text-xs font-semibold text-white hover:bg-violet-700"
                @click="elegirOtroBackup"
              >
                Elegir otro backup
              </button>
              <button
                type="button"
                data-testid="importar-cerrar"
                class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50"
                @click="cerrarImportar"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Limpiar BD -->
      <div
        v-if="modalLimpiar"
        class="fixed inset-0 z-50 overflow-y-auto"
        role="dialog"
        aria-modal="true"
        data-testid="modal-limpiar-bd"
        @keydown.escape.window="cerrarLimpieza"
      >
        <div class="fixed inset-0 bg-dark-900/40 backdrop-blur-sm" @click="cerrarLimpieza" />
        <div class="flex min-h-full items-center justify-center p-4 text-center">
          <div
            class="relative w-full max-w-md overflow-hidden rounded-2xl border border-dark-100 bg-white p-6 text-left shadow-2xl"
            @click.stop
          >
            <template v-if="!resumenLimpieza">
              <div class="flex items-center gap-2.5 border-b border-dark-100 pb-4">
                <span class="rounded-xl bg-rose-50 p-2 text-rose-600"><AlertTriangle class="h-5 w-5" /></span>
                <h3 class="text-base font-bold text-dark-900">Limpiar base de datos de Recruiting</h3>
              </div>
              <p class="mt-4 text-sm text-dark-600">
                Se eliminarán <strong>definitivamente</strong> todos los candidatos, búsquedas, registros del pipeline,
                notificaciones de Recruiting y los CV almacenados (<span class="font-mono text-xs">cv_procesados_ok</span>,
                <span class="font-mono text-xs">cv_errores</span> y
                <span class="font-mono text-xs">cv_duplicados</span>), con sus archivos físicos. Usuarios, roles, empresas,
                parámetros y catálogos no se tocan.
              </p>
              <p class="mt-2 text-sm font-semibold text-rose-700">Esta acción no se puede deshacer.</p>
              <p
                v-if="errorLimpieza"
                class="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
                data-testid="limpiar-bd-error"
              >
                {{ errorLimpieza }}
              </p>
              <div class="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  data-testid="limpiar-bd-cancelar"
                  :disabled="limpiando"
                  class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2 text-xs font-semibold text-dark-700 hover:bg-dark-50 disabled:opacity-60"
                  @click="cerrarLimpieza"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  data-testid="limpiar-bd-confirmar"
                  :disabled="limpiando"
                  class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-60"
                  @click="confirmarLimpieza"
                >
                  <span>{{ limpiando ? 'Limpiando...' : 'Sí, eliminar todo' }}</span>
                </button>
              </div>
            </template>
            <template v-else>
              <div data-testid="limpiar-bd-resumen">
                <div class="flex items-center gap-2.5 border-b border-dark-100 pb-4">
                  <span class="rounded-xl bg-emerald-50 p-2 text-emerald-600"><CheckCircle class="h-5 w-5" /></span>
                  <h3 class="text-base font-bold text-dark-900">Limpieza completada</h3>
                </div>
                <p class="mt-4 text-xs font-semibold text-dark-500 uppercase">
                  Registros eliminados:
                  <span data-testid="limpiar-bd-total-registros">{{ resumenLimpieza.total_registros }}</span>
                </p>
                <ul class="mt-2 space-y-1 text-sm text-dark-700">
                  <li
                    v-for="[clave, cantidad] in Object.entries(resumenLimpieza.registros)"
                    :key="clave"
                    class="flex justify-between"
                  >
                    <span>{{ etiquetaRegistro(clave) }}</span><strong>{{ cantidad }}</strong>
                  </li>
                </ul>
                <p class="mt-4 text-xs font-semibold text-dark-500 uppercase">
                  Archivos eliminados:
                  <span data-testid="limpiar-bd-total-archivos">{{ resumenLimpieza.total_archivos }}</span>
                </p>
                <ul class="mt-2 space-y-1 text-sm text-dark-700">
                  <li
                    v-for="[clave, cantidad] in Object.entries(resumenLimpieza.archivos)"
                    :key="clave"
                    class="flex justify-between"
                  >
                    <span>{{ etiquetaArchivo(clave) }}</span><strong>{{ cantidad }}</strong>
                  </li>
                </ul>
                <div class="mt-6 flex justify-end">
                  <button
                    type="button"
                    data-testid="limpiar-bd-aceptar"
                    class="cursor-pointer rounded-xl bg-primary-600 px-4 py-2 text-xs font-semibold text-white hover:bg-primary-700"
                    @click="cerrarLimpieza"
                  >
                    Aceptar
                  </button>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>
  </ParametrosLayout>
</template>
