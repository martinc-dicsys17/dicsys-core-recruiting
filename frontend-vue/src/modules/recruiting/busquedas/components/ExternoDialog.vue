<script setup lang="ts">
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import { computed, ref, watch } from 'vue'

import { useAsignarExterno, useQuitarExterno } from '../composables/useListadoBusquedas'
import type { Busqueda, ExternoDisponible } from '../types'

/** Asigna, reemplaza o quita el usuario externo de una búsqueda (solo grupo Recruiting). */
const busqueda = defineModel<Busqueda | null>('busqueda', { required: true })
defineProps<{ externos: ExternoDisponible[] }>()

const toast = useToast()
const asignar = useAsignarExterno()
const quitar = useQuitarExterno()
const guardando = computed(() => asignar.isPending.value || quitar.isPending.value)

const seleccionado = ref('')
watch(busqueda, (b) => (seleccionado.value = b?.externo_id || ''))

// Se conserva la última búsqueda para que el contenido no desaparezca durante la animación de cierre.
const mostrada = ref<Busqueda | null>(busqueda.value)
watch(busqueda, (nueva) => {
  if (nueva) mostrada.value = nueva
})
// La fila se actualiza en la caché con la respuesta: se muestra siempre la versión vigente.
const actual = computed(() => busqueda.value ?? mostrada.value)

const visible = computed({
  get: () => busqueda.value !== null,
  set: (abierto) => {
    if (!abierto) cerrar()
  },
})
const cerrar = () => (busqueda.value = null)
const aviso = (severity: 'success' | 'error', summary: string) => toast.add({ severity, summary, life: severity === 'error' ? 8000 : 5000 })

const textoActual = computed(() => {
  const b = actual.value
  if (!b?.externo_id) return 'Sin asignar'
  return b.externo_nombre + (b.externo_email ? ` (${b.externo_email})` : '')
})

async function guardar(): Promise<void> {
  const b = busqueda.value
  if (!b || guardando.value) return
  if (!seleccionado.value) {
    aviso('error', 'Selecciona un usuario externo.')
    return
  }
  if (seleccionado.value === b.externo_id) {
    cerrar()
    return
  }
  if (b.externo_id && !window.confirm('Se reemplazara el usuario externo asignado actualmente. Queres continuar?')) return
  try {
    await asignar.mutateAsync({ id: b.id, externoId: seleccionado.value })
    aviso('success', 'Usuario externo asignado correctamente.')
    cerrar()
  } catch (e) {
    aviso('error', e instanceof Error ? e.message : 'Error de conexion al asignar el usuario externo.')
  }
}

async function quitarAsignacion(): Promise<void> {
  const b = busqueda.value
  if (!b || !b.externo_id || guardando.value) return
  if (!window.confirm('Se quitara la asignacion del usuario externo. La busqueda y sus candidatos no se modifican. Queres continuar?')) return
  try {
    await quitar.mutateAsync(b.id)
    aviso('success', 'Asignacion del usuario externo quitada.')
    cerrar()
  } catch (e) {
    aviso('error', e instanceof Error ? e.message : 'Error de conexion al quitar la asignacion.')
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    dismissable-mask
    :draggable="false"
    unstyled
    :pt="{ mask: { class: 'fixed inset-0 z-50 flex items-center justify-center bg-dark-900/60 p-4' } }"
  >
    <template #container>
      <div class="w-[28rem] max-w-full space-y-4 rounded-xl bg-white p-5 shadow-xl" data-testid="modal-externo">
        <div>
          <h3 class="text-base font-semibold text-dark-900">Usuario externo de la búsqueda</h3>
          <p class="mt-0.5 text-xs text-dark-500">{{ actual?.titulo }}</p>
        </div>
        <p class="text-sm text-dark-700">
          Asignado actualmente: <span class="font-semibold" data-testid="externo-actual">{{ textoActual }}</span>
        </p>
        <select
          v-model="seleccionado"
          class="w-full rounded-lg border border-dark-200 bg-white px-3 py-2 text-sm"
          data-testid="select-externo"
        >
          <option value="" disabled>Seleccionar usuario externo</option>
          <option v-for="u in externos" :key="u.id" :value="u.id">{{ u.nombre }} ({{ u.email }})</option>
        </select>
        <p v-if="!externos.length" class="text-xs text-dark-400">No hay usuarios habilitados en el grupo Externos.</p>
        <div class="flex items-center justify-between gap-2 pt-1">
          <button
            v-if="actual?.externo_id"
            type="button"
            :disabled="guardando"
            class="cursor-pointer rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-60"
            data-testid="quitar-externo"
            @click="quitarAsignacion"
          >
            Quitar asignación
          </button>
          <div class="ml-auto flex items-center gap-2">
            <button
              type="button"
              class="cursor-pointer rounded-lg border border-dark-200 bg-dark-50 px-3 py-1.5 text-xs font-medium text-dark-700 hover:bg-dark-100"
              data-testid="cerrar-externo"
              @click="cerrar"
            >
              Cerrar
            </button>
            <button
              type="button"
              :disabled="guardando"
              class="cursor-pointer rounded-lg bg-primary-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
              data-testid="guardar-externo"
              @click="guardar"
            >
              Guardar
            </button>
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>
