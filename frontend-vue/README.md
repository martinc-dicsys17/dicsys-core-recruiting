# Dicsys Core - Nueva interfaz (Vue 3) - Piloto

Primera implementacion de la nueva arquitectura frontend. Convive con el frontend actual
(Flask + Jinja + HTMX/Alpine), que no se modifica: cada pantalla nueva vive bajo `/v2/...`.

Pantallas: **Blacklist** (`/v2/recruiting/blacklist`), solo de consulta y con datos ficticios.

## Stack

Vue 3 (Composition API, `<script setup>`) - TypeScript estricto - Vite - Vue Router -
Tailwind CSS 4 - Pinia (sesion) - TanStack Query (datos de servidor) - iconos Lucide
(los mismos del frontend actual) - PrimeVue 4 como biblioteca de componentes (en prueba).

### PrimeVue 4

- Version fijada en 4.x (`primevue@4` + `@primeuix/themes@2`; la 5 ya existe y no se usa).
- Tema: `src/styles/primevue-preset.ts` (preset Aura con la paleta Dicsys). Los ajustes visuales
  comunes a todos los componentes van ahi, no en cada pantalla.
- Convive con Tailwind por capas CSS (`@layer theme, base, primevue, components, utilities` en
  `main.css` y `cssLayer` en `main.ts`): las utilidades de Tailwind pueden ajustar un componente de PrimeVue.
- Los componentes se importan uno por uno en cada archivo (`import DataTable from 'primevue/datatable'`).
- Patron de listado + detalle: `modules/recruiting/blacklist/components/` (DataTable con seleccion de fila y Dialog).

## Como se integra

- `npm run build` compila la SPA dentro de `frontend/static/vue/`.
- Flask (`frontend/modulos/vue_app/app_module.py`) sirve ese `index.html` en `/v2/<ruta>`,
  detras del mismo `login_required` y la misma sesion de siempre, e inyecta en el HTML los
  datos de sesion (usuario, empresa, menu) en `<script id="dicsys-bootstrap">`.
- El acceso en el menu lateral actual sale de `PANTALLAS_VUE` (mismo archivo) y se dibuja en
  `core/base.html` con el estandar visual de pantallas Vue: fondo verde suave + etiqueta `VUE`.

## Comandos

```bash
npm install        # una vez
npm run build      # chequeo de tipos + compilacion hacia frontend/static/vue
npm run build:watch  # recompila al guardar (para ver los cambios en http://localhost/v2/...)
npm run dev        # servidor de desarrollo aislado: http://localhost:5173/v2/recruiting/blacklist
```

`npm run dev` no pasa por Flask: usa una sesion y un menu de demostracion.

## Estructura

```
src/
  core/            base comun: bootstrap de sesion, stores Pinia, layout (encabezado y menu)
  modules/<modulo>/<pantalla>/
    api/           contrato de datos (repository) y su implementacion
    composables/   consultas TanStack Query
    components/    componentes de la pantalla
    demo/          datos ficticios, separados de cualquier dato real
  router/          rutas de la SPA (base /v2/)
  styles/main.css  tokens de diseno (mismos colores y tipografia que core/base.html)
```

## Agregar una pantalla

1. Crear `src/modules/<modulo>/<pantalla>/` y registrar la ruta en `src/router/index.ts`.
2. Agregarla a `PANTALLAS_VUE` en `frontend/modulos/vue_app/app_module.py` para que aparezca en el menu.
3. `npm run build`.

## Pendiente de definir

- Datos reales de Blacklist: hoy `api/blacklist.repository.ts` devuelve `demo/blacklist.demo-data.ts`.
  Cuando exista el endpoint se agrega la implementacion HTTP (proxy `/api/v1` de Flask) sin tocar los componentes.
- Despliegue: `frontend/static/vue/` debe existir en el servidor (versionar el compilado o compilar en la imagen Docker).
- Permisos: hoy la pantalla solo exige sesion iniciada.
