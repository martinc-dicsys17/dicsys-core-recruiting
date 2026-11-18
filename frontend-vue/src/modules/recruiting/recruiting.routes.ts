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
  {
    // /recruiting/gestion-busquedas y /recruiting/asignar-candidato (Flask) redirigen acá conservando vista y filtro.
    // El alias es la URL que arma Flask para el ítem «Pipeline» del menú: así el menú reconoce la pantalla como Vue.
    path: '/recruiting/gestion-busquedas',
    alias: '/recruiting/asignar-candidato',
    name: 'recruiting-pipeline',
    component: () => import('./pipeline/PipelinePage.vue'),
    meta: { titulo: 'Pipeline - Recruiting' },
  },
  {
    // /recruiting/oportunidades/<id>/pipeline (Flask) redirige acá conservando sus parámetros. En el menú se resalta
    // «Pipeline» (no «Búsquedas», aunque la dirección cuelgue de /recruiting/oportunidades), como antes.
    path: '/recruiting/oportunidades/:id([0-9a-fA-F-]{36})/pipeline',
    name: 'recruiting-pipeline-busqueda',
    component: () => import('./pipeline/PipelineBusquedaPage.vue'),
    meta: { titulo: 'Pipeline - Recruiting', itemMenu: 'recruiting-pipeline' },
  },
  {
    // /recruiting/parametros/<sección> (Flask) redirige acá conservando sus parámetros.
    path: '/recruiting/parametros',
    name: 'recruiting-parametros',
    component: () => import('./parametros/ConfiguracionPage.vue'),
    meta: { titulo: 'Parámetros - Recruiting' },
  },
  {
    path: '/recruiting/parametros/skills',
    name: 'recruiting-parametros-skills',
    component: () => import('./parametros/SkillsPage.vue'),
    meta: { titulo: 'Skills - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/habilidades',
    name: 'recruiting-parametros-habilidades',
    component: () => import('./parametros/HabilidadesPage.vue'),
    meta: { titulo: 'Habilidades - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/provincias',
    name: 'recruiting-parametros-provincias',
    component: () => import('./parametros/ProvinciasPage.vue'),
    meta: { titulo: 'Provincias - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/ciudades',
    name: 'recruiting-parametros-ciudades',
    component: () => import('./parametros/CiudadesPage.vue'),
    meta: { titulo: 'Ciudades - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/lideres',
    name: 'recruiting-parametros-lideres',
    component: () => import('./parametros/LideresPage.vue'),
    meta: { titulo: 'Líderes - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/reclutadores',
    name: 'recruiting-parametros-reclutadores',
    component: () => import('./parametros/ReclutadoresPage.vue'),
    meta: { titulo: 'Reclutadores - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/perfiles-profesionales',
    name: 'recruiting-parametros-perfiles',
    component: () => import('./parametros/PerfilesPage.vue'),
    meta: { titulo: 'Perfiles profesionales - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/motivos-blacklist',
    name: 'recruiting-parametros-motivos',
    component: () => import('./parametros/MotivosPage.vue'),
    meta: { titulo: 'Motivos de Blacklist - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/archivos-cv',
    name: 'recruiting-parametros-archivos-cv',
    component: () => import('./parametros/ArchivosCvPage.vue'),
    meta: { titulo: 'Archivos de CV - Parámetros de Recruiting' },
  },
  {
    path: '/recruiting/parametros/historial-cargas-cv',
    name: 'recruiting-parametros-historial-cargas-cv',
    component: () => import('./parametros/HistorialPage.vue'),
    meta: { titulo: 'Historial de cargas de CV - Parámetros de Recruiting' },
  },
  // Futuras pantallas del módulo Recruiting se incorporarán aquí siguiendo el mismo patrón.
]
