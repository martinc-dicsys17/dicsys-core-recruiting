import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// La SPA se compila dentro de frontend/static/vue para que Flask la sirva con la sesion actual.
// En desarrollo (npm run dev) corre sola en http://localhost:5173 con datos de sesion de demostracion.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/static/vue/' : '/',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: { port: 5173, strictPort: true },
  build: {
    outDir: fileURLToPath(new URL('../frontend/static/vue', import.meta.url)),
    emptyOutDir: true,
    chunkSizeWarningLimit: 600,
  },
}))
