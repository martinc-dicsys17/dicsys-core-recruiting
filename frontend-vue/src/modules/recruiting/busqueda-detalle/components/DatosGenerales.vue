<script setup lang="ts">
import { Award, Briefcase, Code2, Sparkles } from '@lucide/vue'

import { etiquetaDato } from '../presentacion'
import type { FormularioBusqueda, Oportunidad } from '../types'
import SelectorChips from './SelectorChips.vue'

/** Tarjeta «Datos Generales y Cliente»: lectura, o edición (solo Descripción y Skills deseadas se pueden cambiar). */
defineProps<{
  datos: Oportunidad
  editando: boolean
  skillsCatalogo: string[]
  habilidadesCatalogo: string[]
  perfilesPuesto: string[]
  perfilesError: boolean
  perfilesCargados: boolean
}>()
const form = defineModel<FormularioBusqueda>('form', { required: true })

const ENTRADA =
  'w-full px-3.5 py-2 rounded-xl border border-dark-200 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 text-sm'
// Bloqueados en edición: si el valor guardado no figura entre las opciones, el combo muestra la primera (como el <select> anterior).
const SENIORITIES = ['Trainee', 'Junior', 'Semi Sr', 'Senior', 'Lead', 'Architect', 'Manager']
const MODALIDADES = ['Remoto', 'Hibrido', 'Presencial']
const mostrado = (valor: string | null | undefined, opciones: string[]) => (valor && opciones.includes(valor) ? valor : (opciones[0] ?? ''))
const SELECT = `${ENTRADA} text-dark-700 cursor-pointer`
const ETIQUETA = 'block text-xs font-semibold text-dark-600 mb-1'
const DATO = 'text-xs font-semibold text-dark-400 mb-0.5'
</script>

<template>
  <div class="bg-white rounded-2xl border border-dark-100 shadow-soft p-6">
    <h2 class="text-base font-bold text-dark-900 pb-2 mb-4 border-b border-dark-100 flex items-center gap-2">
      <Briefcase class="w-4 h-4 text-primary-600" />
      <span>Datos Generales y Cliente</span>
    </h2>

    <!-- Modo lectura -->
    <div v-if="!editando" class="grid sm:grid-cols-2 gap-4 text-sm">
      <div class="sm:col-span-2">
        <p :class="DATO">Título de la Posición</p>
        <p class="font-bold text-dark-900 text-base">{{ datos.titulo || '—' }}</p>
      </div>
      <div>
        <p :class="DATO">Perfil / Puesto</p>
        <p class="font-semibold text-dark-800">{{ datos.puesto || '—' }}</p>
      </div>
      <div>
        <p :class="DATO">Cliente</p>
        <p class="font-semibold text-dark-800">{{ datos.cliente || '—' }}</p>
      </div>
      <div>
        <p :class="DATO">Área / Negocio</p>
        <p class="font-medium text-dark-800">{{ datos.area || 'Operaciones / IT' }}</p>
      </div>
      <div>
        <p :class="DATO">Seniority Solicitado</p>
        <p class="font-medium text-dark-800">{{ datos.seniority || 'Senior' }}</p>
      </div>
      <div>
        <p :class="DATO">Modalidad de Trabajo</p>
        <p class="font-medium text-dark-800">{{ etiquetaDato(datos.modalidad || 'Remoto') }}</p>
      </div>
      <div>
        <p :class="DATO">Vacantes</p>
        <p class="font-medium text-dark-800">{{ datos.vacantes || 1 }} posición(es)</p>
      </div>
      <div>
        <p :class="DATO">Rango Salarial Pretendido</p>
        <p class="font-medium text-dark-800">{{ datos.rango || 'A convenir' }}</p>
      </div>

      <!-- Skills y habilidades en lectura, separadas -->
      <div class="sm:col-span-2 mt-3 pt-3 border-t border-dark-100 space-y-3">
        <div>
          <div class="flex items-center gap-1.5 mb-1.5">
            <Code2 class="w-3.5 h-3.5 text-primary-600" />
            <p class="text-xs font-bold text-dark-700">Skills / Tecnologías requeridas</p>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="s in datos.skills"
              :key="s"
              class="px-2.5 py-1 text-xs font-medium rounded-lg bg-primary-50 text-primary-700 border border-primary-200/60"
              >{{ s }}</span
            >
            <span v-if="!datos.skills.length" class="text-xs text-dark-400 italic">Sin tecnologías especificadas</span>
          </div>
        </div>

        <div>
          <div class="flex items-center gap-1.5 mb-1.5">
            <Award class="w-3.5 h-3.5 text-emerald-600" />
            <p class="text-xs font-bold text-dark-700">Habilidades / Competencias requeridas</p>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="h in datos.habilidades"
              :key="h"
              class="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200/60"
              >{{ h }}</span
            >
            <span v-if="!datos.habilidades.length" class="text-xs text-dark-400 italic">
              Sin habilidades o competencias especificadas
            </span>
          </div>
        </div>

        <div data-testid="descripcion-busqueda">
          <p class="text-xs font-bold text-dark-700 mb-1.5">Descripción de la posición</p>
          <p v-if="datos.descripcion" class="text-sm text-dark-700 whitespace-pre-line">{{ datos.descripcion }}</p>
          <span v-else class="text-xs text-dark-400 italic">Sin descripción</span>
        </div>

        <div>
          <div class="flex items-center gap-1.5 mb-1.5">
            <Sparkles class="w-3.5 h-3.5 text-amber-600" />
            <p class="text-xs font-bold text-dark-700">Skills deseadas</p>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="s in datos.skills_deseadas"
              :key="s"
              class="px-2.5 py-1 text-xs font-medium rounded-lg bg-amber-50 text-amber-800 border border-amber-200/60"
              >{{ s }}</span
            >
            <span v-if="!datos.skills_deseadas.length" class="text-xs text-dark-400 italic">
              Sin skills deseadas especificadas
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Modo edición: los datos del pedido se muestran bloqueados; solo Descripción y Skills deseadas se editan -->
    <div v-else class="grid sm:grid-cols-2 gap-4 text-sm">
      <fieldset disabled class="contents">
        <div class="sm:col-span-2">
          <label :class="ETIQUETA">Título de la posición *</label>
          <input v-model="form.titulo" type="text" required placeholder="Ej: Senior Data Engineer" :class="ENTRADA" />
        </div>
        <div class="sm:col-span-2">
          <label :class="ETIQUETA">Perfil / Puesto</label>
          <select v-model="form.puesto" :class="`${ENTRADA} bg-white cursor-pointer`">
            <option value="">Seleccionar puesto...</option>
            <!-- Perfil actual de la búsqueda aunque esté desactivado o ya no figure en el catálogo -->
            <option v-if="datos.puesto?.trim() && !perfilesPuesto.includes(datos.puesto.trim())" :value="datos.puesto.trim()">
              {{ datos.puesto.trim() }}
            </option>
            <option v-for="perfil in perfilesPuesto" :key="perfil" :value="perfil">{{ perfil }}</option>
          </select>
          <p v-if="perfilesError" class="text-[11px] text-rose-600 mt-1" data-testid="perfiles-puesto-error">
            No se pudieron cargar los perfiles profesionales. Se conserva el puesto actual.
          </p>
          <p v-else-if="perfilesCargados && !perfilesPuesto.length" class="text-[11px] text-dark-400 mt-1" data-testid="perfiles-puesto-vacio">
            No hay perfiles profesionales activos. Se administran en Parámetros.
          </p>
        </div>
        <div>
          <label :class="ETIQUETA">Cliente *</label>
          <input v-model="form.cliente" type="text" required placeholder="Ej: Camuzzi, AGD, Telecom..." :class="ENTRADA" />
        </div>
        <div>
          <label :class="ETIQUETA">Área / Negocio</label>
          <input v-model="form.area" type="text" placeholder="Ej: Datos & Analytics / IT" :class="ENTRADA" />
        </div>
        <div>
          <label :class="ETIQUETA">Seniority</label>
          <select :value="mostrado(form.seniority, SENIORITIES)" :class="SELECT">
            <option value="Trainee">Trainee</option>
            <option value="Junior">Junior</option>
            <option value="Semi Sr">Semi Sr</option>
            <option value="Senior">Senior</option>
            <option value="Lead">Lead</option>
            <option value="Architect">Architect</option>
            <option value="Manager">Manager</option>
          </select>
        </div>
        <div>
          <label :class="ETIQUETA">Modalidad de Trabajo</label>
          <select :value="mostrado(form.modalidad, MODALIDADES)" :class="SELECT">
            <option value="Remoto">Remoto</option>
            <option value="Hibrido">Híbrido</option>
            <option value="Presencial">Presencial</option>
          </select>
        </div>
        <div>
          <label :class="ETIQUETA">Cantidad de Vacantes</label>
          <input v-model.number="form.vacantes" type="number" min="1" :class="ENTRADA" />
        </div>
        <div>
          <label :class="ETIQUETA">Rango Salarial / Pretendido</label>
          <input v-model="form.rango" type="text" placeholder="Ej: USD 3.500 - 4.500 o $ 3.500.000" :class="ENTRADA" />
        </div>

        <SelectorChips v-model="form.skills" tipo="skills" :catalogo="skillsCatalogo" />
        <SelectorChips v-model="form.habilidades" tipo="habilidades" :catalogo="habilidadesCatalogo" />
      </fieldset>

      <!-- Descripción de la posición (editable junto con Skills deseadas) -->
      <div class="sm:col-span-2">
        <label :class="ETIQUETA">Descripción de la posición</label>
        <textarea
          v-model="form.descripcion"
          data-testid="descripcion-editar"
          rows="4"
          placeholder="Detalle de responsabilidades, tecnologías y objetivos del puesto..."
          class="w-full px-3.5 py-2.5 rounded-xl border border-dark-200 focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 text-sm resize-none"
        ></textarea>
      </div>

      <SelectorChips v-model="form.skills_deseadas" tipo="deseadas" :catalogo="skillsCatalogo" />
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
