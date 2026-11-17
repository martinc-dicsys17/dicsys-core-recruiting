<script setup lang="ts">
import { Info, UserCheck, UserPlus, UserX } from '@lucide/vue'
import { computed, ref } from 'vue'

import { claseEstado, formatearFecha, formatearFechaHora } from '../presentacion'
import type { ExternoDisponible, FormularioBusqueda, Oportunidad, TipoAviso } from '../types'

/**
 * Tarjeta «Asignación del Proceso»: reclutador, usuario externo, líder, estado, tipo y tiempos. Con permiso se puede
 * reasignar el reclutador y asignar o quitar el usuario externo (cada acción devuelve si salió bien para cerrar el panel).
 */
const props = defineProps<{
  datos: Oportunidad
  editando: boolean
  reclutadores: string[]
  externos: ExternoDisponible[]
  puedeAsignarReclutador: boolean
  puedeAdministrarExternos: boolean
  veLiderTipoFecha: boolean
  guardandoReclutador: boolean
  guardandoExterno: boolean
  guardarReclutador: (nombre: string) => Promise<boolean>
  guardarExterno: (externoId: string) => Promise<boolean>
  quitarExterno: () => Promise<boolean>
}>()
const emit = defineEmits<{ aviso: [tipo: TipoAviso, mensaje: string] }>()
const form = defineModel<FormularioBusqueda>('form', { required: true })

const DATO = 'text-xs font-semibold text-dark-400 mb-0.5'
const ETIQUETA = 'block text-xs font-semibold text-dark-600 mb-1'
const ENTRADA =
  'w-full px-3.5 py-2 rounded-xl border border-dark-200 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 text-sm'
const BOTON_ASIGNAR =
  'inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-primary-600 bg-primary-50 hover:bg-primary-100 rounded-lg transition-colors cursor-pointer'

const reclutadorActual = computed(() => props.datos.recruiter_nombre || '')

// Se conserva visible el reclutador actual aunque ya no esté activo en el catálogo.
const opcionesReclutador = computed(() => {
  const actual = reclutadorActual.value
  return actual && !props.reclutadores.includes(actual) ? [actual, ...props.reclutadores] : props.reclutadores
})

// En edición (bloqueado) el combo muestra el reclutador de la búsqueda o, si no tiene, la primera opción (como el <select> anterior).
const reclutadorMostrado = computed(() =>
  opcionesReclutador.value.includes(form.value.recruiter_nombre) ? form.value.recruiter_nombre : (opcionesReclutador.value[0] ?? ''),
)

// ---- Reclutador ----
const reasignando = ref(false)
const reclutadorSeleccionado = ref('')
function iniciarReasignacion(): void {
  reclutadorSeleccionado.value = reclutadorActual.value
  reasignando.value = true
}
async function confirmarReclutador(): Promise<void> {
  if (!reclutadorSeleccionado.value) return emit('aviso', 'error', 'Seleccioná un reclutador.')
  if (await props.guardarReclutador(reclutadorSeleccionado.value)) reasignando.value = false
}

// ---- Usuario externo ----
const gestionandoExterno = ref(false)
const externoSeleccionado = ref('')
function iniciarGestionExterno(): void {
  externoSeleccionado.value = props.datos.externo_id || ''
  gestionandoExterno.value = true
}
async function confirmarExterno(): Promise<void> {
  if (!externoSeleccionado.value) return emit('aviso', 'error', 'Selecciona un usuario externo.')
  if (externoSeleccionado.value === props.datos.externo_id) {
    gestionandoExterno.value = false
    return
  }
  if (
    props.datos.externo_id &&
    !window.confirm('Se reemplazara el usuario externo asignado actualmente. Queres continuar?')
  )
    return
  if (await props.guardarExterno(externoSeleccionado.value)) gestionandoExterno.value = false
}
async function confirmarQuitarExterno(): Promise<void> {
  if (!props.datos.externo_id) return
  if (
    !window.confirm(
      'Se quitara la asignacion del usuario externo. La busqueda y sus candidatos no se modifican. Queres continuar?',
    )
  )
    return
  if (await props.quitarExterno()) {
    externoSeleccionado.value = ''
    gestionandoExterno.value = false
  }
}

const textoExterno = computed(() =>
  props.datos.externo_nombre
    ? props.datos.externo_nombre + (props.datos.externo_email ? ` (${props.datos.externo_email})` : '')
    : 'Sin asignar',
)
const qActivos = computed(() => props.datos.q_activos ?? 0)
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-6">
    <h2 class="text-base font-bold text-dark-900 pb-2 mb-4 border-b border-dark-100 flex items-center gap-2">
      <UserCheck class="w-4 h-4 text-primary-600" />
      <span>Asignación del Proceso</span>
    </h2>

    <!-- Modo lectura -->
    <div v-if="!editando" class="grid sm:grid-cols-2 gap-4 text-sm">
      <div>
        <p :class="DATO">Recruiter Asignado</p>
        <div class="flex items-center gap-2 flex-wrap">
          <p class="font-semibold text-dark-800">{{ reclutadorActual || '—' }}</p>
          <button v-if="puedeAsignarReclutador && !reasignando" type="button" :class="BOTON_ASIGNAR" @click="iniciarReasignacion">
            <UserPlus class="w-3 h-3" />
            <span>{{ reclutadorActual ? 'Cambiar' : 'Asignar' }}</span>
          </button>
        </div>
        <div v-if="puedeAsignarReclutador && reasignando" class="flex items-center gap-2 mt-1.5 flex-wrap">
          <select
            v-model="reclutadorSeleccionado"
            class="px-3 py-1.5 rounded-lg border border-dark-200 text-sm text-dark-700 bg-white cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          >
            <option value="" disabled>Seleccionar reclutador</option>
            <option v-for="nombre in opcionesReclutador" :key="nombre" :value="nombre">{{ nombre }}</option>
          </select>
          <button
            type="button"
            :disabled="guardandoReclutador"
            class="px-3 py-1.5 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg cursor-pointer disabled:opacity-50"
            @click="confirmarReclutador"
          >
            {{ guardandoReclutador ? 'Guardando...' : 'Guardar' }}
          </button>
          <button
            type="button"
            :disabled="guardandoReclutador"
            class="px-3 py-1.5 text-xs font-semibold text-dark-600 hover:bg-dark-100 rounded-lg cursor-pointer"
            @click="reasignando = false"
          >
            Cancelar
          </button>
        </div>
      </div>
      <div>
        <p :class="DATO">Fecha de asignación</p>
        <p class="font-mono text-dark-700">
          {{ datos.fecha_asignacion ? formatearFechaHora(datos.fecha_asignacion) : 'Sin asignar' }}
        </p>
      </div>

      <!-- Recruiter externo (opcional, máximo uno) -->
      <div id="seccion-recruiter-externo" class="sm:col-span-2">
        <p :class="DATO">Recruiter Externo</p>
        <div class="flex items-center gap-2 flex-wrap">
          <p id="externo-asignado-nombre" class="font-semibold text-dark-800">{{ textoExterno }}</p>
          <template v-if="puedeAdministrarExternos">
            <button v-if="!gestionandoExterno" id="btn-gestionar-externo" type="button" :class="BOTON_ASIGNAR" @click="iniciarGestionExterno">
              <UserPlus class="w-3 h-3" />
              <span>{{ datos.externo_id ? 'Cambiar' : 'Asignar' }}</span>
            </button>
            <button
              v-if="datos.externo_id && !gestionandoExterno"
              id="btn-quitar-externo"
              type="button"
              :disabled="guardandoExterno"
              class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
              @click="confirmarQuitarExterno"
            >
              <UserX class="w-3 h-3" />
              <span>Quitar asignacion</span>
            </button>
          </template>
        </div>
        <div v-if="puedeAdministrarExternos && gestionandoExterno" class="flex items-center gap-2 mt-1.5 flex-wrap">
          <select
            id="select-externo"
            v-model="externoSeleccionado"
            class="px-3 py-1.5 rounded-lg border border-dark-200 text-sm text-dark-700 bg-white cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
          >
            <option value="" disabled>Seleccionar usuario externo</option>
            <option v-for="u in externos" :key="u.id" :value="u.id">{{ u.nombre }} ({{ u.email }})</option>
          </select>
          <button
            id="btn-guardar-externo"
            type="button"
            :disabled="guardandoExterno"
            class="px-3 py-1.5 text-xs font-semibold text-white bg-primary-600 hover:bg-primary-700 rounded-lg cursor-pointer disabled:opacity-50"
            @click="confirmarExterno"
          >
            {{ guardandoExterno ? 'Guardando...' : 'Confirmar' }}
          </button>
          <button
            type="button"
            :disabled="guardandoExterno"
            class="px-3 py-1.5 text-xs font-semibold text-dark-600 hover:bg-dark-100 rounded-lg cursor-pointer"
            @click="gestionandoExterno = false"
          >
            Cancelar
          </button>
          <p v-if="!externos.length" class="text-xs text-dark-400 w-full">No hay usuarios habilitados en el grupo Externos.</p>
        </div>
      </div>

      <div v-if="veLiderTipoFecha">
        <p :class="DATO">Líder / Hiring Manager</p>
        <p class="font-semibold text-dark-800">{{ datos.lider_nombre || 'Sin líder asignado' }}</p>
      </div>
      <div>
        <p :class="DATO">Estado Operativo</p>
        <div class="pt-0.5">
          <span class="px-2.5 py-0.5 text-xs font-semibold rounded-lg border inline-block" :class="claseEstado(datos.estado)">
            {{ datos.estado || 'Abierta' }}
          </span>
        </div>
      </div>

      <template v-if="veLiderTipoFecha">
        <div>
          <p :class="DATO">Tipo de Oportunidad</p>
          <p class="font-medium text-dark-800">{{ datos.tipo || 'Efectiva' }}</p>
        </div>
        <div>
          <p :class="DATO">Fecha de creación</p>
          <p class="font-mono text-dark-700">{{ formatearFecha(datos.fecha_creacion) }}</p>
        </div>
      </template>

      <div>
        <p :class="DATO">Días Abierta</p>
        <div class="pt-0.5">
          <span
            class="px-2 py-0.5 text-xs font-bold rounded-lg inline-block font-mono"
            :class="
              (datos.dias_abierta ?? 0) > 30
                ? 'bg-red-50 text-red-700 border border-red-200'
                : 'bg-dark-100 text-dark-700 border border-dark-200/60'
            "
          >
            <span>{{ datos.dias_abierta ?? 0 }}</span> días
          </span>
        </div>
      </div>
      <div>
        <p :class="DATO">Candidatos Activos en Proceso</p>
        <div class="pt-0.5">
          <span class="px-2.5 py-0.5 text-xs font-bold rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 font-mono inline-block">
            <span>{{ qActivos }}</span> activos
          </span>
        </div>
      </div>
    </div>

    <!-- Modo edición (bloqueado) -->
    <div v-else class="grid sm:grid-cols-2 gap-4 text-sm">
      <fieldset disabled class="contents">
        <div>
          <label :class="ETIQUETA">Recruiter Asignado</label>
          <select :value="reclutadorMostrado" :class="`${ENTRADA} text-dark-700 bg-white cursor-pointer`">
            <option v-for="nombre in opcionesReclutador" :key="nombre" :value="nombre">{{ nombre }}</option>
          </select>
        </div>
        <div v-if="veLiderTipoFecha">
          <label :class="ETIQUETA">Líder / Hiring Manager</label>
          <input v-model="form.lider_nombre" type="text" placeholder="Ej: Martin Israilevich, Maria Jose Padin..." :class="ENTRADA" />
        </div>
        <div>
          <label :class="ETIQUETA">Estado de la Búsqueda</label>
          <select v-model="form.estado" :class="`${ENTRADA} text-dark-700 cursor-pointer`">
            <option value="Abierta">Abierta</option>
            <option value="Pre-ingreso">Pre-ingreso</option>
            <option value="Suspendida">Suspendida</option>
            <option value="Ganada">Ganada</option>
            <option value="Cancelada">Cancelada</option>
          </select>
        </div>
        <div>
          <label :class="ETIQUETA">Prioridad</label>
          <select v-model="form.prioridad" :class="`${ENTRADA} text-dark-700 cursor-pointer`">
            <option value="Critica">Crítica</option>
            <option value="Alta">Alta</option>
            <option value="Media">Media</option>
            <option value="Baja">Baja</option>
          </select>
        </div>
        <template v-if="veLiderTipoFecha">
          <div>
            <label :class="ETIQUETA">Tipo de Oportunidad</label>
            <select v-model="form.tipo" :class="`${ENTRADA} text-dark-700 cursor-pointer`">
              <option value="Efectiva">Efectiva</option>
              <option value="Potencial">Potencial</option>
            </select>
          </div>
          <div>
            <label :class="ETIQUETA">Fecha de creación</label>
            <input
              type="date"
              :value="datos.fecha_creacion ?? ''"
              readonly
              disabled
              class="h-10 w-full px-3.5 py-2 rounded-xl border border-dark-200 bg-dark-50 cursor-not-allowed text-sm text-dark-500"
            />
          </div>
        </template>
        <div>
          <p class="text-xs font-semibold text-dark-400 mb-1">Días Abierta (calculado)</p>
          <p class="font-mono text-dark-700 pt-2 text-sm"><span>{{ datos.dias_abierta ?? 0 }}</span> días transcurridos</p>
        </div>
      </fieldset>
    </div>

    <div class="mt-5 pt-4 border-t border-dark-100 text-xs text-dark-500 flex items-center gap-2">
      <Info class="w-4 h-4 text-dark-400 flex-shrink-0" />
      <span>Los tiempos de apertura se contabilizan desde la fecha de asignación hasta la cobertura o cierre de la búsqueda.</span>
    </div>
  </div>
</template>

<style scoped>
/* Campos bloqueados (fieldset disabled): como en la pantalla anterior, los inputs de texto llevan el fondo gris tenue
   del navegador; los combos conservan su fondo. */
fieldset:disabled input:not([class*='bg-']) {
  background-color: rgba(239, 239, 239, 0.3);
}
fieldset:disabled input {
  color: rgb(0, 0, 0);
}
/* El navegador atenúa los combos deshabilitados (Tailwind 4 lo reinicia a opacidad 1). */
fieldset:disabled select {
  opacity: 0.7;
}
fieldset:disabled select:not([class*='text-']) {
  color: rgb(0, 0, 0);
}
</style>
