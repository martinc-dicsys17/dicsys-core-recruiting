import { createRouter, createWebHistory } from 'vue-router'

import { BASE_SPA } from '@/core/bootstrap'
import { recruitingRoutes } from '@/modules/recruiting/recruiting.routes'

declare module 'vue-router' {
  interface RouteMeta {
    titulo?: string
  }
}

/**
 * Enrutador principal de Dicsys Core SPA.
 * Las rutas de cada módulo se importan con carga diferida (lazy loading).
 */
export const router = createRouter({
  history: createWebHistory(`${BASE_SPA}/`),
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

router.afterEach((to) => {
  document.title = to.meta.titulo ? `${to.meta.titulo} - Dicsys Core` : 'Dicsys Core'
})
