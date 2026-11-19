import { createRouter, createWebHistory } from 'vue-router'

import { BASE_SPA } from '@/core/bootstrap'
import { useSessionStore } from '@/core/stores/session'
import { recruitingRoutes } from '@/modules/recruiting/recruiting.routes'

declare module 'vue-router' {
  interface RouteMeta {
    titulo?: string
    /** Nombre de la ruta cuyo ítem del menú se resalta en esta pantalla, si no es el que corresponde a su dirección. */
    itemMenu?: string
    /** Pantalla solo para administradores (Flask la protege igual al entrar por la URL; el backend valida cada llamada). */
    soloAdmin?: boolean
  }
}

/**
 * Enrutador principal de Dicsys Core SPA.
 * Las rutas de cada módulo se importan con carga diferida (lazy loading).
 *
 * `sensitive`: una variante en mayúsculas de una ruta (/recruiting/Parametros/...) no abre la pantalla. Flask solo
 * protege la dirección exacta y la variante caería en la ruta genérica de la SPA, que solo exige la sesión.
 */
export const router = createRouter({
  history: createWebHistory(`${BASE_SPA}/`),
  sensitive: true,
  routes: [
    { path: '/', redirect: { name: 'recruiting-blacklist' } },
    ...recruitingRoutes,
    {
      path: '/:resto(.*)*',
      name: 'no-encontrada',
      component: () => import('@/core/pages/NotFoundPage.vue'),
      meta: { titulo: 'Pantalla no encontrada' },
    },
  ],
})

/**
 * Pantallas de administradores: una navegación interna (sin pasar por Flask) de quien no lo es se convierte en una
 * carga completa de la misma URL, y Flask responde su 403 como en la pantalla anterior.
 */
router.beforeEach((to) => {
  if (to.meta.soloAdmin && !useSessionStore().esAdmin) {
    window.location.assign(`${BASE_SPA}${to.fullPath}`)
    return false
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.titulo ? `${to.meta.titulo} - Dicsys Core` : 'Dicsys Core'
})
