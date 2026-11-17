<script setup lang="ts">
import { AlertCircle, ArrowLeft, Check, CheckCircle, Edit3, Loader2, Lock, X } from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { guardarAviso } from '../busquedas/aviso'
import AsignacionProceso from './components/AsignacionProceso.vue'
import CandidatosAsignados from './components/CandidatosAsignados.vue'
import CandidatosSugeridos from './components/CandidatosSugeridos.vue'
import DatosGenerales from './components/DatosGenerales.vue'
import ModalSmartMatching from './components/ModalSmartMatching.vue'
import { useAccionesBusqueda } from './composables/useAccionesBusqueda'
import { useBusquedaDetalle } from './composables/useBusquedaDetalle'
import { claseEstado, desgloseMatch, destinoAtras, formularioDesde, LISTADO, porcentajeMatch } from './presentacion'
import type { CandidatoSugerido, DesgloseMatch, FormularioBusqueda, TipoAviso } from './types'

const ruta = useRoute()
const id = computed(() => String(ruta.params.id))

// `?edit=true` (la ruta de edición de Flask redirige acá) abre la ficha directamente en modo edición.
const editando = ref(ruta.query.edit === 'true')
const guardando = ref(false)

const d = useBusquedaDetalle(id, editando)
const datos = computed(() => d.oportunidad.data.value)

watch(
  () => datos.value?.titulo,
  (titulo) => {
    if (titulo) document.title = `${titulo} — Recruiting | Dicsys Core`
  },
)

// Como la pantalla anterior: si la búsqueda no se puede abrir, se vuelve al listado con el aviso.
watch(
  () => d.oportunidad.isError.value,
  (fallo) => {
    if (!fallo) return
    const estado = (d.oportunidad.error.value as { estado?: number } | null)?.estado
    guardarAviso({
      tipo: 'error',
      mensaje:
        estado === 403
          ? 'No tenés acceso a esta búsqueda: no la tenés asignada.'
          : 'La búsqueda solicitada no existe o no fue encontrada.',
    })
    window.location.assign(LISTADO)
  },
  { immediate: true },
)

// «Volver» conserva el destino de origen (?volver=, solo rutas internas de Recruiting); si no, el listado.
const atras = destinoAtras(ruta.query.volver)
// Las fichas de candidato y el alta vuelven acá: la dirección de esta pantalla de siempre (sin el prefijo /v2).
const volverActual = computed(() => `${LISTADO}/${id.value}${window.location.search}`)

// ---- Avisos (toast) ----
const toast = ref({ visible: false, tipo: 'success' as TipoAviso, mensaje: '' })
let temporizador: ReturnType<typeof setTimeout> | null = null
function mostrarToast(tipo: TipoAviso, mensaje: string): void {
  toast.value = { visible: true, tipo, mensaje }
  if (temporizador) clearTimeout(temporizador)
  temporizador = setTimeout(() => (toast.value.visible = false), 4000)
}
onBeforeUnmount(() => temporizador && clearTimeout(temporizador))

const acciones = useAccionesBusqueda(id, mostrarToast)

// ---- Edición: solo Descripción y Skills deseadas se guardan; el resto se muestra bloqueado ----
const form = ref<FormularioBusqueda | null>(null)
watch(
  datos,
  (nuevos) => {
    if (nuevos && !form.value) form.value = formularioDesde(nuevos)
  },
  { immediate: true },
)
function iniciarEdicion(): void {
  if (datos.value) form.value = formularioDesde(datos.value)
  editando.value = true
}
function cancelarEdicion(): void {
  if (datos.value) form.value = formularioDesde(datos.value)
  editando.value = false
}
async function guardarCambios(): Promise<void> {
  if (!form.value) return
  guardando.value = true
  try {
    await acciones.guardar.mutateAsync({
      skills_deseadas: form.value.skills_deseadas,
      descripcion: form.value.descripcion.trim() || null,
    })
    editando.value = false
  } catch {
    // el aviso de error ya lo mostró la mutación
  } finally {
    guardando.value = false
  }
}

// ---- Asignaciones: devuelven si salió bien para que el panel se cierre ----
const intentar = async (accion: () => Promise<unknown>): Promise<boolean> => {
  try {
    await accion()
    return true
  } catch {
    return false
  }
}
const guardarReclutador = (nombre: string) => intentar(() => acciones.asignarReclutador.mutateAsync(nombre))
const guardarExterno = (externoId: string) => intentar(() => acciones.asignarExterno.mutateAsync(externoId))
const quitarExterno = () => intentar(() => acciones.quitarExterno.mutateAsync())

// ---- Smart Matching ----
const desglose = ref<DesgloseMatch | null>(null)
function verDesglose(c: CandidatoSugerido): void {
  if (datos.value) desglose.value = desgloseMatch(datos.value, c)
}
function postular(c: CandidatoSugerido): void {
  if (acciones.postular.isPending.value) return
  const minimo = d.matchMinimo.value
  if (porcentajeMatch(c) < minimo && !window.confirm(`¿Estás seguro de asignarlo aunque tiene menos de ${minimo}%?`)) return
  acciones.postular.mutate(c.id)
}
const postulandoId = computed(() => (acciones.postular.isPending.value ? (acciones.postular.variables.value ?? null) : null))

const listo = computed(() => d.oportunidad.isSuccess.value && d.permisosListos.value && !!form.value)
</script>

<template>
  <div class="p-2 lg:p-4 w-full animate-fade-in">
    <!-- Aviso (toast) -->
    <div
      v-if="toast.visible"
      role="status"
      class="fixed bottom-6 right-6 z-50 flex items-center gap-2.5 px-4 py-3 rounded-xl shadow-xl border text-sm font-medium"
      :class="toast.tipo === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'"
      data-testid="toast"
    >
      <CheckCircle v-if="toast.tipo === 'success'" class="w-5 h-5 flex-shrink-0" />
      <AlertCircle v-else class="w-5 h-5 flex-shrink-0" />
      <span>{{ toast.mensaje }}</span>
    </div>

    <div v-if="!listo || !datos || !form" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
      <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando búsqueda...</span>
    </div>

    <template v-else>
      <!-- Encabezado: título y botones (lectura o edición) -->
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
        <div v-if="!editando">
          <div class="flex items-center gap-3 mb-1">
            <h1 class="text-2xl font-bold text-dark-900" data-testid="busqueda-titulo">{{ datos.titulo || 'Búsqueda' }}</h1>
            <span class="px-2.5 py-0.5 text-xs font-semibold rounded-lg border" :class="claseEstado(datos.estado)">
              {{ datos.estado || 'Abierta' }}
            </span>
          </div>
          <p class="text-sm text-dark-500">
            <span>{{ datos.cliente || 'Cliente' }}</span> ·
            <span>Reclutador: <span>{{ datos.recruiter_nombre || 'Sin asignar' }}</span></span>
          </p>
        </div>
        <div v-else>
          <div class="flex items-center gap-2 mb-1">
            <span class="px-2.5 py-1 text-xs font-bold uppercase rounded-lg bg-amber-100 text-amber-800">Modo Edición</span>
            <h1 class="text-2xl font-bold text-dark-900">Editar Búsqueda</h1>
          </div>
          <p class="text-sm text-dark-500">Modificá los campos de la vacante y guardá los cambios para actualizar la búsqueda.</p>
        </div>

        <div class="flex items-center gap-2">
          <div v-if="!editando" class="flex items-center gap-2.5">
            <button
              v-if="!d.ganada.value"
              type="button"
              title="Editar Búsqueda"
              data-testid="editar"
              class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-semibold px-4 py-2.5 rounded-xl shadow-soft hover:shadow-md transition-all cursor-pointer text-sm"
              @click="iniciarEdicion"
            >
              <Edit3 class="w-4 h-4 text-white" />
              <span>Editar</span>
            </button>
            <a
              :href="atras"
              title="Volver a Búsquedas"
              data-testid="volver"
              class="inline-flex items-center gap-2 bg-white hover:bg-dark-50 text-dark-700 border border-dark-200 font-semibold px-4 py-2.5 rounded-xl shadow-soft transition-colors cursor-pointer text-sm"
            >
              <ArrowLeft class="w-4 h-4 text-dark-600" />
              <span>Volver</span>
            </a>
          </div>
          <div v-else class="flex items-center gap-2">
            <button
              type="button"
              :disabled="guardando"
              data-testid="cancelar-edicion"
              class="inline-flex items-center gap-2 bg-white hover:bg-dark-50 text-dark-700 border border-dark-200 font-semibold px-4 py-2.5 rounded-xl shadow-soft transition-colors cursor-pointer text-sm disabled:opacity-50"
              @click="cancelarEdicion"
            >
              <X class="w-4 h-4 text-dark-600" />
              <span>Cancelar</span>
            </button>
            <button
              type="button"
              :disabled="guardando"
              data-testid="guardar-cambios"
              class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-semibold px-5 py-2.5 rounded-xl shadow-soft transition-colors cursor-pointer text-sm disabled:opacity-50"
              @click="guardarCambios"
            >
              <Check v-if="!guardando" class="w-4 h-4 text-white" />
              <span v-else class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full"></span>
              <span>{{ guardando ? 'Guardando...' : 'Guardar Cambios' }}</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Búsqueda Ganada: cerrada al confirmar el Ingreso de un candidato (solo consulta) -->
      <div
        v-if="d.ganada.value"
        data-testid="aviso-busqueda-ganada"
        class="flex items-start gap-3 mb-6 px-4 py-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-800 text-sm"
      >
        <Lock class="w-5 h-5 flex-shrink-0 mt-0.5" />
        <div>
          <p class="font-bold">Búsqueda Ganada y cerrada</p>
          <p class="text-xs mt-0.5">
            Un candidato llegó a la etapa Ingreso. La búsqueda queda solo para consulta: no se pueden agregar candidatos,
            moverlos de etapa ni modificar el proceso de selección.
          </p>
        </div>
      </div>

      <div class="space-y-6">
        <div class="grid lg:grid-cols-2 gap-6">
          <DatosGenerales
            v-model:form="form"
            :datos="datos"
            :editando="editando"
            :skills-catalogo="d.skills.data.value ?? []"
            :habilidades-catalogo="d.habilidades.data.value ?? []"
            :perfiles-puesto="d.perfilesPuesto.data.value ?? []"
            :perfiles-error="d.perfilesPuesto.isError.value"
            :perfiles-cargados="d.perfilesPuesto.isSuccess.value"
          />
          <AsignacionProceso
            v-model:form="form"
            :datos="datos"
            :editando="editando"
            :reclutadores="d.reclutadores.data.value ?? []"
            :externos="d.externos.data.value ?? []"
            :puede-asignar-reclutador="d.puedeAsignarReclutador.value"
            :puede-administrar-externos="d.puedeAdministrarExternos.value"
            :ve-lider-tipo-fecha="d.permisos.value.puede_ver_lider_tipo_fecha_busqueda"
            :guardando-reclutador="acciones.asignarReclutador.isPending.value"
            :guardando-externo="acciones.asignarExterno.isPending.value || acciones.quitarExterno.isPending.value"
            :guardar-reclutador="guardarReclutador"
            :guardar-externo="guardarExterno"
            :quitar-externo="quitarExterno"
            @aviso="mostrarToast"
          />
        </div>

        <CandidatosAsignados
          :busqueda-id="datos.id"
          :candidatos="d.asignados.data.value ?? []"
          :volver-actual="volverActual"
          :es-externo="d.permisos.value.es_externo"
          :puede-cargar-cv="d.puedeCargarCv.value"
          :cargando-cv="acciones.cargarCv.isPending.value"
          @cargar-cv="acciones.cargarCv.mutate($event)"
        />

        <CandidatosSugeridos
          v-if="d.veSmartMatching.value"
          :datos="datos"
          :sugeridos="d.sugeridos.data.value ?? []"
          :match-minimo="d.matchMinimo.value"
          :volver-actual="volverActual"
          :postulando-id="postulandoId"
          @postular="postular"
          @desglose="verDesglose"
        />
      </div>

      <ModalSmartMatching
        v-if="d.veSmartMatching.value && desglose"
        :desglose="desglose"
        :match-minimo="d.matchMinimo.value"
        @cerrar="desglose = null"
      />
    </template>
  </div>
</template>

<style scoped>
/* Los campos de la pantalla anterior (Tailwind 3) usaban texto negro y placeholder gris-400; Tailwind 4 los reinicia distinto. */
:deep(input::placeholder),
:deep(textarea::placeholder) {
  color: #9ca3af;
}
:deep(input:not([class*='text-']):not([type='checkbox'])),
:deep(textarea:not([class*='text-'])) {
  color: #000;
}
</style>
