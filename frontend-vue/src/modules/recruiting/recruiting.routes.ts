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
    // /recruiting/candidatos (Flask) redirige acá conservando filtros, página y demás parámetros.
    path: '/recruiting/candidatos',
    name: 'recruiting-candidatos',
    component: () => import('./candidatos/CandidatosPage.vue'),
    meta: { titulo: 'Candidatos - Recruiting' },
  },
  {
    // /recruiting/candidatos/<id> (Flask) redirige acá conservando `volver`.
    path: '/recruiting/candidatos/:id([0-9a-fA-F-]{36})',
    name: 'recruiting-candidato-detalle',
    component: () => import('./candidato-detalle/CandidatoDetallePage.vue'),
    meta: { titulo: 'Candidato - Recruiting' },
  },
  {
    // /recruiting/candidatos/<id>?editar=1 (Flask) redirige acá conservando `volver`.
    path: '/recruiting/candidatos/:id([0-9a-fA-F-]{36})/editar',
    name: 'recruiting-candidato-editar',
    component: () => import('./candidato-editar/EditarCandidatoPage.vue'),
    meta: { titulo: 'Editar Candidato - Recruiting' },
  },
  {
    // /recruiting/candidatos/nuevo (Flask) redirige acá conservando busqueda_id y volver.
    path: '/recruiting/candidatos/nuevo',
    name: 'recruiting-candidato-nuevo',
    component: () => import('./candidato-nuevo/NuevoCandidatoPage.vue'),
    meta: { titulo: 'Nuevo Candidato - Recruiting' },
  },
  {
    // /recruiting/oportunidades (Flask) redirige acá conservando filtros y página.
    path: '/recruiting/oportunidades',
    name: 'recruiting-busquedas',
    component: () => import('./busquedas/BusquedasPage.vue'),
    meta: { titulo: 'Búsquedas - Recruiting' },
  },
  {
    // /recruiting/oportunidades/nueva (Flask) redirige acá.
    path: '/recruiting/oportunidades/nueva',
    name: 'recruiting-busqueda-nueva',
    component: () => import('./busqueda-nueva/NuevaBusquedaPage.vue'),
    meta: { titulo: 'Nueva Búsqueda - Recruiting' },
  },
  {
    // /recruiting/oportunidades/<id> y .../editar (Flask) redirigen acá; la edición es en la misma ficha (?edit=true).
    path: '/recruiting/oportunidades/:id([0-9a-fA-F-]{36})',
    name: 'recruiting-busqueda-detalle',
    component: () => import('./busqueda-detalle/BusquedaDetallePage.vue'),
    meta: { titulo: 'Búsqueda - Recruiting' },
  },
  // Futuras pantallas del módulo Recruiting se incorporarán aquí siguiendo el mismo patrón.
]
