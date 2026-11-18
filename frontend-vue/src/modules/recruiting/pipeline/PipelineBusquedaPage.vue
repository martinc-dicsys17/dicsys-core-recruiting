<script setup lang="ts">
import { AlertCircle, AlertTriangle, CheckCircle, Loader2, X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { guardarAviso } from '../busquedas/aviso'
import CabeceraBusqueda from './components/CabeceraBusqueda.vue'
import EtapasProceso from './components/EtapasProceso.vue'
import FiltrosPipeline from './components/FiltrosPipeline.vue'
import ModalDescartar from './components/ModalDescartar.vue'
import ModalMoverEtapa from './components/ModalMoverEtapa.vue'
import ModalReingresar from './components/ModalReingresar.vue'
import TablaPipeline from './components/TablaPipeline.vue'
import { usePermisosPipeline } from './composables/usePermisosPipeline'
import { useCambiarEtapa, usePipelineBusqueda, type VariablesCambio } from './composables/usePipelineBusqueda'
import { estadoAlAvanzar, filtrarPorEtapa, normalizarEtapaNombre, obtenerSiguienteEtapa } from './etapas'
import { cambioAvance, cambioDescarte, cambioReingreso, idCandidato } from './movimientos'
import { alcanceDesdeQuery, ERROR_PIPELINE, RUTA_GESTION, searchSinFiltroDeEtapa, volverA } from './presentacion'
import type { CandidatoPipeline, DatosAvance, TipoToast } from './types'

/**
 * Pipeline de una búsqueda: sus candidatos por etapa, con mover de etapa (y adjunto), descartar y reingresar. Los
 * parámetros de la URL son los de la pantalla anterior (`alcance_candidatos`; `etapas` y `columna` llegan desde la
 * vista global y, como antes, el filtro arranca siempre en «Todas»).
 */
const ruta = useRoute()
const id = computed(() => String(ruta.params.id))
const alcance = computed(() => alcanceDesdeQuery(ruta.query))

const { permisos, listos: permisosListos } = usePermisosPipeline()
const { busqueda, candidatos } = usePipelineBusqueda(id, alcance)
const { cambiar, marcarGanada } = useCambiarEtapa(id, alcance)

const op = computed(() => busqueda.data.value)
const lista = computed<CandidatoPipeline[]>(() => candidatos.data.value ?? [])
const errorCandidatos = computed(() =>
  candidatos.isError.value ? candidatos.error.value?.message || ERROR_PIPELINE : null,
)
const listo = computed(() => !!op.value && permisosListos.value && !candidatos.isPending.value)

// Búsqueda Ganada = cerrada: solo consulta (el backend también rechaza cualquier cambio con 409).
const ganada = computed(() => String(op.value?.estado ?? '').trim().toLowerCase() === 'ganada')
const puedeMoverDescartar = computed(() => permisos.value.puede_mover_descartar && !ganada.value)
const puedeAsignarCandidatos = computed(() => permisos.value.puede_asignar_candidatos && !ganada.value)

watch(
  () => op.value?.titulo,
  () => {
    if (op.value) document.title = `Pipeline — ${op.value.titulo || 'Búsqueda'} | Recruiting | Dicsys Core`
  },
)

// Como la pantalla anterior: si la búsqueda no se puede abrir, se vuelve a Pipeline con el aviso.
watch(
  () => busqueda.isError.value,
  (fallo) => {
    if (!fallo) return
    const estado = (busqueda.error.value as { estado?: number } | null)?.estado
    guardarAviso({
      tipo: 'error',
      mensaje:
        estado === 403
          ? 'No tenés acceso a esta búsqueda: no la tenés asignada.'
          : 'La búsqueda solicitada no existe o no fue encontrada.',
    })
    window.location.assign(RUTA_GESTION)
  },
  { immediate: true },
)

// ---- Filtro por etapa: siempre arranca en «Todas» (también al cambiar el filtro de candidatos) ----
const etapaFiltro = ref('Todas')
watch(alcance, () => (etapaFiltro.value = 'Todas'))
const filtrados = computed(() => filtrarPorEtapa(lista.value, etapaFiltro.value))

// Las pantallas que se abren desde acá vuelven a la dirección de siempre de esta (sin el prefijo /v2).
const volverActual = computed(() => volverA(`/recruiting/oportunidades/${id.value}/pipeline`, window.location.search))
const volverCandidato = computed(() =>
  volverA(`/recruiting/oportunidades/${id.value}/pipeline`, searchSinFiltroDeEtapa(window.location.search)),
)
const enlaceFicha = computed(() => `/recruiting/oportunidades/${op.value?.id || 1}?volver=${volverActual.value}`)

// ---- Aviso (toast) ----
const toast = ref({ visible: false, tipo: 'success' as TipoToast, mensaje: '' })
let temporizador: ReturnType<typeof setTimeout> | undefined
function notificar(mensaje: string, tipo: TipoToast = 'success'): void {
  toast.value = { visible: true, tipo, mensaje }
  clearTimeout(temporizador)
  temporizador = setTimeout(() => (toast.value.visible = false), 3500)
}
onBeforeUnmount(() => clearTimeout(temporizador))

const recargar = (demora: number) => setTimeout(() => window.location.reload(), demora)

// ---- Modales ----
type Modal = 'mover' | 'descartar' | 'reingresar'
const modal = ref<Modal | null>(null)
const seleccionado = ref<CandidatoPipeline | null>(null)
const guardando = ref(false)

function abrir(tipo: Modal, candidato: CandidatoPipeline): void {
  if (candidato.es_anonimo) return
  if (tipo === 'mover' && !obtenerSiguienteEtapa(candidato.etapa_actual)) {
    notificar('El candidato se encuentra en una etapa terminal y no puede avanzar más.', 'warning')
    return
  }
  seleccionado.value = { ...candidato }
  modal.value = tipo
}

/** Guarda el cambio y, pase lo que pase, cierra el modal (como la pantalla anterior). */
async function guardar(
  variables: Omit<VariablesCambio, 'candidatoId'>,
  alTerminar: (ok: boolean, mensaje: string) => void,
  errorDeRed: string,
): Promise<void> {
  const candidato = seleccionado.value
  if (!candidato) return
  guardando.value = true
  try {
    const resultado = await cambiar.mutateAsync({ ...variables, candidatoId: idCandidato(candidato) })
    alTerminar(resultado.ok, resultado.ok ? '' : resultado.mensaje)
  } catch {
    notificar(errorDeRed, 'warning')
  } finally {
    guardando.value = false
    modal.value = null
    seleccionado.value = null
  }
}

function confirmarAvance(datos: DatosAvance): void {
  const nombre = seleccionado.value?.nombre ?? ''
  const ingreso = normalizarEtapaNombre(datos.nuevaEtapa) === 'Ingreso'
  const conAdjunto = datos.archivo ? ' con archivo adjunto' : ''
  void guardar(
    {
      cambio: cambioAvance(datos.nuevaEtapa, estadoAlAvanzar(datos.nuevaEtapa), datos.comentario, datos.pretension),
      archivo: datos.archivo,
      porDefecto: 'Error al mover etapa',
    },
    (ok, mensaje) => {
      if (ok && ingreso) {
        // El backend cerró la búsqueda como Ganada: se recarga para mostrarla bloqueada (solo consulta).
        marcarGanada()
        notificar(`Se movió a ${nombre} a Ingreso${conAdjunto}. La búsqueda quedó Ganada y cerrada.`)
        recargar(1500)
      } else if (ok) {
        notificar(`Se movió a ${nombre} a la etapa '${datos.nuevaEtapa}'${conAdjunto}.`)
      } else {
        notificar(mensaje, 'warning')
        // Si el Ingreso se registró pero falló el adjunto, la búsqueda ya quedó Ganada: se recarga para reflejarlo.
        if (ingreso) recargar(2500)
      }
    },
    'Error de red al actualizar etapa',
  )
}

function confirmarDescarte(datos: { motivo: string; comentario: string }): void {
  const nombre = seleccionado.value?.nombre ?? ''
  void guardar(
    {
      cambio: cambioDescarte(datos.motivo, datos.comentario),
      archivo: null,
      porDefecto: 'Error al descartar candidato',
      visible: { motivo_descarte: datos.motivo, feedback_etapa: datos.comentario },
    },
    (ok, mensaje) => notificar(ok ? `El candidato ${nombre} fue marcado como descartado.` : mensaje, 'warning'),
    'Error de red al registrar el descarte',
  )
}

function confirmarReingreso(motivo: string): void {
  const nombre = seleccionado.value?.nombre ?? ''
  void guardar(
    { cambio: cambioReingreso(motivo), archivo: null, porDefecto: 'Error al reingresar candidato' },
    (ok, mensaje) =>
      ok
        ? notificar(`El candidato ${nombre} reingresó exitosamente al proceso en 'Entrevista RRHH'.`)
        : notificar(mensaje, 'warning'),
    'Error de red al reingresar el candidato',
  )
}

const cerrarModal = () => (modal.value = null)
</script>

<template>
  <div class="animate-fade-in">
    <div
      v-if="errorCandidatos"
      class="mb-6 p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 flex items-center gap-3"
      data-testid="pipeline-error"
    >
      <AlertCircle class="w-5 h-5 flex-shrink-0" />
      <span>{{ errorCandidatos }}</span>
    </div>

    <!-- Toast Notification -->
    <Transition
      enter-active-class="transition ease-out duration-300"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-2"
    >
      <div
        v-if="toast.visible"
        role="status"
        data-testid="toast"
        class="fixed bottom-6 right-6 z-50 max-w-md shadow-xl rounded-xl border p-4 flex items-center gap-3"
        :class="toast.tipo === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-amber-50 border-amber-200 text-amber-800'"
      >
        <CheckCircle v-if="toast.tipo === 'success'" class="w-5 h-5 flex-shrink-0" />
        <AlertTriangle v-else class="w-5 h-5 flex-shrink-0" />
        <p class="text-sm font-medium">{{ toast.mensaje }}</p>
        <button type="button" class="ml-auto text-dark-400 hover:text-dark-600" aria-label="Cerrar" @click="toast.visible = false">
          <X class="w-4 h-4" />
        </button>
      </div>
    </Transition>

    <!-- Selector de vista (Vista global / Pipeline individual) -->
    <div class="flex flex-wrap justify-end items-center gap-2 mb-4">
      <FiltrosPipeline vista-actual="individual" />
    </div>

    <div v-if="!listo || !op" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
      <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando pipeline...</span>
    </div>

    <template v-else>
      <CabeceraBusqueda :op="op" :ganada="ganada" :enlace-ficha="enlaceFicha" />

      <EtapasProceso v-model="etapaFiltro" :candidatos="lista" />

      <TablaPipeline
        :busqueda-id="op.id"
        :candidatos="lista"
        :filtrados="filtrados"
        :etapa-filtro="etapaFiltro"
        :ganada="ganada"
        :puede-mover-descartar="puedeMoverDescartar"
        :puede-asignar-candidatos="puedeAsignarCandidatos"
        :volver-candidato="volverCandidato"
        :volver-actual="volverActual"
        @mover="abrir('mover', $event)"
        @descartar="abrir('descartar', $event)"
        @reingresar="abrir('reingresar', $event)"
        @ver-todas="etapaFiltro = 'Todas'"
      />
    </template>

    <ModalMoverEtapa
      v-if="modal === 'mover' && seleccionado"
      :candidato="seleccionado"
      :guardando="guardando"
      @cerrar="cerrarModal"
      @confirmar="confirmarAvance"
    />
    <ModalDescartar
      v-if="modal === 'descartar' && seleccionado"
      :candidato="seleccionado"
      :guardando="guardando"
      @cerrar="cerrarModal"
      @confirmar="confirmarDescarte"
    />
    <ModalReingresar
      v-if="modal === 'reingresar' && seleccionado"
      :candidato="seleccionado"
      :guardando="guardando"
      @cerrar="cerrarModal"
      @confirmar="confirmarReingreso"
    />
  </div>
</template>

<style scoped>
/* Tailwind 3 (pantalla anterior) pintaba el placeholder en gris-400; Tailwind 4 lo reinicia distinto. */
:deep(input::placeholder),
:deep(textarea::placeholder) {
  color: #9ca3af;
}
</style>
