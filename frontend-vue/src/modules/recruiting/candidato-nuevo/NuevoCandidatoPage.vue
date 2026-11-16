<script setup lang="ts">
import { AlertCircle, ArrowLeft, Briefcase, Loader2, User, UserPlus } from '@lucide/vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import CvDropzone from './components/CvDropzone.vue'
import ChipsSelector from './components/ChipsSelector.vue'
import { useCatalogosCandidato } from './composables/useCatalogosCandidato'
import { useCrearCandidato } from './composables/useCrearCandidato'
import type { FormularioCandidato } from './types'
import {
  busquedaIdValido,
  destinoVolver,
  emailValido,
  enmascararFecha,
  errorFechaNacimiento,
  limpiarTelefono,
} from './validacion'

const ruta = useRoute()
const toast = useToast()

// Alta desde una búsqueda asignada (?busqueda_id=) y pantalla de origen (?volver=), como la pantalla anterior.
const busquedaId = busquedaIdValido(ruta.query.busqueda_id)
const destino = destinoVolver(ruta.query.volver, busquedaId)

const MODALIDADES = ['Remoto', 'Híbrido', 'Presencial']
// Mismas opciones que la pantalla anterior (valor guardado y texto visible).
const DISPONIBILIDADES = [
  { valor: 'Inmediata', texto: 'Inmediata' },
  { valor: '2 semanas', texto: '2 semanas (preaviso estándar)' },
  { valor: '1 mes', texto: '1 mes' },
  { valor: 'A convenir', texto: 'A convenir' },
]

const form = reactive<FormularioCandidato>({
  nombre: '',
  apellido: '',
  email: '',
  telefono: '',
  provincia_id: null,
  ciudad_id: null,
  linkedin: '',
  dni: '',
  fecha_nacimiento: '',
  puesto: '',
  seniority: 'Semi Senior',
  modalidad: 'Remoto',
  skills: [],
  habilidades: [],
})
// Disponibilidad y Observaciones se muestran como en la pantalla anterior, que tampoco las enviaba al guardar.
const disponibilidad = ref('Inmediata')
const observaciones = ref('')
const cv = ref<File | null>(null)

const provinciaId = computed(() => form.provincia_id)
const { provincias, ciudades, puestos, seniority, skills, habilidades } = useCatalogosCandidato(provinciaId)

// La ciudad depende de la provincia: al cambiarla se limpia la ciudad elegida.
watch(provinciaId, () => (form.ciudad_id = null))

// Errores por campo: se muestran al intentar guardar y se limpian al corregir.
const errores = reactive<Record<string, string>>({})
const errorGeneral = ref('')
const intentado = ref(false)

function validar(): boolean {
  errores.nombre = form.nombre.trim() ? '' : 'Ingresá los nombres'
  errores.apellido = form.apellido.trim() ? '' : 'Ingresá el apellido'
  errores.email = !form.email.trim() ? 'Ingresá el email' : emailValido(form.email) ? '' : 'Ingresá un email válido'
  errores.telefono = form.telefono.trim() ? '' : 'Ingresá el teléfono'
  errores.fecha_nacimiento = errorFechaNacimiento(form.fecha_nacimiento)
  return Object.values(errores).every((e) => !e)
}

watch(form, () => {
  if (intentado.value) validar()
})

function alEscribirTelefono(valor: string | undefined): void {
  form.telefono = limpiarTelefono(valor ?? '')
}
function alEscribirFecha(valor: string | undefined): void {
  form.fecha_nacimiento = enmascararFecha(valor ?? '')
  if (form.fecha_nacimiento.length === 10 || !form.fecha_nacimiento) errores.fecha_nacimiento = errorFechaNacimiento(form.fecha_nacimiento)
  else errores.fecha_nacimiento = ''
}

const alta = useCrearCandidato()
const guardando = computed(() => alta.isPending.value)

function subirAlInicio(): void {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function guardar(): void {
  if (guardando.value || alta.isSuccess.value) return // evita dobles envíos
  intentado.value = true
  errorGeneral.value = ''
  if (!validar()) {
    errorGeneral.value =
      errores.fecha_nacimiento && !errores.nombre && !errores.apellido && !errores.email && !errores.telefono
        ? `Por favor verificá los errores en el formulario: ${errores.fecha_nacimiento}`
        : 'Por favor completá los campos obligatorios (*): Nombre, Apellido, Email y Teléfono.'
    subirAlInicio()
    return
  }
  alta.mutate(
    { formulario: { ...form }, busquedaId, cv: cv.value },
    {
      onSuccess: ({ cvSubido }) => {
        toast.add(
          cvSubido
            ? { severity: 'success', summary: 'Candidato guardado exitosamente.', life: 4000 }
            : {
                severity: 'warn',
                summary: 'Candidato guardado',
                detail: 'No se pudo subir el CV adjunto. Podés cargarlo desde la ficha del candidato.',
                life: 6000,
              },
        )
        // Mismo comportamiento que antes: vuelve a la pantalla de origen (las pantallas siguientes son de Flask).
        window.setTimeout(() => window.location.assign(destino), cvSubido ? 900 : 2500)
      },
      onError: (error) => {
        errorGeneral.value = error instanceof Error ? error.message : 'Ocurrió un error al guardar el candidato.'
        subirAlInicio()
      },
    },
  )
}

// El Toast queda debajo del encabezado general, como en Blacklist.
const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }

const CLASE_ETIQUETA = 'mb-1 block text-xs font-semibold text-dark-600'
const CLASE_ERROR = 'mt-1 text-xs font-medium text-red-600'
</script>

<template>
  <div class="relative isolate -m-6 min-h-[calc(100vh-68px)] bg-slate-50/70 p-6 text-dark-900">
    <div class="animate-fade-in">
      <header class="mb-7 flex flex-wrap items-center gap-4">
        <span
          class="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-bordo-700 to-dark-900 text-white shadow-sm ring-1 ring-dark-900/10"
        >
          <UserPlus class="h-6 w-6 text-white" />
        </span>
        <div>
          <h1 class="text-3xl font-extrabold tracking-tight text-dark-900">Nuevo Candidato</h1>
          <p class="mt-0.5 text-xs text-dark-400">Alta de un candidato en el Banco de Talentos</p>
        </div>
        <Button
          as="a"
          :href="destino"
          label="Volver"
          title="Volver a Candidatos"
          class="ml-auto bg-bordo-700! hover:bg-bordo-800! text-white! border-bordo-700! shadow-sm"
          data-testid="volver"
        >
          <template #icon><ArrowLeft class="mr-1.5 h-4 w-4" /></template>
        </Button>
      </header>

      <div
        v-if="errorGeneral"
        role="alert"
        data-testid="error-general"
        class="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        <AlertCircle class="h-5 w-5 shrink-0 text-red-600" />
        <span>{{ errorGeneral }}</span>
      </div>

      <section class="overflow-hidden rounded-2xl border border-dark-200 bg-white shadow-xs">
        <form class="space-y-6 p-6 lg:p-8" novalidate @submit.prevent="guardar">
          <!-- Sección 1: datos personales -->
          <div>
            <h2 class="mb-4 flex items-center gap-2 border-b border-dark-100 pb-2 text-base font-bold text-dark-900">
              <User class="h-4 w-4 text-bordo-700" />
              Datos Personales y Contacto
            </h2>
            <div class="grid gap-5 md:grid-cols-2">
              <div>
                <label for="nombre" :class="CLASE_ETIQUETA">Nombres *</label>
                <InputText id="nombre" v-model="form.nombre" fluid placeholder="Nombres" :invalid="!!errores.nombre" />
                <p v-if="errores.nombre" :class="CLASE_ERROR">{{ errores.nombre }}</p>
              </div>
              <div>
                <label for="apellido" :class="CLASE_ETIQUETA">Apellido *</label>
                <InputText
                  id="apellido"
                  v-model="form.apellido"
                  fluid
                  placeholder="Apellido"
                  :invalid="!!errores.apellido"
                />
                <p v-if="errores.apellido" :class="CLASE_ERROR">{{ errores.apellido }}</p>
              </div>
              <div>
                <label for="email" :class="CLASE_ETIQUETA">Email *</label>
                <InputText
                  id="email"
                  v-model="form.email"
                  type="email"
                  fluid
                  placeholder="ejemplo@correo.com"
                  :invalid="!!errores.email"
                />
                <p v-if="errores.email" :class="CLASE_ERROR">{{ errores.email }}</p>
              </div>
              <div>
                <label for="telefono" :class="CLASE_ETIQUETA">Teléfono *</label>
                <InputText
                  id="telefono"
                  :model-value="form.telefono"
                  fluid
                  placeholder="ej: +54 9 351 1234567"
                  :invalid="!!errores.telefono"
                  @update:model-value="alEscribirTelefono"
                />
                <p v-if="errores.telefono" :class="CLASE_ERROR">{{ errores.telefono }}</p>
              </div>
              <div>
                <label for="provincia" :class="CLASE_ETIQUETA">Provincia</label>
                <Select
                  v-model="form.provincia_id"
                  input-id="provincia"
                  :options="provincias.data.value ?? []"
                  option-label="nombre"
                  option-value="provincia_id"
                  placeholder="Seleccionar provincia..."
                  :loading="provincias.isPending.value"
                  show-clear
                  fluid
                  :pt="{ listContainer: { style: 'max-height: min(24rem, calc(100vh - 8rem))' } }"
                />
                <p v-if="provincias.isError.value" :class="CLASE_ERROR" data-testid="provincias-error">
                  No se pudieron cargar las provincias.
                </p>
              </div>
              <div>
                <label for="ciudad" :class="CLASE_ETIQUETA">Ciudad</label>
                <Select
                  v-model="form.ciudad_id"
                  input-id="ciudad"
                  :options="ciudades.data.value ?? []"
                  option-label="nombre"
                  option-value="ciudad_id"
                  placeholder="Seleccionar ciudad..."
                  :disabled="form.provincia_id === null"
                  :loading="ciudades.isFetching.value"
                  show-clear
                  fluid
                  :pt="{ listContainer: { style: 'max-height: min(24rem, calc(100vh - 8rem))' } }"
                />
                <p v-if="ciudades.isError.value" :class="CLASE_ERROR" data-testid="ciudades-error">
                  No se pudieron cargar las ciudades.
                </p>
              </div>
              <div>
                <label for="linkedin" :class="CLASE_ETIQUETA">Perfil de LinkedIn</label>
                <InputText id="linkedin" v-model="form.linkedin" fluid />
              </div>
              <div>
                <label for="dni" :class="CLASE_ETIQUETA">DNI</label>
                <InputText id="dni" v-model="form.dni" fluid />
              </div>
              <div>
                <label for="fecha-nacimiento" :class="CLASE_ETIQUETA">Fecha de Nacimiento</label>
                <InputText
                  id="fecha-nacimiento"
                  :model-value="form.fecha_nacimiento"
                  fluid
                  maxlength="10"
                  placeholder="DD-MM-YYYY"
                  :invalid="!!errores.fecha_nacimiento"
                  @update:model-value="alEscribirFecha"
                  @blur="errores.fecha_nacimiento = errorFechaNacimiento(form.fecha_nacimiento)"
                />
                <p v-if="errores.fecha_nacimiento" :class="CLASE_ERROR" data-testid="error-fecha">
                  {{ errores.fecha_nacimiento }}
                </p>
              </div>
            </div>
          </div>

          <!-- Sección 2: perfil profesional -->
          <div class="pt-4">
            <h2 class="mb-4 flex items-center gap-2 border-b border-dark-100 pb-2 text-base font-bold text-dark-900">
              <Briefcase class="h-4 w-4 text-bordo-700" />
              Perfil Profesional
            </h2>
            <div class="grid gap-5 md:grid-cols-2">
              <div class="md:col-span-2">
                <label for="puesto" :class="CLASE_ETIQUETA">Puesto</label>
                <Select
                  v-model="form.puesto"
                  input-id="puesto"
                  :options="puestos.data.value ?? []"
                  placeholder="Seleccionar puesto..."
                  :loading="puestos.isPending.value"
                  show-clear
                  class="w-full md:max-w-md"
                  :pt="{ listContainer: { style: 'max-height: min(24rem, calc(100vh - 8rem))' } }"
                />
                <p v-if="puestos.isError.value" class="mt-1 text-[11px] text-rose-600" data-testid="perfiles-puesto-error">
                  No se pudieron cargar los perfiles profesionales. Podés guardar el candidato sin puesto.
                </p>
                <p
                  v-else-if="puestos.isSuccess.value && !puestos.data.value?.length"
                  class="mt-1 text-[11px] text-dark-400"
                  data-testid="perfiles-puesto-vacio"
                >
                  No hay perfiles profesionales activos. Se administran en Parámetros.
                </p>
              </div>

              <div>
                <label for="seniority" :class="CLASE_ETIQUETA">Seniority</label>
                <Select
                  v-model="form.seniority"
                  input-id="seniority"
                  :options="seniority.data.value ?? []"
                  :loading="seniority.isPending.value"
                  fluid
                />
              </div>
              <div>
                <label for="modalidad" :class="CLASE_ETIQUETA">Modalidad preferida</label>
                <Select v-model="form.modalidad" input-id="modalidad" :options="MODALIDADES" fluid />
              </div>

              <div class="md:col-span-2">
                <ChipsSelector
                  v-model="form.skills"
                  id-campo="skills"
                  titulo="Skills / Tecnologías"
                  :opciones="skills.data.value ?? []"
                  etiqueta-disponibles="Tecnologías disponibles:"
                  texto-vacio="Ninguna tecnología seleccionada. Podés elegir del catálogo o agregar una nueva."
                  placeholder-nueva="Agregar otra tecnología (ej: Python, Docker, AWS)..."
                  tono="bordo"
                />
              </div>
              <div class="md:col-span-2">
                <ChipsSelector
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

              <div class="md:col-span-2">
                <label for="disponibilidad" :class="CLASE_ETIQUETA">Disponibilidad</label>
                <Select
                  v-model="disponibilidad"
                  input-id="disponibilidad"
                  :options="DISPONIBILIDADES"
                  option-label="texto"
                  option-value="valor"
                  fluid
                />
              </div>
              <div class="md:col-span-2">
                <label for="observaciones" :class="CLASE_ETIQUETA">Observaciones</label>
                <Textarea
                  id="observaciones"
                  v-model="observaciones"
                  rows="3"
                  fluid
                  class="resize-none"
                  placeholder="Notas internas, comentarios de contacto o feedback preliminar..."
                />
              </div>

              <div class="md:col-span-2">
                <CvDropzone v-model="cv" />
              </div>
            </div>
          </div>

          <div class="flex items-center justify-end gap-3 border-t border-dark-100 pt-4">
            <Button
              as="a"
              :href="destino"
              label="Cancelar"
              severity="secondary"
              text
              data-testid="cancelar"
            />
            <Button
              type="submit"
              :disabled="guardando || alta.isSuccess.value"
              class="bg-bordo-700! hover:bg-bordo-800! text-white! border-bordo-700! shadow-sm"
              data-testid="guardar"
            >
              <Loader2 v-if="guardando" class="mr-2 h-4 w-4 animate-spin" />
              {{ guardando ? 'Guardando...' : 'Guardar Candidato' }}
            </Button>
          </div>
        </form>
      </section>
    </div>
    <Toast position="top-right" :pt="ESTILOS_TOAST" />
  </div>
</template>
