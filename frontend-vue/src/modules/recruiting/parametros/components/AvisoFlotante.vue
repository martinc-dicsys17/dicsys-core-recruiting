<script setup lang="ts">
import { AlertCircle, CheckCircle } from '@lucide/vue'

import type { TipoAviso } from '../composables/useAviso'

defineProps<{ mensaje: string; tipo: TipoAviso }>()
</script>

<template>
  <Transition
    enter-active-class="transition ease-out duration-300"
    enter-from-class="opacity-0 translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition ease-in duration-200"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="mensaje"
      class="fixed top-5 right-5 z-50 flex max-w-md items-center gap-3 rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-lg"
      :class="tipo === 'exito' ? 'bg-emerald-600' : 'bg-rose-600'"
      role="status"
      aria-live="polite"
    >
      <CheckCircle v-if="tipo === 'exito'" class="h-4 w-4 shrink-0" />
      <AlertCircle v-else class="h-4 w-4 shrink-0" />
      <span>{{ mensaje }}</span>
    </div>
  </Transition>
</template>
