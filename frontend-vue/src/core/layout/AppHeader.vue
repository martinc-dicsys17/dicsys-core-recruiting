<script setup lang="ts">
import { ChevronDown, LogOut, Menu, User } from '@lucide/vue'
import { ref } from 'vue'

import logoDicsys from '@/assets/logo-dicsys-ai-azul.svg'
import { useSessionStore } from '@/core/stores/session'

defineEmits<{ alternarMenu: [] }>()

const sesion = useSessionStore()
const menuUsuarioAbierto = ref(false)
</script>

<template>
  <div class="dicsys-gradient fixed top-0 right-0 left-0 z-50 h-1"></div>

  <header class="fixed top-1 z-30 w-full border-b border-dark-200/50 bg-white/80 backdrop-blur-md">
    <div class="flex items-center justify-between px-4 py-3 lg:px-6">
      <div class="flex items-center">
        <button
          type="button"
          class="mr-3 rounded-xl p-2 text-dark-500 transition-colors hover:bg-dark-200/50"
          aria-label="Mostrar u ocultar el menú"
          @click="$emit('alternarMenu')"
        >
          <Menu class="h-5 w-5" />
        </button>
        <img
          v-if="sesion.empresa.logoUrl"
          :src="sesion.empresa.logoUrl"
          :alt="`Logo de ${sesion.empresa.nombre}`"
          class="mr-3 h-10 w-10 rounded-lg border border-dark-200 bg-white object-contain p-0.5"
        />
        <img v-else :src="logoDicsys" alt="Dicsys Core" class="mr-3 h-10 w-auto" />
        <span class="gradient-text hidden text-xl font-bold sm:block">Core</span>
      </div>

      <div class="flex items-center gap-2">
        <div class="relative ml-2">
          <button
            type="button"
            class="flex items-center gap-3 rounded-xl p-1.5 transition-colors hover:bg-dark-200/50"
            aria-haspopup="menu"
            :aria-expanded="menuUsuarioAbierto"
            @click="menuUsuarioAbierto = !menuUsuarioAbierto"
          >
            <img
              v-if="sesion.usuario.avatarUrl"
              :src="sesion.usuario.avatarUrl"
              :alt="`Foto de ${sesion.usuario.nombre}`"
              class="h-9 w-9 rounded-xl object-cover shadow-soft"
            />
            <span
              v-else
              class="flex h-9 w-9 items-center justify-center rounded-xl bg-linear-to-br from-primary-400 to-accent-purple text-sm font-semibold text-white shadow-soft"
            >
              {{ sesion.inicial }}
            </span>
            <span class="hidden text-left lg:block">
              <span class="block text-sm font-semibold text-dark-800">{{ sesion.usuario.nombre || 'Usuario' }}</span>
              <span class="block text-xs text-dark-400">{{ sesion.usuario.rol }}</span>
            </span>
            <ChevronDown class="hidden h-4 w-4 text-dark-400 lg:block" />
          </button>

          <template v-if="menuUsuarioAbierto">
            <div class="fixed inset-0 z-40" @click="menuUsuarioAbierto = false"></div>
            <div
              role="menu"
              class="absolute right-0 z-50 mt-2 w-64 animate-pop-in overflow-hidden rounded-2xl border border-dark-200/50 bg-white py-2 shadow-soft"
            >
              <div class="border-b border-dark-100 px-4 py-3">
                <p class="text-sm font-semibold text-dark-800">{{ sesion.usuario.nombre || sesion.usuario.email }}</p>
                <p class="text-xs text-dark-400">{{ sesion.usuario.email }}</p>
              </div>
              <a
                :href="sesion.enlaces.perfil"
                role="menuitem"
                class="flex items-center px-4 py-2.5 text-sm text-dark-600 transition-colors hover:bg-dark-50"
              >
                <User class="mr-3 h-4 w-4 text-dark-400" />Mi Perfil
              </a>
              <div class="mt-2 border-t border-dark-100 pt-2">
                <a
                  :href="sesion.enlaces.cerrarSesion"
                  role="menuitem"
                  class="flex items-center px-4 py-2.5 text-sm text-red-600 transition-colors hover:bg-red-50"
                >
                  <LogOut class="mr-3 h-4 w-4" />Cerrar Sesión
                </a>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </header>
</template>
