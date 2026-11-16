<script setup lang="ts">
import {
  AlertCircle,
  ArrowLeft,
  Briefcase,
  CheckCircle,
  Download,
  Edit3,
  ExternalLink,
  FileText,
  Loader2,
  ShieldBan,
  User,
} from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { destinoVolver } from '../candidato-nuevo/validacion'
import { urlCv } from '../candidatos/api/candidatos.repository'
import { useCandidatoDetalle } from './composables/useCandidatoDetalle'
import {
  claseEstado,
  DISPONIBILIDADES,
  formatoSalarioLectura,
  MODALIDADES,
  mostrarUbicacionRegistrada,
  nombreCv,
  SENIORITY,
  ubicacionSegunCatalogo,
  valoresFicha,
} from './presentacion'

const ruta = useRoute()
const id = computed(() => String(ruta.params.id))
const { candidato, provincias, ciudades, perfilesPuesto, provinciaId, ciudadId, listo } = useCandidatoDetalle(id)

// «Volver» conserva el destino de origen (?volver=), validado como en la pantalla anterior; si no, el listado.
const destinoAtras = destinoVolver(ruta.query.volver, '')

const datos = computed(() => candidato.data.value)
const v = computed(() => (datos.value ? valoresFicha(datos.value) : null))
const nombreCompleto = computed(() => (datos.value ? `${datos.value.nombre} ${datos.value.apellido || ''}` : ''))

watch(nombreCompleto, (nombre) => {
  if (nombre) document.title = `${nombre.trim()} — Reclutamiento - Dicsys Core`
})

// Editar: la edición sigue siendo la de la pantalla anterior (se abre ya en modo edición).
const enlaceEditar = computed(() => {
  const consulta = new URLSearchParams({ editar: '1' })
  if (ruta.query.volver) consulta.set('volver', String(ruta.query.volver))
  return `/recruiting/candidatos/${id.value}?${consulta.toString()}`
})

// ---- Ubicación (provincia y ciudad guardadas, según los catálogos) ----
const provinciaNombre = computed(
  () => provincias.data.value?.find((p) => p.provincia_id === provinciaId.value)?.nombre ?? '',
)
const ciudadNombre = computed(() => ciudades.data.value?.find((c) => c.ciudad_id === ciudadId.value)?.nombre ?? '')
const segunCatalogo = computed(() =>
  datos.value ? ubicacionSegunCatalogo(datos.value, provincias.data.value ?? [], ciudades.data.value ?? []) : '',
)

// ---- Aviso de perfiles de puesto ----
const perfilesError = computed(() => perfilesPuesto.isError.value)
const perfilesVacio = computed(() => perfilesPuesto.isSuccess.value && !perfilesPuesto.data.value?.length)

// ---- Agregar a Blacklist: hoy solo confirma y avisa que todavía no está disponible (igual que antes) ----
const confirmarBlacklist = ref(false)
const toast = ref({ visible: false, tipo: 'success' as 'success' | 'error', mensaje: '' })
let temporizador: ReturnType<typeof setTimeout> | null = null

function mostrarToast(tipo: 'success' | 'error', mensaje: string): void {
  toast.value = { visible: true, tipo, mensaje }
  if (temporizador) clearTimeout(temporizador)
  temporizador = setTimeout(() => (toast.value.visible = false), 3500)
}
// Escape cierra el modal estando donde esté el foco (en la pantalla anterior: @keydown.escape.window de Alpine; en Vue
// ese modificador no existe, así que se escucha el teclado de la ventana).
function alTeclear(evento: KeyboardEvent): void {
  if (evento.key === 'Escape') confirmarBlacklist.value = false
}
onMounted(() => window.addEventListener('keydown', alTeclear))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', alTeclear)
  if (temporizador) clearTimeout(temporizador)
})

function agregarABlacklist(): void {
  confirmarBlacklist.value = false
  mostrarToast('error', 'El alta a Blacklist todavía no está disponible.')
}

const CAMPO =
  'w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors bg-dark-50/80 text-dark-800 border-dark-200 cursor-default'
const ETIQUETA = 'block text-xs font-semibold text-dark-600 mb-1'
const TITULO_SECCION = 'text-base font-bold text-dark-900 pb-2 mb-4 border-b border-dark-100 flex items-center gap-2'
const CHIP = 'inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg bg-dark-200/60 text-dark-800 border border-dark-300/60'
const CONTENEDOR_CHIPS = 'flex flex-wrap gap-1.5 p-2 bg-dark-50 border border-dark-200 rounded-xl min-h-[44px] items-center'
</script>

<template>
  <div class="w-full max-w-none animate-fade-in p-2 lg:p-6">
    <!-- Modal de confirmación: agregar a Blacklist -->
    <div
      v-if="confirmarBlacklist"
      class="fixed inset-0 z-50 flex items-center justify-center bg-dark-900/50 p-4"
      @click.self="confirmarBlacklist = false"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="titulo-modal-blacklist"
        class="w-full max-w-md rounded-2xl border border-dark-200 bg-white p-6 shadow-xl"
      >
        <div class="flex items-start gap-3">
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#a3162b]">
            <ShieldBan class="h-5 w-5 text-white" />
          </span>
          <div>
            <h2 id="titulo-modal-blacklist" class="text-lg font-bold text-dark-900">¿Agregar a Blacklist?</h2>
            <p class="mt-1 text-sm text-dark-600">
              ¿Estás seguro de mandar a
              <strong>{{ nombreCompleto }}</strong>
              a la Blacklist?
            </p>
          </div>
        </div>
        <div class="mt-6 flex justify-end gap-2">
          <button
            type="button"
            class="cursor-pointer rounded-xl border border-dark-200 bg-white px-4 py-2.5 text-sm font-semibold text-dark-700 hover:bg-dark-50"
            @click="confirmarBlacklist = false"
          >
            Cancelar
          </button>
          <button
            type="button"
            data-testid="confirmar-blacklist"
            class="cursor-pointer rounded-xl bg-[#a3162b] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#7f1526]"
            @click="agregarABlacklist"
          >
            Sí, agregar
          </button>
        </div>
      </div>
    </div>

    <!-- Aviso (toast) -->
    <div
      v-if="toast.visible"
      role="status"
      class="fixed right-6 bottom-6 z-50 flex items-center gap-2.5 rounded-xl border px-4 py-3 text-sm font-medium shadow-xl"
      :class="toast.tipo === 'success' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-800'"
    >
      <CheckCircle v-if="toast.tipo === 'success'" class="h-5 w-5 shrink-0" />
      <AlertCircle v-else class="h-5 w-5 shrink-0" />
      <span>{{ toast.mensaje }}</span>
    </div>

    <!-- Error al cargar la ficha -->
    <div v-if="candidato.isError.value" data-testid="detalle-error">
      <div class="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
        <AlertCircle class="h-5 w-5 shrink-0" />
        <span class="flex-1">{{ candidato.error.value?.message }}</span>
        <a
          :href="destinoAtras"
          class="inline-flex items-center gap-2 rounded-xl border border-dark-200 bg-white px-4 py-2.5 text-sm font-semibold text-dark-700 shadow-soft hover:bg-dark-50"
        >
          <ArrowLeft class="h-4 w-4 text-dark-600" /><span>Volver</span>
        </a>
      </div>
    </div>

    <div v-else-if="!listo || !datos || !v" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
      <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando ficha del candidato...</span>
    </div>

    <template v-else>
      <!-- Encabezado con título y botones de acción -->
      <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="mb-1 flex items-center gap-3">
            <h1 class="text-2xl font-bold text-dark-900" data-testid="detalle-nombre">{{ nombreCompleto }}</h1>
            <span class="rounded-lg px-2.5 py-0.5 text-xs font-semibold" :class="claseEstado(datos.estado)">
              {{ datos.estado }}
            </span>
          </div>
          <p class="text-sm text-dark-500">{{ datos.headline || 'Ficha del Candidato' }}</p>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            id="btn-agregar-blacklist"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[#a3162b] px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-[#7f1526]"
            @click="confirmarBlacklist = true"
          >
            <ShieldBan class="h-4 w-4 text-white" />
            <span>Agregar a Blacklist</span>
          </button>
          <a
            :href="enlaceEditar"
            data-testid="editar"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700"
          >
            <Edit3 class="h-4 w-4 text-white" />
            <span>Editar</span>
          </a>
          <a
            :href="destinoAtras"
            title="Volver"
            data-testid="volver"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-dark-200 bg-white px-4 py-2.5 text-sm font-semibold text-dark-700 shadow-soft transition-colors hover:bg-dark-50"
          >
            <ArrowLeft class="h-4 w-4 text-dark-600" />
            <span>Volver</span>
          </a>
        </div>
      </div>

      <!-- Ficha (modo lectura) -->
      <div class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
        <form class="space-y-6 p-6 lg:p-8" @submit.prevent>
          <!-- Sección 1: Datos Personales -->
          <div>
            <h2 :class="TITULO_SECCION">
              <User class="h-4 w-4 text-primary-600" />
              <span>Datos Personales y Contacto</span>
            </h2>
            <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label :class="ETIQUETA">Nombres *</label>
                <input type="text" disabled :value="v.nombre" placeholder="Nombres" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Apellido *</label>
                <input type="text" disabled :value="v.apellido" placeholder="Apellido" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Email *</label>
                <input type="email" disabled :value="v.email" placeholder="ejemplo@correo.com" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Teléfono *</label>
                <input type="text" disabled :value="v.telefono" placeholder="ej: +54 9 351 1234567" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Provincia</label>
                <select disabled :class="CAMPO" data-testid="detalle-provincia">
                  <option value="">{{ provinciaNombre || 'Seleccionar provincia...' }}</option>
                </select>
              </div>
              <div>
                <label :class="ETIQUETA">Ciudad</label>
                <select disabled :class="CAMPO" data-testid="detalle-ciudad">
                  <option value="">{{ ciudadNombre || 'Seleccionar ciudad...' }}</option>
                </select>
                <p v-if="mostrarUbicacionRegistrada(datos, segunCatalogo)" class="mt-1 text-[11px] text-dark-400">
                  Ubicación registrada: <span>{{ datos.ubicacion }}</span>
                </p>
              </div>
              <div>
                <label :class="ETIQUETA">Perfil de LinkedIn</label>
                <div class="relative">
                  <input type="text" disabled :value="v.linkedin" placeholder="https://linkedin.com/in/usuario" :class="CAMPO" />
                  <a
                    v-if="v.linkedin"
                    :href="v.linkedin"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="absolute top-1/2 right-2.5 -translate-y-1/2 rounded-lg p-1 text-primary-600 transition-colors hover:bg-primary-50 hover:text-primary-700"
                    title="Abrir perfil de LinkedIn"
                  >
                    <ExternalLink class="h-4 w-4" />
                  </a>
                </div>
              </div>
              <div>
                <label :class="ETIQUETA">DNI</label>
                <input type="text" disabled :value="v.dni" placeholder="—" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Fecha de Nacimiento</label>
                <input type="text" disabled :value="v.fechaNacimiento" maxlength="10" placeholder="DD-MM-YYYY" :class="CAMPO" />
              </div>
            </div>
          </div>

          <!-- Sección 2: Perfil Profesional -->
          <div class="pt-4">
            <h2 :class="TITULO_SECCION">
              <Briefcase class="h-4 w-4 text-primary-600" />
              <span>Perfil Profesional</span>
            </h2>
            <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label :class="ETIQUETA">Puesto</label>
                <select disabled :class="CAMPO" data-testid="detalle-puesto">
                  <option value="">{{ v.headline.trim() || 'Seleccionar puesto...' }}</option>
                </select>
                <p v-if="perfilesError" class="mt-1 text-[11px] text-rose-600" data-testid="perfiles-puesto-error">
                  No se pudieron cargar los perfiles profesionales. Se conserva el puesto actual.
                </p>
                <p v-else-if="perfilesVacio" class="mt-1 text-[11px] text-dark-400" data-testid="perfiles-puesto-vacio">
                  No hay perfiles profesionales activos. Se administran en Parámetros.
                </p>
              </div>

              <div>
                <label :class="ETIQUETA">Seniority</label>
                <select disabled :class="CAMPO" data-testid="detalle-seniority">
                  <option value="">Seleccionar seniority...</option>
                  <option v-for="s in SENIORITY" :key="s" :value="s" :selected="s === v.seniority">{{ s }}</option>
                </select>
              </div>

              <div>
                <label :class="ETIQUETA">Modalidad preferida</label>
                <select disabled :class="CAMPO" data-testid="detalle-modalidad">
                  <option value="">Seleccionar modalidad...</option>
                  <option v-for="m in MODALIDADES" :key="m" :value="m" :selected="m === v.modalidad">{{ m }}</option>
                </select>
              </div>

              <div>
                <label :class="ETIQUETA">Pretensión salarial</label>
                <div class="w-full rounded-xl border border-dark-200 bg-dark-50/80 px-3.5 py-2.5 text-sm font-medium text-dark-800" data-testid="detalle-salario">
                  <span>{{ formatoSalarioLectura(datos) }}</span>
                </div>
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Fuente</label>
                <input type="text" disabled :value="v.fuente" placeholder="Portal Propio" :class="CAMPO" />
              </div>

              <!-- Skills / Tecnologías -->
              <div class="space-y-2 sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Skills / Tecnologías</label>
                <div :class="CONTENEDOR_CHIPS" data-testid="detalle-skills">
                  <span v-for="skill in v.skills" :key="skill" :class="CHIP"><span>{{ skill }}</span></span>
                  <span v-if="!v.skills.length" class="px-2 text-xs text-dark-400 italic">
                    <span>Sin tecnologías registradas.</span>
                  </span>
                </div>
              </div>

              <!-- Habilidades / Competencias -->
              <div class="space-y-2 sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Habilidades / Competencias</label>
                <div :class="CONTENEDOR_CHIPS" data-testid="detalle-habilidades">
                  <span v-for="hab in v.habilidades" :key="hab" :class="CHIP"><span>{{ hab }}</span></span>
                  <span v-if="!v.habilidades.length" class="px-2 text-xs text-dark-400 italic">
                    <span>Sin habilidades o competencias registradas.</span>
                  </span>
                </div>
              </div>

              <!-- Disponibilidad -->
              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Disponibilidad</label>
                <select disabled :class="CAMPO" data-testid="detalle-disponibilidad">
                  <option
                    v-for="d in DISPONIBILIDADES"
                    :key="d.valor"
                    :value="d.valor"
                    :selected="d.valor === v.disponibilidad"
                  >
                    {{ d.etiqueta }}
                  </option>
                </select>
              </div>

              <!-- Observaciones -->
              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Observaciones</label>
                <textarea
                  rows="3"
                  disabled
                  :value="v.observaciones"
                  placeholder="Notas internas, comentarios de contacto o feedback preliminar..."
                  :class="`${CAMPO} resize-none`"
                ></textarea>
              </div>

              <!-- Curriculum Vitae (CV) -->
              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Curriculum Vitae (CV)</label>
                <div class="flex items-center justify-between rounded-2xl border border-dark-200 bg-white p-4 shadow-xs">
                  <div class="flex min-w-0 items-center gap-3.5">
                    <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
                      <FileText class="h-5 w-5" />
                    </div>
                    <div class="truncate">
                      <p class="truncate text-xs font-bold text-dark-800">{{ nombreCv(datos) }}</p>
                      <p class="text-[11px] text-dark-400">{{ datos.cv_url ? 'Documento digital adjunto' : 'Sin archivo cargado' }}</p>
                    </div>
                  </div>
                  <div>
                    <a
                      v-if="datos.cv_url"
                      :href="urlCv(datos.cv_url)"
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid="descargar-cv"
                      class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-50 px-3.5 py-2 text-xs font-semibold text-primary-600 transition-colors hover:bg-primary-100 hover:text-primary-700"
                    >
                      <Download class="h-4 w-4" />
                      <span>Descargar CV</span>
                    </a>
                    <span v-else class="text-xs text-dark-400 italic">No disponible</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </form>
      </div>
    </template>
  </div>
</template>
