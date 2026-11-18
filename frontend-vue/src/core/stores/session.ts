import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { leerBootstrap } from '@/core/bootstrap'

/** Sesion actual (solo lectura): la entrega Flask al servir la SPA. */
export const useSessionStore = defineStore('session', () => {
  const datos = ref(leerBootstrap())

  const usuario = computed(() => datos.value.usuario)
  const empresa = computed(() => datos.value.empresa)
  const enlaces = computed(() => datos.value.enlaces)
  const menus = computed(() => datos.value.menus)
  const esDemo = computed(() => datos.value.origen === 'demo')
  const esAdmin = computed(() => datos.value.esAdmin === true)
  const inicial = computed(() => (usuario.value.nombre || usuario.value.email || 'U').charAt(0).toUpperCase())

  return { usuario, empresa, enlaces, menus, esDemo, esAdmin, inicial }
})
