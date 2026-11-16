<script setup lang="ts">
import { AlertCircle, Award, Check, Loader2, UserPlus } from '@lucide/vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'
import { CLASE_BOTON_CANCELAR, CLASE_BOTON_CONFIRMAR, PT_DIALOGO } from '../estilos'

import { useAsignarBusqueda, useBusquedasElegibles } from '../composables/useAsignarBusqueda'
import { detalleMatch } from '../cv'
import type { CandidatoListado } from '../types'

/** Asigna el candidato a una búsqueda abierta compatible (Match > 50 % y todavía sin asignar). */
const candidato = defineModel<CandidatoListado | null>('candidato', { required: true })

const toast = useToast()
const id = computed(() => candidato.value?.id ?? null)
const elegibles = useBusquedasElegibles(id)
const asignar = useAsignarBusqueda()

const seleccionada = ref('')
const error = ref('')
watch(candidato, () => {
  seleccionada.value = ''
  error.value = ''
})

// Se conserva el último candidato para que el contenido no desaparezca durante la animación de cierre.
const mostrado = ref<CandidatoListado | null>(candidato.value)
watch(candidato, (nuevo) => {
  if (nuevo) mostrado.value = nuevo
})

const busquedas = computed(() => elegibles.data.value ?? [])
const nombre = computed(() => `${mostrado.value?.nombre ?? ''} ${mostrado.value?.apellido ?? ''}`.trim())
const visible = computed({
  get: () => candidato.value !== null,
  set: (abierto) => {
    if (!abierto && !asignar.isPending.value) candidato.value = null
  },
})

async function confirmar(): Promise<void> {
  if (!seleccionada.value || !candidato.value || asignar.isPending.value) return
  error.value = ''
  try {
    await asignar.mutateAsync({ busquedaId: seleccionada.value, candidatoId: candidato.value.id })
    candidato.value = null
    toast.removeAllGroups()
    toast.add({ severity: 'success', summary: 'Candidato asignado a la búsqueda correctamente', life: 5000 })
  } catch (e) {
    // Ya asignado u otro aviso: el diálogo sigue abierto para elegir otra búsqueda o cancelar.
    error.value = e instanceof Error ? e.message : 'Error de conexión con el servidor al asignar el candidato.'
  }
}
</script>

<template>
  <Dialog :pt="PT_DIALOGO" v-model:visible="visible" modal :draggable="false" :closable="!asignar.isPending.value" style="width: 36rem">
    <template #header>
      <div class="flex items-center gap-2.5">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
          <UserPlus class="h-5 w-5" />
        </div>
        <div>
          <h3 class="text-base font-bold text-dark-900">Asignar a Búsqueda</h3>
          <p class="text-xs font-normal text-dark-400">
            Candidato: <span class="font-semibold text-dark-700">{{ nombre }}</span>
          </p>
        </div>
      </div>
    </template>

    <div v-if="error" role="alert" data-testid="error-asignar" class="mb-4 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
      <AlertCircle class="h-4 w-4 shrink-0 text-red-600" /><span>{{ error }}</span>
    </div>

    <div v-if="elegibles.isPending.value" class="space-y-2 rounded-xl border border-dark-200 bg-dark-50/30 p-8 text-center text-dark-400">
      <Loader2 class="mx-auto h-8 w-8 animate-spin text-primary-600" />
      <p class="text-xs">Evaluando coincidencias de perfil con búsquedas abiertas...</p>
    </div>

    <div v-else-if="elegibles.isError.value" class="rounded-xl border border-dark-200 bg-dark-50/30 p-8 text-center text-dark-500">
      <p class="text-sm font-semibold text-dark-800">No se pudieron cargar las búsquedas.</p>
      <Button label="Reintentar" size="small" class="mt-3" @click="elegibles.refetch()" />
    </div>

    <div v-else-if="busquedas.length === 0" class="rounded-xl border border-dark-200 bg-dark-50/30 p-8 text-center text-dark-500" data-testid="sin-busquedas">
      <div class="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-50 text-amber-600"><AlertCircle class="h-6 w-6" /></div>
      <p class="text-sm font-semibold text-dark-800">No hay ninguna búsqueda que pueda aplicar.</p>
      <p class="mt-1 text-xs text-dark-400">
        El perfil del candidato no alcanza el nivel de compatibilidad requerido con las búsquedas abiertas o ya se
        encuentra asignado a ellas.
      </p>
    </div>

    <div v-else class="space-y-3">
      <div class="flex items-center justify-between">
        <label class="block text-xs font-semibold text-dark-700">Seleccionar Búsqueda Abierta Elegible</label>
        <span class="text-[11px] font-medium text-dark-400">{{ busquedas.length }} disponibles</span>
      </div>
      <div class="max-h-72 divide-y divide-dark-100 overflow-hidden overflow-y-auto rounded-xl border border-dark-200 bg-dark-50/30">
        <div
          v-for="b in busquedas"
          :key="b.id"
          role="radio"
          :aria-checked="seleccionada === b.id"
          tabindex="0"
          data-testid="busqueda-elegible"
          class="flex cursor-pointer items-center justify-between gap-3 p-3 text-left transition-colors"
          :class="seleccionada === b.id ? 'border-l-4 border-primary-600 bg-primary-50/70' : 'bg-transparent hover:bg-white'"
          @click="((seleccionada = b.id), (error = ''))"
          @keydown.enter.prevent="((seleccionada = b.id), (error = ''))"
          @keydown.space.prevent="((seleccionada = b.id), (error = ''))"
        >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="cursor-help rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold whitespace-nowrap text-emerald-700" :title="detalleMatch(b)">
                {{ b.match_porcentaje || b.porcentaje_match }}% match
              </span>
              <span v-if="b.seniority_compatible" class="flex items-center gap-1 rounded border border-blue-200/60 bg-blue-50 px-1.5 py-0.5 text-[10px] font-semibold whitespace-nowrap text-blue-700">
                <Award class="h-3 w-3 text-blue-600" /><span>Seniority compatible</span>
              </span>
            </div>
            <h4 class="mt-1 text-xs leading-snug font-semibold text-dark-800">
              <span class="font-normal text-dark-500">Búsqueda:</span> {{ b.titulo || 'Sin título' }}
            </h4>
            <div class="mt-0.5 flex items-center gap-2 text-[11px] text-dark-500">
              <span class="font-medium text-dark-600">{{ b.cliente || 'Cliente' }}</span>
              <span>•</span>
              <span>{{ b.seniority || b.modalidad || 'General' }}</span>
              <span v-if="b.id_busqueda">• <span class="font-mono text-dark-400">#{{ b.id_busqueda }}</span></span>
            </div>
            <div v-if="b.skills_coincidentes?.length" class="mt-1.5 flex flex-wrap gap-1">
              <span v-for="s in b.skills_coincidentes" :key="s" class="rounded border border-emerald-200/50 bg-emerald-50 px-1.5 text-[10px] text-emerald-700">{{ s }}</span>
            </div>
          </div>
          <div class="shrink-0">
            <div class="flex h-5 w-5 items-center justify-center rounded-full border transition-colors" :class="seleccionada === b.id ? 'border-primary-600 bg-primary-600 text-white' : 'border-dark-300 bg-white'">
              <Check v-if="seleccionada === b.id" class="h-3 w-3" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <Button label="Cancelar" unstyled :class="CLASE_BOTON_CANCELAR" :disabled="asignar.isPending.value" @click="visible = false" />
      <Button
        v-if="!elegibles.isPending.value && busquedas.length > 0"
        unstyled
        :class="CLASE_BOTON_CONFIRMAR"
        :disabled="!seleccionada || asignar.isPending.value"
        data-testid="confirmar-asignacion"
        @click="confirmar"
      >
        <Loader2 v-if="asignar.isPending.value" class="h-4 w-4 animate-spin" /><Check v-else class="h-4 w-4" />
        <span>{{ asignar.isPending.value ? 'Asignando...' : 'Confirmar Asignación' }}</span>
      </Button>
    </template>
  </Dialog>
</template>
