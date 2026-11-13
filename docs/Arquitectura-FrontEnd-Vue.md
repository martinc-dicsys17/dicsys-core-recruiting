# Arquitectura Frontend Vue - Dicsys Core

Documento de referencia de la arquitectura del frontend nuevo (Vue 3). Toda pantalla nueva se construye con lo que
dice este documento, tomando Blacklist (`frontend-vue/src/modules/recruiting/blacklist/`) como implementación de
referencia (regla «Pantallas nuevas en Vue» de `CLAUDE.md`). Las pantallas legacy (Flask + Jinja + HTMX + Alpine)
siguen como están y se rigen por [`Arquitectura-FrontEnd.md`](Arquitectura-FrontEnd.md); se migran solo cuando se pide.

Fuentes que este documento ordena: `CLAUDE.md`, [`frontend-vue/README.md`](../frontend-vue/README.md),
[`Dicsys-Core-Tech-Stack.md`](Dicsys-Core-Tech-Stack.md), [`Auth-Navegador.md`](Auth-Navegador.md) (D-12, F07) y los
planes [`update-techs-v1-final.md`](../update-techs-v1-final.md) y [`update-techs-v2-final.md`](../update-techs-v2-final.md).
Los planes v2 están en estado «propuesta, sin implementar»: lo que se toma de ellos se marca abajo y no se da por
vigente sin decirlo.

## Cómo leer el estado de cada punto

| Marca | Significado |
|---|---|
| **Implementado** | Existe hoy en el repo y funciona (Blacklist, `vue_app`, F07). |
| **Adoptar** | Decisión vigente para toda pantalla nueva. Puede que todavía no esté construida: entonces se indica qué falta. |
| **Futuro** | Queda para una fase posterior (F08 o siguientes del plan v2). No se construye ahora. |
| **Pendiente** | Decisión sin confirmar. Se anota la recomendación; hasta que se decida, se sigue lo implementado. |

La idea central: **separar el contrato de cada pantalla de la infraestructura que la sirve.** El contrato (cómo pide
datos, cómo se autentica, de dónde sale su permiso y su lugar en el menú, cómo se estructura) se fija ahora, para que
las pantallas nuevas no se reescriban cuando cambie el hosting. La infraestructura (quién sirve los archivos, en qué
prefijo, cómo se publica el compilado) es transitoria y puede cambiar sin tocar pantallas.

---

## 1. Stack tecnológico

| Pieza | Elección | Estado |
|---|---|---|
| Framework | Vue 3, Composition API con `<script setup>` | Implementado |
| Lenguaje | TypeScript estricto (`strict`, `noUncheckedIndexedAccess`, `noUnusedLocals/Parameters` en `tsconfig.app.json`), verificado con `vue-tsc` | Implementado |
| Build | Vite, alias `@` → `src/` | Implementado |
| Rutas | Vue Router con `createWebHistory`, carga diferida por pantalla | Implementado. Guardas por permiso: Adoptar (falta construir, §5) |
| Estado global | Pinia, solo para sesión, empresa, menú, permisos y preferencias de interfaz; nunca respuestas de la API | Implementado (store `session`) |
| Estado de servidor | TanStack Query (`@tanstack/vue-query`) | Implementado |
| Acceso a datos | Repository por pantalla sobre un único cliente HTTP de `core/` | Repository: Implementado. Cliente HTTP: Adoptar (falta construir, §6) |
| Componentes | PrimeVue 4 (`primevue@4`, `@primeuix/themes@2`) con el preset `DicsysPreset` (Aura + paleta Dicsys) | Implementado. Modo con estilos o sin estilos: **Pendiente P1** |
| Estilos | Tailwind CSS 4 (plugin de Vite) con los tokens de [`Design-Tokens.md`](Design-Tokens.md) en `@theme` (`src/styles/main.css`) | Implementado |
| Íconos | Lucide, paquete `@lucide/vue`, importados uno por uno | Implementado (los planes dicen `lucide-vue-next`; ver §11) |
| Fuente | Plus Jakarta Sans | Implementado por CDN de Google Fonts. Empaquetarla en el build: **Pendiente P7** |
| Formularios | VeeValidate + Zod, errores 422 de FastAPI por campo | Futuro: se define con la primera pantalla que tenga formulario |
| Pruebas | Playwright E2E por recorrido de pantalla (exigido por `CLAUDE.md`); Vitest para lógica | **Pendiente P8** (no hay ninguno configurado en `frontend-vue/`) |
| Lint | ESLint (`eslint-plugin-vue`, typescript-eslint) y Prettier | **Pendiente P8** |
| Node | 24 LTS | Futuro, con `.nvmrc` (no existe todavía) |

Las versiones exactas las fija `frontend-vue/package-lock.json`. No se usan Nuxt, SSR, micro-frontends ni otro
framework por módulo.

**Interfaz y diseño.** Toda la interfaz en español; los textos fijos llevan tildes y los datos nuevos (incluidos los de
demostración) van sin tildes (reglas de `CLAUDE.md`). Las pantallas de Recruiting son solo para escritorio: sin
breakpoints `sm:`/`md:`/`lg:` ni adaptaciones móviles, salvo pedido expreso.

---

## 2. Estructura de carpetas

```
frontend-vue/
├── index.html                     # contiene el marcador <script id="dicsys-bootstrap"> que reemplaza Flask
├── vite.config.ts                 # base y carpeta de salida del build (§4)
├── package.json / package-lock.json
└── src/
    ├── main.ts                    # Pinia, Router, TanStack Query, PrimeVue (tema, capas CSS, textos en español)
    ├── App.vue
    ├── core/                      # lo común a toda la SPA; ninguna pantalla lo duplica
    │   ├── bootstrap.ts           # datos de arranque y prefijo BASE_SPA
    │   ├── stores/session.ts      # sesión (Pinia)
    │   ├── layout/                # AppShell, AppHeader, AppSidebar, menuIcons
    │   └── pages/                 # páginas generales (404)
    ├── router/index.ts            # router principal: junta las rutas de cada módulo
    ├── styles/
    │   ├── main.css               # capas CSS, tokens @theme y utilidades comunes
    │   └── primevue-preset.ts     # tema de PrimeVue; los ajustes comunes a todos los componentes van acá
    └── modules/<modulo>/
        ├── <modulo>.routes.ts     # rutas del módulo, con carga diferida
        └── <pantalla>/
            ├── <Pantalla>Page.vue # componente raíz de la pantalla
            ├── types.ts           # tipos de la pantalla
            ├── api/               # contrato (interface) del repository y su implementación
            ├── composables/       # consultas y mutaciones con TanStack Query
            ├── components/        # componentes propios de la pantalla
            ├── demo/              # datos ficticios, solo mientras no exista el endpoint
            └── *.ts               # helpers puros de la pantalla (búsqueda, presentación, formatos)
```

Reglas:

- Una pantalla no importa archivos de otra pantalla. Lo que se repite en dos pantallas sube a `core/` (o a
  `modules/<modulo>/` si es propio del módulo) recién cuando se repite, no antes.
- Los componentes de PrimeVue se importan uno por uno en cada archivo (`import DataTable from 'primevue/datatable'`).
- Los envoltorios propios (`AppTable`, `AppDialog`, `AppForm`) que menciona el plan **no se crean por adelantado**: se
  escriben cuando un patrón aparece en una segunda pantalla (ver P1).
- `demo/` no se mezcla con datos reales y se borra cuando la pantalla pasa a usar el endpoint.

---

## 3. Responsabilidades

| Capa | Le corresponde | No le corresponde |
|---|---|---|
| **FastAPI** | Negocio, validación, persistencia, permisos (los impone), empresa activa del JWT (multitenancy), menú y permisos efectivos (`GET /auth/me`, `GET /menus`), emisión y rotación de tokens | Presentación |
| **Flask** (mientras conviva, hasta F13) | Login, 2FA, selección de empresa y logout; servir `index.html` y los recursos compilados de la SPA; guarda de entrada de `/v2/*`; proxy `/api/v1/*` hacia FastAPI; las pantallas legacy | Lógica o datos de las pantallas Vue; nuevas pantallas Jinja |
| **Vue** | Pintar las pantallas nuevas, navegación interna, estado de servidor (TanStack Query), sesión en memoria, mostrar u ocultar según permisos | Decidir permisos de verdad, filtrar por empresa, duplicar reglas de negocio, tocar la base |

El backend es el que valida: la SPA solo orienta la interfaz (mismo principio que `CLAUDE.md` fija para el frontend).

---

## 4. Integración actual: Flask sirve la SPA (Implementado)

```
navegador ──► Flask (contenedor frontend)
               ├─ /v2/<ruta>         ──► vue_app.spa: index.html compilado + datos de arranque inyectados
               ├─ /static/vue/*      ──► recursos compilados (JS, CSS, imágenes)
               ├─ /api/v1/<path>     ──► proxy hacia FastAPI (agrega el Bearer de la sesión Flask)
               └─ resto              ──► pantallas legacy
```

- **Host**: `frontend/modulos/vue_app/app_module.py`, blueprint con `url_prefix='/v2'`. Cualquier ruta bajo `/v2` sirve
  el mismo `index.html` y la resuelve Vue Router. La respuesta va con `Cache-Control: no-store`. Si el compilado no
  existe, responde 503 con el aviso de compilar.
- **Datos de arranque**: Flask reemplaza `<script id="dicsys-bootstrap">null</script>` por un JSON (serializado con
  `htmlsafe_json_dumps`) con usuario, empresa, enlaces al legacy y menú. Este mecanismo es **transitorio**: ver §5.
- **Acceso desde el menú legacy**: `PANTALLAS_VUE` (mismo archivo) agrega las pantallas Vue al menú de
  `core/base.html` con el estándar visual de pantallas Vue (fondo verde suave y etiqueta `VUE`). También **transitorio**:
  ver §5.3.
- **Prefijo**: `/v2` vive en dos lugares y solo ahí: `url_prefix` del blueprint y `BASE_SPA` en `src/core/bootstrap.ts`.
- **Build**: `npm run build` (`vue-tsc -b && vite build`) compila con `base: '/static/vue/'` hacia
  `frontend/static/vue/`. Ese compilado **está versionado en git** y entra en la imagen del contenedor `frontend` por el
  `COPY . .` de su Dockerfile. `frontend-vue/` no forma parte de ninguna imagen ni de CI. Cómo se publica el compilado
  a futuro: **Pendiente P3**.
- **Desarrollo**: `npm run dev` levanta Vite en `http://localhost:5173` con una sesión de demostración (no pasa por
  Flask). `npm run build:watch` recompila al guardar; en desarrollo el override monta `./frontend` en el contenedor, así
  que los cambios se ven en `http://localhost/v2/...`.

Esta integración es la oficial **durante la etapa de transición** (§9). Se eligió sobre el contenedor propio del plan
porque F08 depende de F06 (infraestructura pendiente) y de producción encendida, y para un equipo de 1-2 devs construir
proxy y contenedor ahora no paga (regla de balance de `CLAUDE.md`).

---

## 5. Sesión, autenticación, menú y permisos

### 5.1 Arquitectura objetivo (D-12, Adoptar)

La decisión vigente es D-12, implementada del lado del backend en F07 (ver [`Auth-Navegador.md`](Auth-Navegador.md)):

- Un solo login, en Flask, hasta F13. FastAPI emite la cookie `HttpOnly` del refresh y Flask la reenvía al navegador.
- La SPA obtiene el access token con `POST /api/v1/auth/refresh` (con `X-Requested-With`), lo guarda **solo en memoria**
  (Pinia) y lo manda como `Authorization: Bearer`. Ante un 401 renueva una vez y reintenta; si el refresh devuelve 401,
  navegación completa a `/login`. Nunca `localStorage` ni `sessionStorage` para tokens.
- Usuario, empresa activa, empresas, permisos efectivos y menú salen de **`GET /api/v1/auth/me`** (existe:
  `backend/modules/auth/routers.py`, schema `SesionActual`).
- La SPA **no lee la sesión de Flask** (`update-techs-v2-final.md` §3: «Lo que no se hace»).
- Archivos que se piden sin Bearer (`<img>`, `<a href>`): URL firmada con `POST /api/v1/auth/descargas`.

Lo que **todavía no está** para usar este modelo de punta a punta:

- `AUTH_REFRESH_ENABLED` está en `false` por defecto: sin el flag, el login no emite la cookie del refresh.
- El proxy `/api/v1` de Flask (`frontend/app.py`, `proxy_api`) **pone el Bearer de la sesión Flask** en cada pedido; un
  `Authorization` que mande la SPA no llega al backend. El Bearer en memoria cobra sentido cuando la SPA hable con la
  API sin pasar por Flask (F08). En `auth/*` sí reenvía la cookie del refresh y `X-Requested-With`.

### 5.2 Cómo se aplica hoy (Adoptar)

Para que las pantallas nazcan preparadas sin depender de lo que falta:

1. **Toda llamada al backend pasa por el cliente HTTP de `core/`** (§6), contra `/api/v1/*` en el mismo origen. Cómo se
   autentica ese pedido es un detalle del cliente: en la transición, la sesión Flask vía el proxy; en F08, el Bearer en
   memoria con refresh. **Ninguna pantalla maneja tokens, cookies ni cabeceras de autenticación.**
2. **Usuario, menú y permisos vienen de `GET /auth/me`**, no del bloque inyectado. El bloque `dicsys-bootstrap` queda
   solo para lo que es propio de Flask mientras conviva (enlaces a inicio, perfil y cerrar sesión). Estado: **falta
   construir** el shell sobre `/auth/me`; Blacklist todavía usa el bloque inyectado.
3. **Los componentes leen la sesión del store `session`**, nunca del DOM ni de `window`. Así, cambiar la fuente
   (bloque → `/auth/me`) no toca las pantallas.

### 5.3 Permisos y menú de una pantalla Vue

- **Regla vigente**: el registry del backend es la fuente del menú y de los permisos (`recruiting.<item>`, etc.), y toda
  ruta del frontend exige su permiso (`CLAUDE.md`; [`modulos/recruiting.md`](modulos/recruiting.md)).
- **Adoptar**: cada pantalla Vue tiene su ítem en el registry con su código de permiso; la ruta de Flask que la sirve
  exige ese permiso; el router de Vue tiene una guarda que lo verifica con los permisos de `/auth/me` (solo para
  orientar: FastAPI impone en cada endpoint).
- **Implementado hoy, a reemplazar**: `vue_app` protege `/v2/*` solo con `login_required` y el menú usa `PANTALLAS_VUE`,
  que no conoce permisos. Cómo se representa en el registry un ítem que apunta a una ruta Vue en lugar de a un endpoint
  de Flask: **Pendiente P5**.
- El menú de la SPA tiene que respetar la estructura del registry, incluido el tercer nivel (`items` anidados, por
  ejemplo Administración → Proveedores). Hoy `AppSidebar.vue` dibuja solo dos niveles: **falta construir**.

---

## 6. Cliente HTTP y repositories (Adoptar)

```
Componente ──► composable (TanStack Query) ──► repository de la pantalla ──► cliente HTTP de core/ ──► /api/v1/*
```

- **Cliente HTTP** (`src/core/api/`, falta construir): un único punto que arma la URL (`/api/v1/...`, mismo origen),
  agrega `X-Requested-With` donde corresponde, maneja la autenticación (§5), interpreta los errores del contrato de la
  API (`{"detail": ...}`, 401, 403, 422, 429 con `Retry-After`) y propaga `X-Request-ID`. Las pantallas no hacen `fetch`
  directo.
- **Repository por pantalla** (`<pantalla>/api/<pantalla>.repository.ts`, implementado en Blacklist): una `interface`
  con las operaciones de la pantalla y una implementación exportada. La pantalla solo conoce la interface; pasar de
  `demo/` a la implementación HTTP cambia una exportación, no los componentes.
- **Composables** (`<pantalla>/composables/`): `useQuery`/`useMutation` con una clave por pantalla
  (`['<modulo>', '<pantalla>', ...]`); las mutaciones invalidan su clave y, si conviene, actualizan de forma optimista
  con vuelta atrás ante error (patrón de `useBlacklist.ts`).
- **Tipos**: los de request/response salen del contrato OpenAPI del backend. Si se generan con un cliente
  (`@hey-api/openapi-ts`) o se escriben a mano: **Pendiente P2**. Mientras no se decida, los tipos de cada pantalla van
  en su `types.ts` y deben coincidir con los schemas Pydantic del endpoint.
- **Composición**: antes de pedir un endpoint «por pantalla», primero llamadas paralelas con TanStack Query; un endpoint
  bootstrap en FastAPI solo si la pantalla necesita 4 o más pedidos o datos consistentes entre sí
  (`update-techs-v2-final.md` §4.5).

---

## 7. Router, Pinia, TanStack Query, PrimeVue, Tailwind e íconos

**Vue Router** (Implementado, salvo guardas)

- `createWebHistory(`${BASE_SPA}/`)`; cada módulo exporta sus rutas en `<modulo>.routes.ts` y `router/index.ts` las junta.
- Cada ruta: `path` = `/<modulo>/<pantalla>` (**la misma forma que tendrá la URL canónica**, sin `/v2`), `name` =
  `<modulo>-<pantalla>`, `component` con `import()` diferido, `meta.titulo` para el título de la pestaña.
- Navegación interna con `RouterLink`; hacia pantallas legacy, enlace normal (navegación completa).
- Guardas por permiso: Adoptar (§5.3), falta construir.

**Pinia** (Implementado)

- Solo sesión, empresa, menú, permisos y preferencias de interfaz. Las respuestas de la API viven en TanStack Query.

**TanStack Query** (Implementado)

- Configuración global en `main.ts` (`staleTime` 30 s, sin recarga al enfocar, un reintento). Una pantalla la cambia
  solo con motivo.
- Estados obligatorios en cada pantalla: carga, error con reintento y vacío (con y sin filtros), como Blacklist.

**PrimeVue** (Implementado; modo **Pendiente P1**)

- Tema único en `src/styles/primevue-preset.ts`; los ajustes visuales comunes van ahí, no en cada pantalla.
- Convive con Tailwind por capas (`@layer theme, base, primevue, components, utilities` en `main.css` y `cssLayer` en
  `main.ts`): una utilidad de Tailwind puede ajustar un componente.
- Textos de PrimeVue en español (`locale` en `main.ts`).

**Tailwind 4** (Implementado)

- Tokens en `@theme` de `main.css`, con los valores de [`Design-Tokens.md`](Design-Tokens.md). Si cambian los tokens del
  legacy, cambian acá.
- Utilidades comunes (`dicsys-gradient`, `gradient-text`, `campo`) en `main.css`. Colores sueltos (`bg-[#...]`) solo
  cuando el token no existe.

**Íconos** (Implementado)

- `@lucide/vue`, importados uno por uno. Los íconos del menú llegan del backend por nombre y se resuelven en
  `core/layout/menuIcons.ts`: todo ícono que use el registry tiene que estar en ese mapa (hoy faltan algunos, por
  ejemplo `truck`, `clipboard-check`, `settings-2`).

---

## 8. Cómo se agrega una pantalla nueva

1. Crear `src/modules/<modulo>/<pantalla>/` con la estructura de §2 (`<Pantalla>Page.vue`, `types.ts`, `api/`,
   `composables/`, `components/`).
2. Registrar la ruta en `src/modules/<modulo>/<modulo>.routes.ts` (y el módulo en `router/index.ts` si es nuevo), con la
   forma `/<modulo>/<pantalla>`.
3. Datos: repository sobre el cliente HTTP de `core/` (§6). Si el endpoint todavía no existe, implementación `demo/`
   explícita y visible en la interfaz («Datos de demostración»).
4. Permiso y menú: ítem en el registry con su código de permiso (§5.3). Hasta resolver P5, se agrega a `PANTALLAS_VUE`
   como se hizo con Blacklist, sabiendo que no controla permisos.
5. Diseño: componentes de PrimeVue con el tema común, tokens de Tailwind, interfaz en español, solo escritorio en
   Recruiting.
6. Compilar (`npm run build`) y versionar el compilado mientras siga vigente ese mecanismo (P3).
7. Pruebas: las de §10.

Lo que **no** se hace en una pantalla nueva: `fetch` directo, tokens o cookies en el código de la pantalla, leer el
bloque `dicsys-bootstrap` fuera de `core/`, componentes envoltorio «por si acaso», estilos globales fuera de `styles/`,
islas Vue dentro de templates Jinja.

---

## 9. Transición y hosting futuro

| | Transición (hoy, hasta F08) | Después de F08 (Futuro, plan v2) |
|---|---|---|
| Quién sirve la SPA | Flask, blueprint `vue_app` | Contenedor propio, independiente de Flask |
| Prefijo de las pantallas | `/v2/<modulo>/<pantalla>` | Prefijos canónicos `/<modulo>/<pantalla>` (las URLs no cambian más) |
| Recursos | `/static/vue/` | `/_vue/` |
| Llamadas a la API | `/api/v1/*` por el proxy de Flask, con la sesión Flask | `/api/*` directo a FastAPI con Bearer en memoria (D-12) |
| Menú del legacy | `PANTALLAS_VUE` en `core/base.html` | El registry; el ruteo por prefijo lo hace el proxy |
| Compilado | Versionado en `frontend/static/vue/` | Compilado en CI dentro de la imagen de la SPA |

El pase a F08 no debería tocar pantallas: cambia `base` en `vite.config.ts`, `BASE_SPA`, la estrategia de autenticación
dentro del cliente HTTP y la infraestructura. Por eso son obligatorias las reglas de §5.2, §6 y la forma de las rutas de
§7.

Qué infraestructura habrá en F08 está **Pendiente P4**: `update-techs-v2-final.md` §4.1 propone un proxy Caddy propio con
un contenedor `spa`, y [`Dicsys-Core-Tech-Stack.md`](Dicsys-Core-Tech-Stack.md) propone el Traefik de la plataforma sin
proxy propio y un contenedor `web` con nginx. Los dos documentos no coinciden. También es plan (no vigente) el canario
por la cookie `ui=vue` y la CSP estricta de la SPA.

El gate de `update-techs-v1-final.md` §6 («Mínimo para abrir `frontend-vue/`») no se cumplió cuando se abrió
`frontend-vue/` con Blacklist: la regla de pantallas nuevas en Vue de `CLAUDE.md` adelantó la apertura. Ese gate sigue
valiendo para F08 (proxy, contenedor y apagado progresivo de Flask), no para crear pantallas en la etapa de transición.

---

## 10. Build, pruebas y despliegue

**Build** (Implementado)

```bash
cd frontend-vue
npm install          # una vez
npm run typecheck    # vue-tsc
npm run build        # vue-tsc + vite build → frontend/static/vue/
npm run build:watch  # recompila al guardar
npm run dev          # Vite aislado en :5173 con sesión de demostración
```

**Pruebas**

- Implementado: `frontend/tests/smoke/test_vue_app_host.py` prueba el host (sesión obligatoria, datos de arranque, aviso
  sin compilado, acceso en el menú legacy y que el compilado versionado esté completo y Flask lo sirva). Corre con el
  resto de `frontend/tests` en CI.
- Adoptar (vigente por `CLAUDE.md`): Playwright E2E cuando el cambio afecta un recorrido de pantalla. No está
  configurado en `frontend-vue/`: **Pendiente P8** dónde vive y cómo corre.
- Pendiente P8: Vitest para composables y helpers puros (por ejemplo `busqueda.ts`), ESLint y Prettier.
- CI (`.github/workflows/test.yml`) no tiene Node: hoy no corre `vue-tsc` ni el build.

**Despliegue**

- Implementado: el compilado versionado viaja dentro de la imagen del `frontend` Flask; no hay paso de Node en el deploy.
- Riesgo conocido: nada verifica que `frontend/static/vue/` corresponda a `frontend-vue/src/`. Ver P3.
- Futuro (F08): imagen propia de la SPA compilada en CI y publicada por digest.

---

## 11. Decisiones pendientes

| # | Decisión | Opciones | Recomendación | Mientras tanto |
|---|---|---|---|---|
| P1 | Modo de PrimeVue | Con estilos y `DicsysPreset` (implementado) / sin estilos con tema Tailwind y envoltorios `App*`, previo bake-off contra shadcn-vue (plan v2 §0 fila 5) | Con estilos; envoltorios solo cuando un patrón se repita | Con estilos |
| P2 | Tipos y cliente de la API | Generados desde OpenAPI con `@hey-api/openapi-ts` y control de drift en CI (plan) / escritos a mano | Generar desde la primera pantalla con datos reales (hoy no existe el script de exportación del OpenAPI) | Tipos a mano en `types.ts`, alineados con los schemas |
| P3 | Publicación del compilado | Versionado en `frontend/static/vue/` (implementado) / compilado en la imagen del frontend con una etapa Node / versionado con un job de CI que recompile y compare | Compilar en la imagen (la misma etapa sirve en F08) | Versionado; recompilar siempre antes de commitear |
| P4 | Infraestructura de F08 | Proxy Caddy + contenedor `spa` (v2-final §4.1) / Traefik de la plataforma + contenedor `web` con nginx (Tech-Stack) | Resolver antes de abrir F08; no bloquea las pantallas | Flask sirve la SPA |
| P5 | Pantallas Vue en el registry | Cómo declara un ítem del registry que su destino es una ruta Vue (hoy `ruta` es un endpoint de Flask) y cómo exige su permiso la ruta de `vue_app` | Ítem del registry con su permiso + guarda en Flask y en Vue | `PANTALLAS_VUE` sin control de permisos |
| P6 | Activar `AUTH_REFRESH_ENABLED` | Encender la cookie del refresh en los entornos | Encenderla cuando el cliente HTTP la use | La SPA usa la sesión Flask vía el proxy |
| P7 | Fuente | Google Fonts por CDN (implementado) / empaquetada en el build (Tech-Stack) | Empaquetar (requisito para la CSP estricta futura) | CDN |
| P8 | Herramientas de calidad | Playwright (exigido), Vitest, ESLint y Prettier; dónde viven y cómo corren en CI (Node en CI) | Playwright y `vue-tsc` en CI primero | Pruebas del host en `frontend/tests` |

Diferencias con los planes que este documento deja anotadas, sin resolver por su cuenta:

- `update-techs-v2-final.md` §5 y `Dicsys-Core-Tech-Stack.md` nombran `lucide-vue-next`; lo implementado y vigente es
  `@lucide/vue`.
- El plan prevé `sincronizacion` y `parametros` como primeras pantallas Vue (F09); la primera fue Blacklist, en la
  etapa de transición.
- Las decisiones P1 a P8, cuando se tomen, se registran en este documento y en el plan que corresponda.
