<script setup lang="ts">
import { AlertCircle, ArrowLeft, Briefcase, Check, CheckCircle, Loader2, User, X } from '@lucide/vue'
import { useQuery } from '@tanstack/vue-query'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { obtenerCandidato } from '../candidato-detalle/api/candidato.repository'
import {
  ciudadInicial,
  DISPONIBILIDADES,
  MODALIDADES,
  provinciaInicial,
  SENIORITY,
  ubicacionSegunCatalogo,
  mostrarUbicacionRegistrada,
} from '../candidato-detalle/presentacion'
import { useCatalogosCandidato } from '../candidato-nuevo/composables/useCatalogosCandidato'
import {
  destinoVolver,
  enmascararFecha,
  errorFechaNacimiento,
  limpiarTelefono,
} from '../candidato-nuevo/validacion'
import ChipsEdicion from './components/ChipsEdicion.vue'
import CvEdicion from './components/CvEdicion.vue'
import { useActualizarCandidato } from './composables/useActualizarCandidato'
import {
  armarActualizacion,
  formatearSalario,
  formularioInicial,
  MENSAJE_ACTUALIZADO,
  MENSAJE_OBLIGATORIOS,
  normalizarFechaAlSalir,
  prefijoMoneda,
} from './formulario'
import type { FormularioEdicion } from './types'

const ruta = useRoute()
const router = useRouter()
const id = computed(() => String(ruta.params.id))

// «Cancelar» y «Volver» llevan a la ficha del candidato, que conserva el destino de origen (?volver=).
const volver = destinoVolver(ruta.query.volver, '')
const hayVolver = Boolean(ruta.query.volver)
const irALaFicha = () =>
  router.push({
    name: 'recruiting-candidato-detalle',
    params: { id: id.value },
    ...(hayVolver ? { query: { volver: String(ruta.query.volver) } } : {}),
  })

const candidato = useQuery({
  queryKey: computed(() => ['recruiting', 'candidato-editar', id.value]),
  queryFn: () => obtenerCandidato(id.value),
  retry: false,
  gcTime: 0,
})
const datos = computed(() => candidato.data.value)

// ---- Formulario ----
const form = ref<FormularioEdicion | null>(null)
const ubicacionModificada = ref(false)
const provinciaElegida = computed(() => (form.value?.provincia_id ? Number(form.value.provincia_id) : null))
const { provincias, ciudades, puestos, skills, habilidades } = useCatalogosCandidato(provinciaElegida)

// El formulario se arma una vez que están el candidato y los catálogos que necesita para su ubicación y su puesto.
const catalogosListos = computed(() => !provincias.isPending.value && !puestos.isPending.value)
watch(
  [datos, catalogosListos],
  ([candidatoActual, listos]) => {
    if (form.value || !candidatoActual || !listos) return
    const provinciaId = provinciaInicial(candidatoActual, provincias.data.value ?? [])
    form.value = formularioInicial(candidatoActual, provinciaId, provinciaId && candidatoActual.provincia_id ? candidatoActual.ciudad_id ?? null : null)
  },
  { immediate: true },
)
// Candidatos anteriores (solo texto «Ciudad, Provincia»): la ciudad se reconoce cuando llegan las de su provincia.
watch(
  () => ciudades.data.value,
  (lista) => {
    const actual = datos.value
    if (!form.value || !actual || actual.provincia_id || ubicacionModificada.value || form.value.ciudad_id) return
    const ciudadId = ciudadInicial(actual, provinciaElegida.value, lista ?? [])
    if (ciudadId) form.value.ciudad_id = String(ciudadId)
  },
)

watch(
  () => [datos.value?.nombre, datos.value?.apellido] as const,
  ([nombre, apellido]) => {
    if (nombre) document.title = `${nombre} ${apellido ?? ''}`.trim() + ' — Reclutamiento - Dicsys Core'
  },
)

// La ciudad depende de la provincia: al cambiarla se limpia la ciudad seleccionada.
function cambiarProvincia(): void {
  if (form.value) form.value.ciudad_id = ''
  ubicacionModificada.value = true
}

const segunCatalogo = computed(() =>
  datos.value ? ubicacionSegunCatalogo(datos.value, provincias.data.value ?? [], ciudades.data.value ?? []) : '',
)

// Puesto actual del candidato aunque su perfil esté desactivado o ya no figure en el catálogo.
const opcionesPuesto = computed(() => {
  const catalogo = puestos.data.value ?? []
  const actual = (datos.value?.headline ?? '').trim()
  return actual && !catalogo.includes(actual) ? [actual, ...catalogo] : catalogo
})
const perfilesError = computed(() => puestos.isError.value)
const perfilesVacio = computed(() => puestos.isSuccess.value && !puestos.data.value?.length)

// ---- Entradas con formato ----
const fechaError = ref('')
const campoFecha = ref<HTMLInputElement | null>(null)

function alEscribirTelefono(evento: Event): void {
  const campo = evento.target as HTMLInputElement
  if (form.value) form.value.telefono = campo.value = limpiarTelefono(campo.value)
}
function alEscribirFecha(evento: Event): void {
  const campo = evento.target as HTMLInputElement
  if (!form.value) return
  const texto = enmascararFecha(campo.value)
  form.value.fecha_nacimiento = campo.value = texto
  // Con los 8 dígitos (DD-MM-YYYY) se valida; antes, no.
  fechaError.value = texto.length === 10 ? errorFechaNacimiento(texto) : ''
}
function alSalirDeFecha(): void {
  if (!form.value) return
  if (!form.value.fecha_nacimiento.trim()) {
    fechaError.value = ''
    return
  }
  form.value.fecha_nacimiento = normalizarFechaAlSalir(form.value.fecha_nacimiento)
  fechaError.value = errorFechaNacimiento(form.value.fecha_nacimiento)
}
function alEscribirSalario(evento: Event): void {
  const campo = evento.target as HTMLInputElement
  if (form.value) form.value.salario = campo.value = formatearSalario(campo.value)
}

// ---- Aviso (toast) ----
const toast = ref({ visible: false, tipo: 'success' as 'success' | 'error', mensaje: '' })
let temporizadorToast: ReturnType<typeof setTimeout> | null = null
let temporizadorSalida: ReturnType<typeof setTimeout> | null = null

function mostrarToast(tipo: 'success' | 'error', mensaje: string): void {
  toast.value = { visible: true, tipo, mensaje }
  if (temporizadorToast) clearTimeout(temporizadorToast)
  temporizadorToast = setTimeout(() => (toast.value.visible = false), 3500)
}
onBeforeUnmount(() => {
  if (temporizadorToast) clearTimeout(temporizadorToast)
  if (temporizadorSalida) clearTimeout(temporizadorSalida)
})

// ---- Guardar y cancelar ----
const cv = ref<File | null>(null)
const cvEdicion = ref<InstanceType<typeof CvEdicion> | null>(null)
const actualizar = useActualizarCandidato()
const guardando = computed(() => actualizar.isPending.value)
const bloqueado = computed(() => guardando.value || actualizar.isSuccess.value)

function guardar(): void {
  const f = form.value
  if (!f || bloqueado.value) return
  const errorFecha = f.fecha_nacimiento ? errorFechaNacimiento(f.fecha_nacimiento) : ''
  if (errorFecha) {
    fechaError.value = errorFecha
    campoFecha.value?.focus()
    mostrarToast('error', errorFecha)
    return
  }
  if (!f.nombre.trim() || !f.apellido.trim() || !f.email.trim() || !f.telefono.trim()) {
    mostrarToast('error', MENSAJE_OBLIGATORIOS)
    return
  }
  actualizar.mutate(
    { id: id.value, datos: armarActualizacion(f, ubicacionModificada.value), cv: cv.value },
    {
      onSuccess: () => {
        mostrarToast('success', MENSAJE_ACTUALIZADO)
        // Como antes, se vuelve a la ficha (ya en modo lectura) con el aviso a la vista un momento.
        temporizadorSalida = setTimeout(() => void irALaFicha(), 900)
      },
      onError: (error) => mostrarToast('error', error.message),
    },
  )
}

function cancelar(): void {
  if (guardando.value) return
  cvEdicion.value?.quitar()
  void irALaFicha()
}

const CAMPO = 'w-full px-3.5 py-2.5 rounded-xl border text-sm transition-colors bg-white text-dark-900 border-dark-200 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500'
const CAMPO_COMBO = `${CAMPO} cursor-pointer disabled:cursor-default disabled:bg-dark-50/80 disabled:text-dark-800`
const ETIQUETA = 'block text-xs font-semibold text-dark-600 mb-1'
const TITULO_SECCION = 'text-base font-bold text-dark-900 pb-2 mb-4 border-b border-dark-100 flex items-center gap-2'
</script>

<template>
  <div class="w-full max-w-none animate-fade-in">
    <!-- Aviso (toast) -->
    <div
      v-if="toast.visible"
      role="status"
      data-testid="toast"
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
          :href="volver"
          class="inline-flex items-center gap-2 rounded-xl border border-dark-200 bg-white px-4 py-2.5 text-sm font-semibold text-dark-700 shadow-soft hover:bg-dark-50"
        >
          <ArrowLeft class="h-4 w-4 text-dark-600" /><span>Volver</span>
        </a>
      </div>
    </div>

    <div v-else-if="!form || !datos" class="flex items-center gap-2 p-6 text-sm text-dark-500" role="status">
      <Loader2 class="h-4 w-4 animate-spin" /><span>Cargando ficha del candidato...</span>
    </div>

    <template v-else>
      <!-- Encabezado con título y botones de acción -->
      <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="mb-1 flex items-center gap-2">
            <span class="rounded-lg bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-800 uppercase">Modo Edición</span>
            <h1 class="text-2xl font-bold text-dark-900">Editar Ficha del Candidato</h1>
          </div>
          <p class="text-sm text-dark-500">
            Modificá los datos del candidato y guardá los cambios para actualizar el banco de talentos.
          </p>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            :disabled="guardando"
            data-testid="cancelar-superior"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-dark-200 bg-white px-4 py-2.5 text-sm font-semibold text-dark-700 shadow-soft transition-colors hover:bg-dark-50 disabled:opacity-50"
            @click="cancelar"
          >
            <X class="h-4 w-4 text-dark-600" />
            <span>Cancelar</span>
          </button>
          <button
            type="button"
            :disabled="bloqueado"
            data-testid="guardar-superior"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700 disabled:opacity-50"
            @click="guardar"
          >
            <Check v-if="!guardando" class="h-4 w-4 text-white" />
            <span v-else class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
            <span>{{ guardando ? 'Guardando...' : 'Guardar Cambios' }}</span>
          </button>
        </div>
      </div>

      <!-- Formulario -->
      <div class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
        <form class="space-y-6 p-6 lg:p-8" @submit.prevent="guardar">
          <!-- Sección 1: Datos Personales -->
          <div>
            <h2 :class="TITULO_SECCION">
              <User class="h-4 w-4 text-primary-600" />
              <span>Datos Personales y Contacto</span>
            </h2>
            <div class="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label :class="ETIQUETA">Nombres *</label>
                <input v-model="form.nombre" type="text" name="nombre" placeholder="Nombres" required :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Apellido *</label>
                <input v-model="form.apellido" type="text" name="apellido" placeholder="Apellido" required :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Email *</label>
                <input v-model="form.email" type="email" name="email" placeholder="ejemplo@correo.com" required :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Teléfono *</label>
                <input
                  :value="form.telefono"
                  type="text"
                  name="telefono"
                  placeholder="ej: +54 9 351 1234567"
                  required
                  :class="CAMPO"
                  @input="alEscribirTelefono"
                />
              </div>
              <div>
                <label :class="ETIQUETA">Provincia</label>
                <select v-model="form.provincia_id" name="provincia_id" :class="CAMPO_COMBO" @change="cambiarProvincia">
                  <option value="">Seleccionar provincia...</option>
                  <option v-for="p in provincias.data.value ?? []" :key="p.provincia_id" :value="String(p.provincia_id)">
                    {{ p.nombre }}
                  </option>
                </select>
              </div>
              <div>
                <label :class="ETIQUETA">Ciudad</label>
                <select
                  v-model="form.ciudad_id"
                  name="ciudad_id"
                  :disabled="!form.provincia_id"
                  :class="CAMPO_COMBO"
                  @change="ubicacionModificada = true"
                >
                  <option value="">Seleccionar ciudad...</option>
                  <option v-for="c in ciudades.data.value ?? []" :key="c.ciudad_id" :value="String(c.ciudad_id)">
                    {{ c.nombre }}
                  </option>
                </select>
                <p v-if="mostrarUbicacionRegistrada(datos, segunCatalogo)" class="mt-1 text-[11px] text-dark-400">
                  Ubicación registrada: <span>{{ datos.ubicacion }}</span>
                </p>
              </div>
              <div>
                <label :class="ETIQUETA">Perfil de LinkedIn</label>
                <input v-model="form.linkedin_url" type="text" placeholder="https://linkedin.com/in/usuario" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">DNI</label>
                <input v-model="form.dni" type="text" name="dni" placeholder="—" :class="CAMPO" />
              </div>
              <div>
                <label :class="ETIQUETA">Fecha de Nacimiento</label>
                <div>
                  <input
                    ref="campoFecha"
                    :value="form.fecha_nacimiento"
                    type="text"
                    name="fecha_nacimiento"
                    maxlength="10"
                    placeholder="DD-MM-YYYY"
                    :class="
                      fechaError
                        ? 'w-full rounded-xl border border-red-500 bg-red-50/20 px-3.5 py-2.5 text-sm text-red-900 transition-colors focus:border-red-500 focus:ring-2 focus:ring-red-500/20 focus:outline-none'
                        : CAMPO
                    "
                    @input="alEscribirFecha"
                    @blur="alSalirDeFecha"
                  />
                  <p v-if="fechaError" class="mt-1 text-xs font-medium text-red-600" data-testid="error-fecha">{{ fechaError }}</p>
                </div>
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
                <select v-model="form.headline" name="puesto" :class="CAMPO_COMBO">
                  <option value="">Seleccionar puesto...</option>
                  <option v-for="p in opcionesPuesto" :key="p" :value="p">{{ p }}</option>
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
                <select v-model="form.seniority" :class="CAMPO_COMBO">
                  <option value="">Seleccionar seniority...</option>
                  <option v-for="s in SENIORITY" :key="s" :value="s">{{ s }}</option>
                </select>
              </div>

              <div>
                <label :class="ETIQUETA">Modalidad preferida</label>
                <select v-model="form.modalidad" :class="CAMPO_COMBO">
                  <option value="">Seleccionar modalidad...</option>
                  <option v-for="m in MODALIDADES" :key="m" :value="m">{{ m }}</option>
                </select>
              </div>

              <div>
                <label :class="ETIQUETA">Pretensión salarial</label>
                <div class="flex items-center">
                  <div class="relative flex-1">
                    <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3.5 text-sm font-medium text-dark-500 select-none">
                      <span>{{ prefijoMoneda(form.moneda) }}</span>
                    </div>
                    <input
                      :value="form.salario"
                      type="text"
                      name="pretension_salarial"
                      :placeholder="`${prefijoMoneda(form.moneda)} 0`"
                      class="w-full rounded-l-xl border border-r-0 border-dark-200 bg-white py-2.5 pr-3.5 text-sm text-dark-900 transition-all focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
                      :class="form.moneda === 'USD' ? 'pl-16' : 'pl-8'"
                      @input="alEscribirSalario"
                    />
                  </div>
                  <select
                    v-model="form.moneda"
                    class="w-36 cursor-pointer rounded-r-xl border border-l border-dark-200 border-l-dark-100 bg-white px-2.5 py-2.5 text-sm font-medium text-dark-800 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
                  >
                    <option value="ARS">Pesos (ARS)</option>
                    <option value="USD">Dólares (USD)</option>
                  </select>
                </div>
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Fuente</label>
                <input v-model="form.fuente" type="text" name="fuente" placeholder="Portal Propio" :class="CAMPO" />
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <ChipsEdicion
                  v-model="form.skills"
                  id-campo="skills"
                  titulo="Skills / Tecnologías"
                  :opciones="skills.data.value ?? []"
                  etiqueta-disponibles="Tecnologías disponibles:"
                  texto-vacio="Ninguna tecnología seleccionada. Podés elegir del catálogo o agregar una nueva."
                  placeholder-nueva="Agregar otra tecnología (ej: Python, Docker, AWS)..."
                  tono="primario"
                />
              </div>
              <div class="sm:col-span-2 lg:col-span-3">
                <ChipsEdicion
                  v-model="form.habilidades"
                  id-campo="habilidades"
                  titulo="Habilidades / Competencias"
                  :opciones="habilidades.data.value ?? []"
                  etiqueta-disponibles="Competencias disponibles:"
                  texto-vacio="Ninguna habilidad o competencia seleccionada. Podés elegir del catálogo o agregar una nueva."
                  placeholder-nueva="Agregar otra habilidad (ej: Liderazgo, Comunicación, Negociación)..."
                  tono="esmeralda"
                />
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Disponibilidad</label>
                <select v-model="form.disponibilidad" name="disponibilidad" :class="CAMPO_COMBO">
                  <option v-for="d in DISPONIBILIDADES" :key="d.valor" :value="d.valor">{{ d.etiqueta }}</option>
                </select>
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Observaciones</label>
                <textarea
                  v-model="form.observaciones"
                  name="observaciones"
                  rows="3"
                  placeholder="Notas internas, comentarios de contacto o feedback preliminar..."
                  :class="`${CAMPO} resize-none`"
                ></textarea>
              </div>

              <div class="sm:col-span-2 lg:col-span-3">
                <label :class="ETIQUETA">Curriculum Vitae (CV)</label>
                <CvEdicion ref="cvEdicion" v-model="cv" :tiene-cv="Boolean(datos.cv_url)" />
              </div>
            </div>
          </div>

          <!-- Botones inferiores -->
          <div class="flex items-center justify-end gap-3 border-t border-dark-100 pt-4">
            <button
              type="button"
              :disabled="guardando"
              data-testid="cancelar"
              class="cursor-pointer rounded-xl px-4 py-2.5 text-sm font-medium text-dark-600 transition-colors hover:bg-dark-50 disabled:opacity-50"
              @click="cancelar"
            >
              Cancelar
            </button>
            <button
              type="submit"
              :disabled="bloqueado"
              data-testid="guardar"
              class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span v-if="!guardando">Guardar Cambios</span>
              <span v-else class="inline-flex items-center gap-2">
                <Loader2 class="h-4 w-4 animate-spin" />
                <span>Guardando...</span>
              </span>
            </button>
          </div>
        </form>
      </div>
    </template>
  </div>
</template>
