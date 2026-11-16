import type { RouteRecordRaw } from 'vue-router'

/**
 * Rutas del módulo Recruiting con carga diferida (lazy loading).
 *
 * Cada pantalla utiliza importación dinámica (`component: () => import(...)`)
 * para que Vite genere un chunk independiente que se descargue bajo demanda
 * únicamente cuando el usuario navegue a esa pantalla.
 */
export const recruitingRoutes: RouteRecordRaw[] = [
  {
    path: '/recruiting/blacklist',
    name: 'recruiting-blacklist',
    component: () => import('./blacklist/BlacklistPage.vue'),
    meta: { titulo: 'Blacklist - Recruiting' },
  },
  {
    // /recruiting/candidatos/nuevo (Flask) redirige acá conservando busqueda_id y volver.
    path: '/recruiting/candidatos/nuevo',
    name: 'recruiting-candidato-nuevo',
    component: () => import('./candidato-nuevo/NuevoCandidatoPage.vue'),
    meta: { titulo: 'Nuevo Candidato - Recruiting' },
  },
  // Futuras pantallas del módulo Recruiting se incorporarán aquí siguiendo el mismo patrón.
]
