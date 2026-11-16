import { useQueryClient } from '@tanstack/vue-query'
import { computed, onScopeDispose, ref } from 'vue'

import { candidatosRepository as repo } from '../api/candidatos.repository'
import { agregarArchivosMasivo, mensajeCancelado, porcentajeLote } from '../cv'
import type { EstadoLote, ReporteLote } from '../types'
import { CLAVE_LISTADO } from './useListadoCandidatos'

const CADA_MS = 800
const REINTENTO_MS = 2000
const MAX_FALLOS = 4
const PAUSA_ANTES_DEL_RESUMEN_MS = 700

/**
 * Carga masiva de CV en segundo plano: arma la selección, inicia el lote y sigue su avance real (procesados
 * sobre el total que informa el backend). Un corte momentáneo se reintenta antes de informar el error.
 * `avisar` muestra los toasts (la pantalla decide cómo).
 */
export function useCargaMasiva(avisar: (tipo: 'warn' | 'error', mensaje: string) => void) {
  const cliente = useQueryClient()

  const abierto = ref(false)
  const archivos = ref<File[]>([])
  const error = ref('')
  const advertenciaLimite = ref('')
  const procesando = ref(false)
  const cancelando = ref(false)
  const estado = ref<EstadoLote | ''>('')
  const progreso = ref({ procesados: 0, total: 0 })
  const resumenAbierto = ref(false)
  const reporteFinal = ref<ReporteLote | null>(null)
  /** Candidatos creados por un lote cancelado: si hubo, al cerrar se refresca el listado. */
  const creadosAlCancelar = ref(0)

  let lote: string | null = null
  let temporizador: ReturnType<typeof setTimeout> | null = null
  let fallos = 0

  const refrescarListado = () => cliente.invalidateQueries({ queryKey: CLAVE_LISTADO })

  function detener(): void {
    if (temporizador) clearTimeout(temporizador)
    temporizador = null
  }

  function terminar(): void {
    detener()
    procesando.value = false
    cancelando.value = false
    lote = null
  }

  onScopeDispose(detener)

  function abrir(): void {
    error.value = ''
    estado.value = ''
    progreso.value = { procesados: 0, total: 0 }
    creadosAlCancelar.value = 0
    archivos.value = []
    advertenciaLimite.value = ''
    abierto.value = true
  }

  function cerrar(): void {
    if (procesando.value) return
    abierto.value = false
    archivos.value = []
    advertenciaLimite.value = ''
    if (creadosAlCancelar.value > 0) void refrescarListado()
    creadosAlCancelar.value = 0
  }

  function agregar(nuevos: File[]): void {
    error.value = ''
    advertenciaLimite.value = ''
    const resultado = agregarArchivosMasivo(archivos.value, nuevos)
    archivos.value = resultado.archivos
    advertenciaLimite.value = resultado.advertenciaLimite
    if (resultado.errores) error.value = resultado.errores
  }

  function quitar(indice: number): void {
    advertenciaLimite.value = ''
    archivos.value = archivos.value.filter((_, i) => i !== indice)
  }

  async function consultar(): Promise<void> {
    const actual = lote
    if (!actual) return
    try {
      const avance = await repo.avanceLote(actual)
      if (actual !== lote) return
      fallos = 0
      progreso.value = { procesados: avance.procesados || 0, total: avance.total || 0 }
      if (avance.estado === 'finalizado') {
        estado.value = 'finalizado'
        detener()
        // Se ve el 100 % y «Carga finalizada» un instante antes del resumen.
        setTimeout(() => {
          reporteFinal.value = avance.reporte ?? null
          archivos.value = []
          abierto.value = false
          resumenAbierto.value = true
          terminar()
        }, PAUSA_ANTES_DEL_RESUMEN_MS)
        return
      }
      if (avance.estado === 'cancelado') {
        estado.value = 'cancelado'
        creadosAlCancelar.value = avance.reporte?.resumen?.creados ?? 0
        error.value = mensajeCancelado(avance)
        terminar()
        return
      }
      if (avance.estado === 'error') {
        estado.value = 'error'
        error.value = avance.error || 'Ocurrió un error al procesar el lote de CVs.'
        avisar('warn', error.value)
        terminar()
        return
      }
      temporizador = setTimeout(() => void consultar(), CADA_MS)
    } catch {
      fallos += 1
      if (fallos < MAX_FALLOS && actual === lote) {
        temporizador = setTimeout(() => void consultar(), REINTENTO_MS)
        return
      }
      estado.value = 'error'
      error.value = 'Error de comunicación con el servidor al consultar el avance de la carga.'
      avisar('error', error.value)
      terminar()
    }
  }

  async function iniciar(): Promise<void> {
    if (!archivos.value.length || procesando.value) return
    procesando.value = true
    error.value = ''
    estado.value = 'procesando'
    progreso.value = { procesados: 0, total: 0 }
    cancelando.value = false
    fallos = 0
    try {
      lote = await repo.iniciarLote(archivos.value)
      void consultar()
    } catch (e) {
      estado.value = 'error'
      const mensaje = e instanceof Error ? e.message : ''
      error.value = mensaje || 'Error de comunicación con el servidor al procesar el archivo comprimido.'
      avisar('warn', error.value)
      terminar()
    }
  }

  async function cancelar(): Promise<void> {
    if (!lote || cancelando.value) return
    cancelando.value = true
    try {
      await repo.cancelarLote(lote)
    } catch {
      cancelando.value = false
      avisar('error', 'No se pudo cancelar la carga. Intentá nuevamente.')
    }
  }

  function aceptarResumen(): void {
    const huboCreados = (reporteFinal.value?.resumen?.creados ?? 0) > 0
    resumenAbierto.value = false
    reporteFinal.value = null
    // Se refresca el listado para mostrar los candidatos nuevos.
    if (huboCreados) void refrescarListado()
  }

  const porcentaje = computed(() => porcentajeLote(progreso.value.procesados, progreso.value.total))

  return {
    abierto, archivos, error, advertenciaLimite, procesando, cancelando, estado, progreso, porcentaje,
    resumenAbierto, reporteFinal,
    abrir, cerrar, agregar, quitar, iniciar, cancelar, aceptarResumen,
  }
}
