import { defineConfig } from '@playwright/test'

import { URL_FRONTEND } from './stack'

/**
 * Pruebas E2E del módulo de Candidatos (Nuevo Candidato, grilla y ficha) contra el stack AISLADO de
 * docker-compose.e2e.yml. Ejecutar desde frontend-vue/:  npm run e2e
 * El globalSetup levanta el stack, verifica que usa la base aislada y siembra datos ficticios; el globalTeardown
 * lo baja (y borra la base). No se instalan navegadores: se usa Microsoft Edge del equipo (canal «msedge»).
 */
export default defineConfig({
  testDir: './specs',
  outputDir: './.salida/artefactos',
  globalSetup: './global-setup.ts',
  globalTeardown: './global-teardown.ts',
  // Un solo trabajador: todas las pruebas comparten la misma base y varias dependen del orden de los datos.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [
    ['list'],
    ['html', { outputFolder: './.salida/informe', open: 'never' }],
    ['json', { outputFile: './.salida/resultado.json' }],
  ],
  use: {
    baseURL: URL_FRONTEND,
    channel: 'msedge',
    viewport: { width: 1440, height: 900 },
    locale: 'es-AR',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
    actionTimeout: 15_000,
  },
})
