<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

/**
 * Marco común de los modales del Pipeline (mismo fondo y panel que la pantalla anterior): se cierra con Escape o con
 * un clic afuera del panel. `ancho` lleva el ancho, los márgenes y el espaciado propios de cada modal.
 */
defineProps<{ ancho: string }>()
const emit = defineEmits<{ cerrar: [] }>()

const alPresionar = (evento: KeyboardEvent) => {
  if (evento.key === 'Escape') emit('cerrar')
}
onMounted(() => window.addEventListener('keydown', alPresionar))
onBeforeUnmount(() => window.removeEventListener('keydown', alPresionar))
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-900/50" role="dialog" aria-modal="true" @click.self="emit('cerrar')">
    <div class="bg-white rounded-2xl shadow-xl border border-dark-100 animate-fade-in flex flex-col" :class="ancho">
      <slot />
    </div>
  </div>
</template>
