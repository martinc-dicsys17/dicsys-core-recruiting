import './styles/main.css'

import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import PrimeVue, { defaultOptions } from 'primevue/config'
import ToastService from 'primevue/toastservice'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './router'
import { DicsysPreset } from './styles/primevue-preset'

const app = createApp(App)
  .use(createPinia())
  .use(router)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
    },
  })
  .use(PrimeVue, {
    theme: {
      preset: DicsysPreset,
      options: {
        darkModeSelector: '.dark',
        cssLayer: { name: 'primevue', order: 'theme, base, primevue, components, utilities' },
      },
    },
    locale: {
      ...defaultOptions.locale,
      emptyMessage: 'Sin resultados',
      emptyFilterMessage: 'Sin resultados',
      aria: {
        ...defaultOptions.locale?.aria,
        close: 'Cerrar',
        firstPageLabel: 'Primera página',
        lastPageLabel: 'Última página',
        nextPageLabel: 'Página siguiente',
        prevPageLabel: 'Página anterior',
        rowsPerPageLabel: 'Filas por página',
        pageLabel: 'Página {page}',
      },
    },
  })
  .use(ToastService)

// Se monta con la ruta inicial ya resuelta para que el menu abra el modulo de la pantalla actual.
void router.isReady().then(() => app.mount('#app'))
