<script setup lang="ts">
import { ref } from 'vue'

import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const menuColapsado = ref(false)
</script>

<template>
  <div class="min-h-screen bg-dark-100 font-sans text-dark-800 antialiased">
    <AppHeader @alternar-menu="menuColapsado = !menuColapsado" />
    <div class="flex pt-[68px]">
      <AppSidebar :colapsado="menuColapsado" @expandir="menuColapsado = false" />
      <main
        class="min-h-[calc(100vh-68px)] min-w-0 flex-1 p-6 transition-all duration-300"
        :class="menuColapsado ? 'ml-[72px]' : 'ml-72'"
      >
        <RouterView />
      </main>
    </div>
  </div>
</template>
