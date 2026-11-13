<script setup lang="ts">
import { Compass } from '@lucide/vue'
</script>

<template>
  <div class="mx-auto flex max-w-sm animate-fade-in flex-col items-center py-24 text-center">
    <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-dark-200/60 text-dark-400">
      <Compass class="h-7 w-7" />
    </div>
    <h1 class="mb-1 text-lg font-bold text-dark-900">Pantalla no encontrada</h1>
    <p class="mb-5 text-sm text-dark-500">La dirección no corresponde a ninguna pantalla de la nueva interfaz.</p>
    <RouterLink
      :to="{ name: 'recruiting-blacklist' }"
      class="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-colors hover:bg-primary-700"
    >
      Ir a Blacklist
    </RouterLink>
  </div>
</template>
