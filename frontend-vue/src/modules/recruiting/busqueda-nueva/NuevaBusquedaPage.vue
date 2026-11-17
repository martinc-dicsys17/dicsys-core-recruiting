<script setup lang="ts">
import { AlertCircle, ArrowLeft, Award, Briefcase, Code2, Loader2, Sparkles, Target } from '@lucide/vue'
import Toast from 'primevue/toast'
import { guardarAviso } from '../busquedas/aviso'
import { useToast } from 'primevue/usetoast'
import { computed, reactive, ref, watch } from 'vue'

import ChipsRequisito from './components/ChipsRequisito.vue'
import { useCatalogosBusqueda, usePermisoCrearBusqueda } from './composables/useCatalogosBusqueda'
import { useCrearBusqueda } from './composables/useCrearBusqueda'
import { errorRango, formatearRango } from './rango'
import type { FormularioBusqueda } from './types'

const toast = useToast()
const LISTADO = '/recruiting/oportunidades'

// Valores iniciales de una búsqueda nueva (los de la pantalla anterior); los demás campos arrancan vacíos.
const form = reactive<FormularioBusqueda>({
  titulo: '',
  tipo: 'Efectiva',
  puesto: '',
  cliente: '',
  hm: '',
  reclutador: '',
  vacantes: 1,
  prioridad: 'Alta',
  seniority: 'Senior',
  modalidad: 'Hibrido',
  rango: '',
  descripcion: '',
  skills: [],
  habilidades: [],
  skills_deseadas: [],
})
// La fecha de creación solo se muestra (deshabilitada): la fija el backend.
const fechaCreacion = new Date().toLocaleDateString('en-CA')

// ---- Permiso de creación: sin él se avisa y se vuelve al listado, como la pantalla anterior ----
const permisos = usePermisoCrearBusqueda()
const puedeCrear = computed(() => permisos.data.value?.puede_crear_busquedas === true)
const sinPermiso = computed(() => !permisos.isPending.value && !puedeCrear.value)
watch(
  sinPermiso,
  (sin) => {
    if (!sin) return
    guardarAviso({ tipo: 'error', mensaje: 'No tenés permisos para crear búsquedas.' })
    window.location.assign(LISTADO)
  },
  { immediate: true },
)

// ---- Catálogos ----
const { puestos, skills, habilidades, lideres, reclutadores } = useCatalogosBusqueda()
// Solo en una búsqueda nueva se preselecciona el primer reclutador del catálogo.
watch(
  () => reclutadores.data.value,
  (lista) => {
    if (!form.reclutador && lista?.length) form.reclutador = lista[0] as string
  },
  { immediate: true },
)

// ---- Rango salarial ----
const rangoTocado = ref(false)
const mensajeRango = computed(() => errorRango(form.rango, rangoTocado.value))
function alEscribirRango(evento: Event): void {
  form.rango = formatearRango((evento.target as HTMLInputElement).value)
  ;(evento.target as HTMLInputElement).value = form.rango
}

// ---- Guardado ----
const alta = useCrearBusqueda()
const guardando = computed(() => alta.isPending.value)
const errorGeneral = ref('')

function subirAlInicio(): void {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function guardar(): void {
  if (guardando.value || alta.isSuccess.value) return // evita dobles envíos
  errorGeneral.value = ''
  if (!form.titulo.trim()) {
    subirAlInicio()
    errorGeneral.value = 'Por favor ingresá el título de la posición.'
    return
  }
  if (!form.cliente.trim()) {
    subirAlInicio()
    errorGeneral.value = 'Por favor seleccioná el cliente.'
    return
  }
  rangoTocado.value = true
  if (errorRango(form.rango, true)) {
    subirAlInicio()
    errorGeneral.value = errorRango(form.rango, true)
    return
  }
  alta.mutate(form, {
    onSuccess: () => {
      toast.add({ severity: 'success', summary: 'Oportunidad creada exitosamente.', life: 4000 })
      // Como antes: vuelve al listado de búsquedas.
      window.setTimeout(() => window.location.assign(LISTADO), 900)
    },
    onError: (error) => {
      subirAlInicio()
      errorGeneral.value = error instanceof Error ? error.message : 'Ocurrió un error al guardar la oportunidad.'
    },
  })
}

const ESTILOS_TOAST = { root: { class: 'top-20! z-50' } }

const CLASE_ETIQUETA = 'mb-1 block text-xs font-semibold text-dark-600'
const CLASE_CAMPO =
  'w-full rounded-xl border border-dark-200 px-3.5 py-2.5 text-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none'
const CLASE_COMBO = `${CLASE_CAMPO} cursor-pointer text-dark-700`
const CLASE_SECCION = 'mb-4 flex items-center gap-2 border-b border-dark-100 pb-2 text-base font-bold text-dark-900'
</script>

<template>
  <div class="animate-fade-in w-full p-2 lg:p-4">
    <!-- Encabezado con el botón Volver arriba a la derecha -->
    <div class="mb-6 flex items-center justify-between gap-4">
      <div>
        <h1 class="text-2xl font-bold text-dark-900">Nueva Oportunidad</h1>
      </div>
      <div>
        <a
          :href="LISTADO"
          class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700"
          title="Volver a Oportunidades"
          data-testid="volver"
        >
          <ArrowLeft class="h-4 w-4 text-white" />
          <span>Volver</span>
        </a>
      </div>
    </div>

    <div
      v-if="errorGeneral"
      role="alert"
      data-testid="error-general"
      class="mb-6 flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
    >
      <AlertCircle class="h-5 w-5 shrink-0 text-red-600" />
      <span>{{ errorGeneral }}</span>
    </div>

    <div v-if="puedeCrear" class="overflow-hidden rounded-2xl border border-dark-100 bg-white shadow-soft">
      <form class="space-y-6 p-6 lg:p-8" @submit.prevent="guardar">
        <!-- Sección 1: datos principales -->
        <div>
          <h2 :class="CLASE_SECCION">
            <Briefcase class="h-4 w-4 text-primary-600" />
            <span>Datos de la Posición</span>
          </h2>
          <div class="grid grid-cols-2 gap-5">
            <div>
              <label for="titulo" :class="CLASE_ETIQUETA">Título de la posición *</label>
              <input
                id="titulo"
                v-model="form.titulo"
                type="text"
                placeholder="Ej: Senior Backend Engineer (Python)"
                required
                :class="CLASE_CAMPO"
              />
            </div>

            <div>
              <label for="tipo" :class="CLASE_ETIQUETA">Tipo de Oportunidad *</label>
              <select id="tipo" v-model="form.tipo" :class="CLASE_COMBO">
                <option value="Efectiva">Efectiva</option>
                <option value="Potencial">Potencial</option>
              </select>
            </div>

            <div class="col-span-2">
              <label for="puesto" :class="CLASE_ETIQUETA">Perfil / Puesto</label>
              <select id="puesto" v-model="form.puesto" :class="`${CLASE_COMBO} bg-white`" style="color: #000">
                <option value="">Seleccionar puesto...</option>
                <option v-for="p in puestos.data.value ?? []" :key="p" :value="p">{{ p }}</option>
              </select>
              <p v-if="puestos.isError.value" class="mt-1 text-[11px] text-rose-600" data-testid="perfiles-puesto-error">
                No se pudieron cargar los perfiles profesionales. Podés guardar la búsqueda sin puesto.
              </p>
              <p
                v-else-if="puestos.isSuccess.value && !(puestos.data.value ?? []).length"
                class="mt-1 text-[11px] text-dark-400"
                data-testid="perfiles-puesto-vacio"
              >
                No hay perfiles profesionales activos. Se administran en Parámetros.
              </p>
            </div>

            <div>
              <label for="cliente" :class="CLASE_ETIQUETA">Cliente / Área *</label>
              <input
                id="cliente"
                v-model="form.cliente"
                type="text"
                list="lista-clientes-sugeridos"
                placeholder="Ej: AGD, Camuzzi, Dicsys, Claro..."
                required
                :class="CLASE_CAMPO"
              />
              <datalist id="lista-clientes-sugeridos">
                <option value="AGD"></option>
                <option value="Camuzzi"></option>
                <option value="Dicsys"></option>
                <option value="Claro"></option>
                <option value="Banco Galicia"></option>
                <option value="Telecom"></option>
                <option value="Naranja X"></option>
                <option value="Prisma Medios"></option>
              </datalist>
            </div>

            <div>
              <label for="lider" :class="CLASE_ETIQUETA">Líder / Hiring Manager</label>
              <select id="lider" v-model="form.hm" :class="`${CLASE_COMBO} bg-white`">
                <option value="">Sin asignar</option>
                <option v-for="l in lideres.data.value ?? []" :key="l" :value="l">{{ l }}</option>
              </select>
            </div>

            <div>
              <label for="reclutador" :class="CLASE_ETIQUETA">Reclutador responsable *</label>
              <select id="reclutador" v-model="form.reclutador" required :class="`${CLASE_COMBO} bg-white`">
                <option value="" disabled>Seleccionar reclutador</option>
                <option v-for="r in reclutadores.data.value ?? []" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>

            <div>
              <label for="vacantes" :class="CLASE_ETIQUETA">Cantidad de vacantes *</label>
              <input id="vacantes" v-model="form.vacantes" type="number" min="1" :class="CLASE_CAMPO" />
            </div>

            <div>
              <label for="prioridad" :class="CLASE_ETIQUETA">Prioridad</label>
              <select id="prioridad" v-model="form.prioridad" :class="CLASE_COMBO">
                <option value="Critica">Crítica</option>
                <option value="Alta">Alta</option>
                <option value="Media">Media</option>
                <option value="Baja">Baja</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Sección 2: perfil y requisitos -->
        <div class="pt-4">
          <h2 :class="CLASE_SECCION">
            <Target class="h-4 w-4 text-primary-600" />
            <span>Requisitos del Perfil</span>
          </h2>
          <div class="grid grid-cols-2 gap-5">
            <div>
              <label for="seniority" :class="CLASE_ETIQUETA">Seniority</label>
              <select id="seniority" v-model="form.seniority" :class="CLASE_COMBO">
                <option value="Junior">Junior</option>
                <option value="Semi Sr">Semi Sr</option>
                <option value="Senior">Senior</option>
                <option value="Lead">Lead</option>
              </select>
            </div>

            <div>
              <label for="modalidad" :class="CLASE_ETIQUETA">Modalidad de trabajo</label>
              <select id="modalidad" v-model="form.modalidad" :class="CLASE_COMBO">
                <option value="Remoto">Remoto</option>
                <option value="Hibrido">Híbrido</option>
                <option value="Presencial">Presencial</option>
              </select>
            </div>

            <div>
              <label for="rango" :class="CLASE_ETIQUETA">Rango Salarial (en pesos)</label>
              <input
                id="rango"
                :value="form.rango"
                type="text"
                autocomplete="off"
                data-testid="rango-salarial"
                placeholder="Ej: $ 2.000.000 - $ 3.500.000"
                class="w-full rounded-xl border px-3.5 py-2.5 text-sm focus:ring-2 focus:outline-none"
                :class="
                  mensajeRango
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                    : 'border-dark-200 focus:border-primary-500 focus:ring-primary-500/20'
                "
                @input="alEscribirRango"
                @blur="rangoTocado = true"
              />
              <p v-if="mensajeRango" data-testid="rango-salarial-error" class="mt-1 text-xs text-red-600">
                {{ mensajeRango }}
              </p>
            </div>

            <div>
              <label for="fecha-creacion" :class="CLASE_ETIQUETA">Fecha de creación</label>
              <input
                id="fecha-creacion"
                :value="fechaCreacion"
                type="date"
                readonly
                disabled
                class="h-11 w-full cursor-not-allowed rounded-xl border border-dark-200 bg-dark-50 px-3.5 py-2.5 text-sm text-dark-500"
              />
            </div>

            <ChipsRequisito
              v-model="form.skills"
              id-campo="skills"
              titulo="Skills / Tecnologías requeridas"
              :icono="Code2"
              tono="primario"
              :opciones="skills.data.value ?? []"
              etiqueta-disponibles="Skills disponibles:"
              texto-vacio="Ninguna tecnología seleccionada. Podés elegir de la lista o tipear una nueva."
              placeholder-nueva="Agregar otra tecnología (ej: NestJS, Redis, Kafka)..."
              texto-boton="+ Agregar Tecnología"
            />

            <ChipsRequisito
              v-model="form.habilidades"
              id-campo="habilidades"
              titulo="Habilidades / Competencias requeridas"
              :icono="Award"
              tono="esmeralda"
              separado
              :opciones="habilidades.data.value ?? []"
              etiqueta-disponibles="Competencias disponibles:"
              texto-vacio="Ninguna habilidad o competencia seleccionada. Podés elegir de la lista o tipear una nueva."
              placeholder-nueva="Agregar otra habilidad o competencia (ej: Liderazgo, Comunicación, Negociación)..."
              texto-boton="+ Agregar Habilidad"
            />

            <ChipsRequisito
              v-model="form.skills_deseadas"
              id-campo="skills-deseadas"
              titulo="Skills deseadas"
              :icono="Sparkles"
              tono="ambar"
              separado
              :opciones="skills.data.value ?? []"
              etiqueta-disponibles="Skills disponibles:"
              texto-vacio="Ninguna skill deseada seleccionada. Podés elegir de la lista o tipear una nueva."
              placeholder-nueva="Agregar otra skill deseada (ej: Terraform, Kubernetes, GraphQL)..."
              texto-boton="+ Agregar Skill"
            />

            <div class="col-span-2">
              <label for="descripcion" :class="CLASE_ETIQUETA">Descripción de la posición</label>
              <textarea
                id="descripcion"
                v-model="form.descripcion"
                rows="3"
                placeholder="Detalle de responsabilidades, tecnologías y objetivos del puesto..."
                :class="`${CLASE_CAMPO} resize-none`"
              ></textarea>
            </div>
          </div>
        </div>

        <!-- Pie con las acciones -->
        <div class="flex items-center justify-end gap-3 border-t border-dark-100 pt-6">
          <a
            :href="LISTADO"
            class="rounded-xl px-4 py-2.5 text-sm font-medium text-dark-600 transition-colors hover:bg-dark-50"
            data-testid="cancelar"
          >
            Cancelar
          </a>
          <button
            type="submit"
            :disabled="guardando"
            data-testid="guardar"
            class="inline-flex cursor-pointer items-center gap-2 rounded-xl bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700 disabled:opacity-50"
          >
            <span v-if="guardando" class="inline-flex"><Loader2 class="h-4 w-4 animate-spin" /></span>
            <span>{{ guardando ? 'Guardando...' : 'Crear Oportunidad' }}</span>
          </button>
        </div>
      </form>
    </div>

    <Toast position="top-right" :pt="ESTILOS_TOAST" />
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
