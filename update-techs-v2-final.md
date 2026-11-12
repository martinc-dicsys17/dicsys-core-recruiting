# Migración a Vue 3 — Paso 2 (v2 final)

> **Estado:** propuesta consolidada, sin implementar.
> **Fecha:** 2026-09-07 · rama `feature/upgrade-tech-stack` @ `2d67931`.
> **Consolida:** `update-techs-v2.md` (plan corto: principios, proxy único, Fase 0, pilotos, olas por tamaño, tablero) y `update-techs-sol-v2.md` (plan largo: stack, convivencia por prefijos, fases 2A-2K módulo por módulo, DoD, testing, estado, riesgos, ADRs). Donde discrepaban, §0 dice qué se eligió y por qué. Las métricas se volvieron a medir sobre el repo con un solo criterio.
> **Relación con v1:** el Paso 1 es `update-techs-v1-final.md` (`F01..F07`) y se ejecuta antes. La **Fase 0** de los documentos v2 (backend listo para la SPA) **es F07** y no se repite acá: este documento arranca en `F08` y termina en `F13` con Flask apagado. Un solo plan, una sola numeración, un solo gate (§1).
> **Destino:** `director` (§14).

---

## 0. Qué cambia respecto a los documentos origen

| # | Tema | `update-techs-v2.md` | `update-techs-sol-v2.md` | v2-final |
|---|---|---|---|---|
| 1 | Paso 1 y Fase 0 | §2 + §3.3 | Releases 1A-1H + gate §13 | Viven en `update-techs-v1-final.md` (F01-F07). Acá queda solo el gate (§1) y cómo se usa la auth (§3) |
| 2 | Primer módulo | `parametros` (CRUD puro) | `sincronizacion` (read-only primero) | **`sincronizacion`** primero: el más chico (319 líneas, 7 `hx-*`), admin-only, arranca read-only y prueba acciones largas con confirmación. **`parametros`** segundo: valida formularios, validaciones y modales. Los dos en F09 |
| 3 | Segundo módulo grande | `soporte` como Piloto 2, "si rinde acá rinde en todo" | CRUD representativo y `soporte` al final | Orden incremental (chico → mediano → grande) **más un spike de `soporte` de 1 semana, descartable, después de los pilotos**: se aprende lo difícil temprano sin poner en producción el módulo más usado mientras el equipo aprende Vue |
| 4 | Server state | TanStack Query | Composables propios con cache e invalidación explícita | **TanStack Query** (`@tanstack/vue-query`): cache, dedupe, reintentos e invalidación sin escribirlos; las reglas de sol-v2 §30 se cumplen con él |
| 5 | Componentes | PrimeVue o shadcn-vue, elegir en el piloto | Componentes base propios | **PrimeVue 4** en modo unstyled con tema Tailwind sobre los tokens de `docs/Design-Tokens.md`, confirmado con un bake-off de 2 días contra shadcn-vue en F08. Motivo: 16 módulos de tablas, formularios y modales; `DataTable`, `Dialog`, `Toast` y `FileUpload` ahorran semanas. Componentes propios solo como wrappers |
| 6 | Routing de convivencia | SPA bajo `/app/*`, Flask en `/*`, redirects 301 al migrar | Prefijos canónicos por módulo migrado; `/v2` solo transitorio | **Prefijos canónicos**: el proxy manda cada prefijo migrado a la SPA y el resto a Flask. Las URLs no cambian nunca, no hay redirects y el rollback es sacar el prefijo de la lista. Assets de la SPA en `/_vue/*`. La SPA vive en un contenedor propio, `spa` (fila 16) |
| 7 | Retiro del código Flask de un módulo migrado | En el mismo PR, "nada por las dudas" | Conservar al menos una release estable | **Una release y como máximo 2 semanas**; el retiro es un pendiente propio por módulo en `director` para que no se estire |
| 8 | Canario | Feature flag en el proxy los primeros días | Grupo interno / canario | **Cookie `ui=vue`** por usuario, combinada con el prefijo. La setea el propio proxy en `/beta/vue/on` y `/off` (responde el `Set-Cookie` y redirige): cero rutas nuevas en Flask. Primero canario, después todos |
| 9 | Tests de la SPA | Vitest + Testing Library | Vitest + Vue Test Utils + Playwright | Vitest + Testing Library para componentes y composables; **Playwright** para E2E de happy paths y login/2FA |
| 10 | Páginas públicas con Open Graph (`/certificates/*`) | No lo trata | Pueden quedar server-rendered | **FastAPI + Jinja** para `/certificates/<id>` y su `.png` (WhatsApp y Twitter exigen HTML con OG, sin JS). QR y PDF se generan en el servidor (`qrcode` y `pypdf` ya están en el backend) |
| 11 | Métricas | 30.700 líneas, 162 templates, 284 HTMX, 147 Alpine | 1.199 refs HTMX, 273 rutas, 407 llamadas, 192 `render_template` | Re-medidas el 2026-09-07 (§2): 33.065 líneas, 164 templates, 281 rutas, 417 `api_request`, 192 `render_template`, 692 `hx-*`, 151 `x-data`, 100 `<form>`, 57 `HX-Trigger`, 6 `hx-swap-oob`, 2 polling |
| 12 | Recibos | Ola B, unir PDFs server-side | 2G, después de auth, uploads y auditoría | Vive en **tres prefijos** (`/recibos`, `/administracion/recibos`, `/nomina/recibos`) y sus pantallas de admin están en los templates de `administracion`: migra **junto con `administracion` y antes que `nomina`**, con reglas de proxy por prefijo más largo |
| 13 | Rutas que ninguno menciona | — | — | El callback OAuth de Webex vive en Flask (`/notificaciones/oauth/callback`) y los archivos pasan por el proxy Flask `/storage/*` (`app.py:128-134`): se migran explícitamente (F10 y F07/F08) |
| 14 | Estimación | 6-9 meses en total | Sin calendario | **8-11 meses en total** (Paso 1 + Paso 2). Más que v2 porque `soporte` + `innovacion` son 15.2k líneas, el 46 % del frontend, y estaban subponderados |
| 15 | Premisa de auth heredada | "el JWT nunca llega al navegador" | — | Falsa: viaja dentro de la cookie de sesión de Flask (v1-final §0 fila 14). No cambia el diseño, cambia el puente: FastAPI emite la cookie de refresh y la sesión Flask deja de ser la fuente para la SPA |
| 16 | Hosting de la SPA | `StaticFiles` de FastAPI o el proxy | ADR pendiente: FastAPI, proxy o storage/CDN | **Contenedor `spa` 100 % nuevo** (decidido con el usuario el 2026-09-07): imagen propia con Caddy sirviendo `dist/`; el proxy solo enruta. Deployar la SPA reinicia solo `spa`, las reglas cambian con `caddy reload`, y al final el contenedor Flask se apaga entero sin que nada nuevo haya vivido adentro ni nada viejo quede en el nuevo |

---

## 1. Gate de entrada y resumen

El Paso 2 empieza cuando el gate de `update-techs-v1-final.md` §6 está cumplido: F01 a F06a y F07 cerradas y en producción, con el DoD de F07 verificado (login por cookie, refresh, `/auth/me`, permisos con usuario restringido y descarga de PDF desde una página fuera de Flask). F06b (imágenes por digest) se cierra dentro de F08, antes del primer piloto. Es el mismo gate en los dos documentos; si cambia en uno, cambia en el otro.

| Fase | Qué | Esfuerzo | Depende de |
|---|---|---|---|
| F08 | Fundación: proxy único, contenedor `spa` propio, esqueleto de la SPA, cliente TS, shell con menú por permisos, build en CI | L (3-4 semanas) | F07 |
| F09 | Pilotos: `sincronizacion` y `parametros`; plomería completa de un módulo de punta a punta | M (2-3 semanas) | F08, F06b |
| F10 | Ola A, CRUD chicos: `notificaciones`, `operaciones`, `llm`, `hrbp`, `usuarios`, `permisos` + spike de `soporte` | L (4-6 semanas) | F09 |
| F11 | Ola B, medianos: `empresa`, `administracion` + `recibos`, `nomina` | L (6-9 semanas) | F10 |
| F12 | Ola C, grandes: `starmiles`, `soporte`, `innovacion` (con certificados públicos en FastAPI) | XL (10-14 semanas; 8-12 con dos devs) | F11 |
| F13 | Core y apagado: login/2FA/recuperación/perfil/selector/notificaciones en Vue; inversión del puente; Flask eliminado | M (3-4 semanas) | F12 |

Regla de oro (v1 y v2): inversión mínima en el legacy, completa en backend y SPA. Métrica única de avance: **líneas de template Jinja restantes** (hoy 33.065) y **módulos apagados / 16**.

---

## 2. Diagnóstico (re-medido 2026-09-07)

| Módulo | Prefijo Flask | Templates | Líneas | Rutas | `api_request` | `hx-*` | `x-data` | `<form>` | Fase |
|---|---|---|---|---|---|---|---|---|---|
| sincronizacion | `/configuracion/sincronizacion` | 3 | 319 | 4 | 8 | 7 | 0 | 0 | F09 · piloto 1 |
| parametros | `/parametros` | 4 | 373 | 6 | 9 | 30 | 1 | 4 | F09 · piloto 2 |
| notificaciones | `/notificaciones` (incluye `/oauth/callback` de Webex) | 3 | 245 | 4 | 5 | 9 | 0 | 0 | F10 |
| operaciones | `/operaciones` | 3 | 367 | 4 | 8 | 9 | 2 | 1 | F10 |
| llm | `/llm` | 4 | 415 | 4 | 4 | 23 | 2 | 2 | F10 |
| hrbp | `/hrbp` | 6 | 440 | 8 | 12 | 24 | 3 | 3 | F10 |
| usuarios | `/usuarios` | 3 | 773 | 7 | 17 | 19 | 8 | 1 | F10 |
| permisos | `/permisos` | 5 | 690 | 10 | 19 | 27 | 5 | 4 | F10, último: toca el menú global |
| empresa | `/empresa` | 4 | 1.289 | 14 | 14 | 36 | 6 | 3 | F11 |
| recibos | `/recibos` · `/administracion/recibos` · `/nomina/recibos` | 1 | 500 | 18 | 10 | 0 | 2 | 1 | F11, con administracion |
| administracion | `/administracion` | 16 | 2.657 | 16 | 19 | 124 | 12 | 6 | F11 |
| nomina | `/nomina` | 21 | 3.932 | 29 | 60 | 76 | 18 | 5 | F11 |
| starmiles | `/starmiles` | 27 | 3.330 | 40 | 54 | 58 | 17 | 11 | F12 |
| soporte | `/soporte` | 29 | 8.792 | 60 | 95 | 61 | 38 | 38 | F12 |
| innovacion | `/innovacion` · `/certificates` (público) | 20 | 6.436 | 31 | 48 | 148 | 16 | 9 | F12 |
| core | `/` (login, 2FA, recuperación, dashboard, perfil, `/health`, `/storage/*`) | 15 | 2.507 | 26 | 33 | 41 | 21 | 12 | F13 |
| **Total** | | **164** | **33.065** | **281** | **417** | **692** | **151** | **100** | |

Dónde duele: `innovacion/mi_path.html` 2.509 líneas, `soporte/tickets.html` 1.242, `soporte/partials/ticket_detalle.html` 1.203, `innovacion/licencias_list.html` 1.025, `soporte/stock.html` 1.014, `nomina/empleados_form.html` 821. Cuatro paradigmas conviven en esas pantallas (Jinja + HTMX + Alpine + JS imperativo); 57 `HX-Trigger` y 6 `hx-swap-oob` coordinan actualizaciones cruzadas (StarMiles, soporte) que en Vue pasan a ser estado explícito. El BFF Flask compone 417 llamadas a FastAPI para 192 `render_template`: más de dos llamadas por pantalla en promedio, el insumo para decidir endpoints bootstrap (§4.5).

---

## 3. Auth y sesión durante la convivencia

El modelo se construye en F07; acá va cómo se usa:

- **Un solo login, en Flask, hasta F13.** El usuario entra por `/login` como hoy. Flask llama a `POST /api/v1/auth/login` (y `seleccionar-empresa`, 2FA) y **reenvía el `Set-Cookie`** de refresh que emite FastAPI. Por el proxy único (§4) la cookie vale para `/api/v1/auth/*`.
- **La SPA arranca sin pedir credenciales**: llama a `POST /api/v1/auth/refresh` (la cookie ya está), recibe un access token corto y lo guarda **solo en memoria** (Pinia, nunca `localStorage`). Antes de expirar, o ante un 401, vuelve a `refresh`; si `refresh` devuelve 401, navegación completa a `/login`.
- **Empresa activa**: viaja en el access token como hoy (`empresa_id`); cambiar de empresa es `seleccionar-empresa` + `refresh`. Flask y la SPA ven la misma empresa porque la fuente es FastAPI.
- **Permisos y menú**: `GET /api/v1/auth/me` (F07) devuelve usuario, empresa, empresas disponibles, permisos efectivos y menú. La SPA solo muestra u oculta; **FastAPI impone**.
- **CSRF**: los endpoints con cookie (`refresh`, `logout`) exigen la cabecera `X-Requested-With` y `SameSite=Lax`. El resto va con Bearer y no es vulnerable a CSRF.
- **Archivos**: lo que hoy pasa por el proxy Flask `/storage/*` se pide a FastAPI. Para `fetch` va con Bearer; para `<img>` y `<a href>` F07 decide entre aceptar la cookie en esos GET o emitir **URLs firmadas de corta duración** (GCS ya lo permite).
- **Inversión del puente (F13)**: la pantalla de login pasa a Vue, la SPA llama a `login` directo, Flask deja de participar y se apaga.
- **Logout** revoca el refresh (rotación + tabla `auth_refresh_tokens`) y borra la sesión Flask mientras conviva.

Lo que no se hace: tokens en `localStorage` o `sessionStorage`; dos logins; sesiones Flask leídas por la SPA; un JWT distinto por mundo.

---

## 4. Arquitectura de convivencia

### 4.1 Proxy único

Dos contenedores de frontend, uno viejo y uno 100 % nuevo, y un `proxy` (Caddy) delante que toma el puerto 80 que hoy publica Flask. Un solo origen: sin CORS, cookies compartidas, rollback por configuración.

```
navegador ──► proxy (Caddy, :80)
               ├─ /api/*                      ──► backend:6001   (FastAPI)
               ├─ /_vue/*                     ──► spa:80         (contenedor nuevo: Caddy file_server con dist/)
               ├─ prefijos migrados (lista)   ──► spa:80         (history fallback a index.html en el propio spa)
               │    /configuracion/sincronizacion*, /parametros*, …
               ├─ /beta/vue/on | /off         ──► el proxy setea la cookie ui=vue y redirige (canario)
               ├─ /certificates/*             ──► backend (FastAPI + Jinja, público con OG)   [desde F12]
               └─ /*                          ──► frontend:80     (contenedor viejo: Flask, decrece hasta apagarse en F13)
```

Reglas:

- La **lista de prefijos migrados** es un archivo versionado (`proxy/Caddyfile`), un PR por cambio. Caddy ordena los `handle` por longitud de path, así que **prefijo más largo gana**: `/nomina/recibos*` puede ir a Vue mientras `/nomina/*` sigue en Flask.
- **Canario**: la regla de un prefijo se activa primero solo si existe la cookie `ui=vue` (matcher `header Cookie *ui=vue*`). El propio proxy atiende `/beta/vue/on` y `/beta/vue/off` (responde el `Set-Cookie` y redirige a `/`) para usuarios internos; Flask no cambia. Cuando el módulo se declara principal, se quita la condición de cookie.
- **Rollback de ruta**: sacar el prefijo de la lista y redeployar el proxy. Segundos, sin tocar código.
- **`spa` es un contenedor 100 % nuevo**: Dockerfile propio en `frontend-vue/` (stage `node:24-alpine` compila `dist/`; imagen final Caddy con `file_server` y `try_files {path} /index.html`), healthcheck propio, sin volúmenes ni variables de Flask. Deployar la SPA reinicia solo `spa`; el proxy no se toca y sigue atendiendo Flask y la API. Alternativas registradas y descartadas: compilar el bundle dentro de la imagen del proxy (cada deploy de la SPA reinicia el router de todos) y `StaticFiles` de FastAPI (acopla el release de la SPA al del backend).
- Desarrollo: el mismo `proxy` en `docker-compose.override.yml` apuntando a Vite (`:5173`, HMR por websocket) en vez de a `spa`. Un solo origen también en dev; el puente de sesión funciona igual.
- TLS y cabeceras: lo que hoy termina TLS delante de Flask (pendiente de confirmar en v1-final F01) pasa a apuntar al proxy; Caddy puede terminar TLS él mismo si no hay nada delante. Flask ya usa `ProxyFix` de un salto y depende de `X-Forwarded-Proto` para generar `https` en el `og:image` (`app.py:28-32`): el proxy lleva `trusted_proxies` para respetar las cabeceras del terminador, o `ProxyFix` sube a dos saltos. Si no, las previews de certificados se rompen.

### 4.2 Navegación entre mundos

- Flask enlaza a un módulo migrado con un `<a href>` normal: el proxy lo manda a la SPA. Los templates Jinja no cambian.
- La SPA enlaza a un módulo legacy con navegación completa (`window.location`), nunca con `router-link`. El router de la SPA solo declara los prefijos migrados; cualquier otra ruta hace navegación completa y cae en Flask.
- **No se monta Vue dentro de templates Jinja** ni HTMX y Vue controlan el mismo DOM. Un módulo está en un mundo o en el otro.
- Identidad visual única: el tema de la SPA sale de `docs/Design-Tokens.md` (colores `primary/accent/dark`, Plus Jakarta Sans, sombras, animaciones). La convivencia no se nota.
- Un solo layout: el shell de la SPA replica sidebar y header de `base.html`; la estructura del menú es la misma porque sale de `/auth/me`.

### 4.3 Retiro del legacy por módulo y apagado completo

Cuando un módulo se declara principal en Vue (canario cerrado), el código Flask queda **una release y como máximo 2 semanas**. Después, un PR propio elimina blueprint, templates y parciales (eliminados, no comentados). Cada módulo tiene en `director` un pendiente "retiro Flask" con fecha.

El contenedor viejo se vacía de a un módulo por dos vías: el tráfico se le saca por prefijo en el proxy y el código se le borra en cada retiro. Durante toda la convivencia, lo único que cambia en él son tres cosas: la seguridad de F01, dejar de publicar el puerto 80 (una línea del compose) y reenviar el `Set-Cookie` de refresh en el login (F07, unas pocas líneas). Nada nuevo vive adentro; nada viejo vive en `spa` ni en el proxy. Por eso el apagado final (F13) es quirúrgico: se elimina el servicio `frontend`, se saca la regla `/*` → Flask y el proxy queda con dos upstreams, `backend` y `spa`. Lo que no se hace es correr los dos frontends completos en paralelo para un solo switch al final: eso sería el big-bang con otro nombre.

### 4.4 Rutas especiales

- `/health`: el proxy expone el suyo; Flask y FastAPI conservan los propios para el compose.
- `/favicon.ico` y `/static/*` de Flask siguen en Flask hasta F13; la SPA tiene los suyos bajo `/_vue/`.
- `/notificaciones/oauth/callback` (OAuth de Webex, redirect URI derivado del host): migra en F10 como ruta de la SPA que llama al endpoint de FastAPI, o pasa directo a FastAPI si el intercambio del código ya vive ahí. Se decide al abrir `notificaciones`.
- `/certificates/<id>` y `/certificates/<id>/<slug>.png`: público, con Open Graph; pasa a FastAPI + Jinja en F12.

### 4.5 API: composición y endpoints bootstrap

Flask hoy compone más de dos llamadas por pantalla en promedio (417 `api_request` para 192 `render_template`). Antes de migrar cada pantalla se decide, en este orden: (1) llamadas paralelas desde la SPA con TanStack Query; (2) catálogos cacheados con invalidación explícita; (3) **endpoint bootstrap** en FastAPI solo cuando una pantalla necesitaría 4 o más requests para pintarse o cuando los datos deben ser consistentes entre sí (contadores + lista). No se crea un endpoint "por pantalla" por reflejo. La auditoría por módulo se hace al abrir su pendiente, no toda al principio (F07 ya la hizo para los pilotos).

---

## 5. Stack de la SPA

| Pieza | Elección | Nota |
|---|---|---|
| Framework | Vue 3 (Composition API, `<script setup>`) | Última mayor al abrir F08; las versiones exactas las fija el lockfile de F08 |
| Build | Vite | HMR, `server.proxy` en dev, `base: '/_vue/'` |
| Lenguaje | TypeScript estricto | El cliente generado lo aprovecha |
| Routing | Vue Router, `createWebHistory()`, guards por permiso desde `/auth/me`, lazy loading por módulo | Solo prefijos migrados |
| Estado global | Pinia, limitado a auth, empresa activa, empresas disponibles, menú/permisos, preferencias de UI | Nada de responses completos |
| Server state | TanStack Query (`@tanstack/vue-query`) | Cache, dedupe, reintentos, invalidación explícita por mutación |
| Cliente API | Generado con `@hey-api/openapi-ts` desde `/openapi.json`; `npm run generate-api`; check de drift en CI | No se escriben fetchers a mano |
| Estilos | Tailwind 4 (plugin Vite) con `@theme` desde `docs/Design-Tokens.md` | Misma identidad que el legacy |
| Componentes | PrimeVue 4 unstyled + tema Tailwind (bake-off de 2 días contra shadcn-vue en F08) | Wrappers propios (`AppTable`, `AppDialog`, `AppForm`) para no acoplar los módulos a la librería |
| Iconos | `lucide-vue-next` | Mismo set que hoy |
| Formularios | VeeValidate + Zod, o el validador de la librería elegida | Errores 422 de FastAPI mapeados a campos |
| Tests | Vitest + Testing Library (componentes, composables); Playwright (E2E happy paths, login/2FA) | La UI actual tiene 0 tests automatizados |
| Lint | ESLint + `eslint-plugin-vue` + typescript-eslint; Prettier | En CI |
| Node | 24 LTS (local ya está en 24.12) | `node:24-alpine` en el stage de build |
| API reference | Scalar (F07) | El equipo frontend vive ahí |
| Hosting | Contenedor `spa` propio: Caddy `file_server` sirviendo `dist/` con fallback a `index.html`; el proxy enruta | Deploy independiente del router y del backend (§4.1) |

No: Nuxt ni SSR (app interna autenticada; las páginas públicas van por FastAPI + Jinja), micro-frontends, otro framework por módulo.

---

## 6. Principios y reglas de convivencia

1. **Sin big-bang**: la migración es por módulo; producción nunca depende de una rama larga. Cada PR de módulo es desplegable y reversible por ruta.
2. **Sin islas permanentes**: no hay Vue dentro de Jinja ni HTMX dentro de Vue.
3. **Convivencia con rumbo**: toda pantalla nueva nace en Vue, aunque su módulo siga en Flask; el legacy solo recibe bugfixes.
4. **El backend manda**: FastAPI es la única fuente de verdad para negocio, autorización, tenant y persistencia. Vue no duplica reglas ni cálculos.
5. **Un solo login y una sola sesión** (§3).
6. **Contrato primero**: el cliente TS se regenera en CI; un cambio de API que rompe la SPA rompe el build, nunca se descubre en producción.
7. **Un módulo migrado se retira del legacy** en el plazo de §4.3; nada queda "por las dudas".
8. **No mezclar** el cutover de un módulo con upgrades de DB, driver o runtime en el mismo release.
9. **Sin tokens en almacenamiento persistente** del navegador; sin datos sensibles cacheados más allá de la sesión.
10. **Paridad antes que mejora**: primero el módulo funciona igual (checklist), después se mejora. Excepción explícita: las pantallas gigantes (`mi_path`, tickets) se rediseñan en componentes, no se traducen 1:1.
11. **Tablero visible**: cada PR de migración actualiza el pendiente en `director`; §13 sale de ahí.

---

## 7. Plan por fases

Convenciones: cada módulo es un pendiente con sub-fases; el DoD de §8 aplica a todos. **(persona)** = depende del usuario.

### F08 — Fundación: proxy, esqueleto, shell

Esfuerzo L (3-4 semanas) · depende de F07 · incluye el cierre de F06b. El esqueleto y el bake-off pueden arrancar mientras F07 termina; el proxy y el puente, no.

- [ ] Servicio `proxy` (Caddy) en el compose con las reglas de §4.1: `/api/*` → backend, `/*` → Flask, lista de prefijos vacía, matcher de canario, rutas `/beta/vue/on|off`, `trusted_proxies` hacia el terminador TLS. Flask deja de publicar el puerto 80. Verificar el puente de sesión de F07 de punta a punta (login en Flask → `refresh` en `/api` con la cookie) y que el `og:image` de certificados siga saliendo en `https`.
- [ ] Servicio `spa` 100 % nuevo: `frontend-vue/Dockerfile` (stage `node:24-alpine` → imagen Caddy con `file_server` y `try_files` a `index.html`), healthcheck, sin volúmenes; el proxy enruta `/_vue/*` y los prefijos migrados a `spa`. Verificar que un deploy de `spa` no reinicia `proxy`.
- [ ] **(persona)** Apuntar la terminación TLS existente al proxy, o habilitar TLS en Caddy.
- [ ] `frontend-vue/` con Vite + Vue 3 + TS estricto + ESLint/Prettier + Vitest + Playwright; `base: '/_vue/'`; `.nvmrc`.
- [ ] Tailwind 4 con `@theme` desde `docs/Design-Tokens.md`; fuente Plus Jakarta Sans.
- [ ] Bake-off de 2 días PrimeVue contra shadcn-vue con una tabla paginada, un formulario con validación y un diálogo, sobre los tokens. Registrar la decisión.
- [ ] Cliente TS: script `generate-api` (exporta `/openapi.json` con `uv run python -m backend.export_openapi` y corre `@hey-api/openapi-ts`); cliente commiteado; job de CI que regenera y falla con diff.
- [ ] Auth store y cliente HTTP: `refresh` al arrancar, access token en memoria, interceptor de 401 → `refresh` → reintento → `/login`; manejo global de 403.
- [ ] Shell: layout, sidebar con **menú dinámico desde `/auth/me`**, header con empresa activa y selector (llama a `seleccionar-empresa` + `refresh`), perfil (enlace al legacy hasta F13), toasts, loading global, páginas 403/404/500, breadcrumbs.
- [ ] Componentes base como wrappers: `AppTable` (paginación, orden, filtros en query params), `AppForm` y campos, `AppDialog`, `AppConfirm`, `AppUploader`, estados vacío/error/loading, badges.
- [ ] Router: guards por permiso, lazy loading por módulo, navegación completa para rutas no migradas.
- [ ] `X-Request-ID` propagado desde la SPA (lo genera el proxy si no viene) para correlacionar con FastAPI.
- [ ] CI de la SPA: lint + `vue-tsc` + vitest + build + drift del cliente; imágenes `spa` y `proxy` publicadas por digest como en v1-final F06b (**cierra F06b**).
- [ ] `docs/Arquitectura-FrontEnd-Vue.md`: carpetas, cómo generar el cliente, cómo agregar un módulo, cómo se declara un prefijo en el proxy, cómo se hace canario y rollback.
- [ ] Playwright: login en Flask → entrar a una ruta de prueba `/vue/hola` protegida por guard → ver el menú del usuario.

DoD: un usuario logueado en Flask entra a la ruta de prueba, ve el shell con **su** menú según permisos y una pantalla protegida por guard; cambiar de empresa se refleja en ambos mundos; una URL profunda carga; rollback de ruta probado; un deploy de `spa` no interrumpe a Flask ni a la API; CI verde con drift check.

### F09 — Pilotos: `sincronizacion` y `parametros`

Esfuerzo M (2-3 semanas) · depende de F08 y F06b.

**Piloto 1 — `sincronizacion`** (`/configuracion/sincronizacion`; 4 rutas, 8 llamadas; tabla, ejecutar, toggle, modal de logs):

1. Listado y logs read-only (permisos, loading, errores).
2. Toggle activo.
3. Ejecución con confirmación e **idempotencia**: el backend ya serializa por advisory lock; verificar que un doble click no encole dos corridas.
4. Canario con `ui=vue` para usuarios internos; ambos mundos contra el mismo FastAPI.
5. Vue principal; Flask conservado según §4.3; pendiente de retiro creado.

**Piloto 2 — `parametros`** (`/parametros`; 6 rutas, 30 `hx-*`, 4 formularios, modales de Webex con validaciones): valida el patrón CRUD completo (lista + filtros en query params + alta/edición en diálogo + borrado con confirmación + errores 422 mapeados a campos). Conservar las validaciones existentes. Es la configuración runtime del sistema: QA con el usuario que la administra.

DoD: los dos módulos cumplen §8; existe un **patrón CRUD documentado** en `docs/Arquitectura-FrontEnd-Vue.md` que un módulo nuevo copia sin copiar una vista entera; rollback de ruta ensayado en producción una vez.

### F10 — Ola A: CRUD chicos + spike de `soporte`

Esfuerzo L (4-6 semanas) · depende de F09 · 2.930 líneas.

Orden: `notificaciones` (incluye decidir el callback OAuth de Webex, §4.4) → `operaciones` → `llm` → `hrbp` → `usuarios` (passwords, reset de 2FA, avatar, magic link: después de los CRUD simples) → `permisos` (último: al cambiar grupos hay que refrescar el contexto global; la SPA invalida `/auth/me`).

- [ ] Un pendiente por módulo con las sub-fases del patrón CRUD; muy paralelizable y muy asistible con IA (la conversión es mecánica; el cuello es el QA).
- [ ] **Spike de `soporte`** (1 semana, rama descartable): tabla de tickets con filtros, drawer de detalle y una columna del kanban, con la librería elegida. Objetivo: validar los patrones de pantallas ricas (estado compartido entre tabla, kanban y contadores; modales anidados; uploads de evidencias) antes de diseñar F11 y F12. Sale un documento corto de decisiones, no código de producción.

DoD: 6 módulos apagados, retiro incluido; el spike dejó por escrito qué patrones cambian para las olas siguientes.

### F11 — Ola B: medianos

Esfuerzo L (6-9 semanas) · depende de F10 · 8.378 líneas.

- **`empresa`** (1.289 líneas, 14 rutas): CRUD con domicilios y logos; al editar la empresa activa se invalida `/auth/me`. Logo con el `AppUploader`.
- **`administracion` + `recibos`** (2.657 + 500 líneas; 16 + 18 rutas; tres prefijos): licencias, clientes con domicilios y categorías, export de recibos por cliente (la whitelist `RECIBOS_ADMIN_ALLOWED_EMAILS` la impone FastAPI), lotes de recibos (carga del masivo, detalle, reprocesar, eliminar con aviso de firmados), portal **Mis recibos** (`/recibos`) y recibos del empleado dentro de nómina (`/nomina/recibos`). Controles: descargas por URL firmada corta o fetch con Bearer, `Content-Disposition` correcto, sin recibos en estado persistente, auditoría de descarga, firma y reversión, **E2E con usuarios de dos empresas** para cruces de tenant. La unión de PDFs de `mis_recibos.html` deja de hacerse en el cliente con `pdf-lib`: la hace FastAPI con `pypdf` y esa librería se retira.
- **`nomina`** (3.932 líneas, 29 rutas, 60 llamadas): sub-fases → catálogos (departamentos, perfiles, categorías, carreras) → lista de empleados read-only → filtros y query params, **una sola colección para tabla y cards** → detalle → alta y edición en secciones (el formulario legacy tiene 821 líneas) → foto y archivos → baja, reactivación y restauración → recibos embebidos y logs. No duplicar paginación ni filtros entre tabla y cards.

DoD: §8 por módulo; los tres prefijos de recibos enrutados a Vue con regla de prefijo más largo; `pdf-lib` eliminado; Ola B apagada y retirada.

### F12 — Ola C: grandes

Esfuerzo XL (10-14 semanas; 8-12 con dos devs en paralelo) · depende de F11 · 18.558 líneas.

- **`starmiles`** (3.330 líneas, 40 rutas, 54 llamadas): sub-fases → home y consultas read-only → desafíos y filtros → inscripciones del empleado → catálogo y canjes → aprobador de inscripciones → aprobador de canjes → administración de desafíos e items → CMS y categorías → empleados 360 y contadores. Cambio conceptual: los `HX-Trigger` y `hx-swap-oob` que hoy sincronizan tablas y contadores pasan a respuestas `{items, resumen}` y a invalidación explícita; millas y contadores consistentes después de cada mutación. E2E separados para aprobador y empleado.
- **`soporte`** (8.792 líneas, 60 rutas, 95 llamadas, 38 formularios): sub-fases → dashboard y métricas → mis solicitudes read-only → tabla de tickets → drawer de detalle (1.203 líneas hoy) → creación y edición → kanban → categorías → pedidos y presupuestos → stock, activos e insumos → evidencias y acuerdos. Componentización: `SupportLayout` → `TicketFilters`, `TicketTable`, `TicketKanban` (`KanbanColumn`, `TicketCard`), `TicketDetailDrawer`, `TicketForm`, `CategoryManager`, `PurchaseOrderFlow`, `AssetSelector`, `EvidenceUploader`. Kanban y tabla comparten filtros y mutaciones; endpoints bootstrap según §4.5 donde una pantalla hoy compone 4 o más llamadas. Las decisiones del spike de F10 se aplican acá.
- **`innovacion`** (6.436 líneas, 31 rutas, 48 llamadas, 148 `hx-*`): sub-fases → listados administrativos → eventos y asistentes → certificaciones administrativas → licencias (1.025 líneas, recién refactorizadas en el legacy) → `mi_path` (2.509 líneas) **rediseñado por secciones funcionales**, no traducido → generación y descarga de certificado. Excepción: `/certificates/<id>` y `/certificates/<id>/<slug>.png` pasan a **FastAPI + Jinja** (público, Open Graph para WhatsApp y Twitter) con QR server-side (`qrcode`) y sin `html2canvas`, `jspdf` ni `qrcodejs`; conservan URLs y previews.

DoD: §8 por módulo; `mi_path` dividido en componentes mantenibles; certificados públicos con la misma URL y metadata; no quedan `HX-Trigger` ni `hx-swap-oob` en producción; Ola C apagada y retirada.

### F13 — Core, inversión del puente y apagado de Flask

Esfuerzo M (3-4 semanas) · depende de F12 · 2.507 líneas.

- [ ] Login, 2FA (challenge y setup), recuperación de password, magic link de bienvenida y "recordarme" en Vue, contra FastAPI directo, con el rate limiting de F07 activo. La SPA recibe la cookie de refresh en `login`; Flask ya no participa.
- [ ] Perfil, avatar, cambio de password, preferencias; selector de empresa nativo del shell.
- [ ] Notificaciones internas: bandeja e indicador; el polling HTMX (2 `hx-trigger every`) pasa a polling de TanStack Query; SSE solo si aporta.
- [ ] Dashboard; 403/404/500 definitivos; `/favicon.ico` y estáticos servidos por el proxy.
- [ ] Verificar que ningún email, card de Webex ni documento enlace rutas que solo existan en Flask.
- [ ] Apagado completo del contenedor viejo: eliminar el servicio `frontend` del compose, su Dockerfile, su lock y sus tests; proxy con `/*` → `spa` y sin lista de prefijos (quedan dos upstreams: `backend` y `spa`); borrar `frontend/` y renombrar `frontend-vue/` → `frontend/`; compose final: `proxy`, `spa`, `backend`, `scheduler`, `postgresql`; retirar de `.env.template` y de la VM las variables exclusivas del servicio Flask (`SECRET_KEY` del frontend, `API_URL`, `FLASK_PORT`, la copia de `RECIBOS_ADMIN_ALLOWED_EMAILS` del frontend; la del backend queda).
- [ ] Docs: `README`; `docs/Arquitectura-FrontEnd-Vue.md` pasa a ser `Arquitectura-FrontEnd.md`; `docs/Arquitectura-Deploy.md`; `docs/Stack-Trace-Flujos.md` revisado.
- [ ] **(persona)** Retirar de la VM volúmenes, imágenes y variables de Flask; conservar un tag o release anterior restaurable durante un mes.

DoD: todo el menú navega dentro de Vue o hacia páginas públicas explícitas; la sesión la administra solo FastAPI; cero consumidores de Flask; el contenedor `frontend` ya no existe en la VM ni en el compose; `frontend/` en el repo es la SPA; métrica del tablero en 0 líneas Jinja (las plantillas públicas de FastAPI se cuentan aparte).

---

## 8. Definition of Done por módulo

Un módulo no está migrado porque "se ve igual". Vale para pilotos y olas:

**Funcionalidad**
- [ ] Checklist de paridad armada **antes** de migrar, mirando el template legacy (flujos, filtros, estados, mensajes).
- [ ] Paridad aprobada por un usuario referente del módulo.
- [ ] URLs, filtros y paginación en query params; back/forward del navegador recupera la vista.
- [ ] Loading, vacío y error definidos en cada pantalla; formularios y uploads completos.

**Seguridad**
- [ ] Permisos idénticos, probados con un usuario restringido: FastAPI impone permisos y tenant; la SPA solo oculta.
- [ ] Sin tokens ni datos sensibles en almacenamiento persistente del navegador.
- [ ] Operaciones destructivas con confirmación; acciones sensibles con idempotencia donde aplique.

**Calidad**
- [ ] Cliente generado desde OpenAPI, sin fetchers a mano; `vue-tsc` sin errores.
- [ ] Tests de componentes críticos; E2E de happy path y de un error relevante.
- [ ] Accesibilidad básica: labels, foco, teclado, ARIA en diálogos y tablas.

**Operación**
- [ ] Logs correlacionables con FastAPI por `X-Request-ID`.
- [ ] Canario ejecutado con usuarios internos; rollback de ruta probado.
- [ ] Vue declarado principal; Flask conservado según §4.3 y **retiro** ejecutado en su pendiente (blueprint, templates y parciales eliminados).
- [ ] Docs actualizadas; pendiente en `director` cerrado con as-built, evidencia y la métrica de líneas Jinja restantes.

---

## 9. Estimación y calendario (Paso 1 + Paso 2)

| Orden | Fase | Esfuerzo | Calendario (1-2 devs con IA) |
|---|---|---|---|
| 1 | Paso 1: F01-F07 (`update-techs-v1-final.md`) | — | semanas 1-9 |
| 2 | F08 Fundación | L | semanas 8-12 (esqueleto y bake-off solapan con F07; proxy y puente no) |
| 3 | F09 Pilotos | M | semanas 12-15 |
| 4 | F10 Ola A + spike | L | semanas 15-21 |
| 5 | F11 Ola B | L | semanas 21-30 |
| 6 | F12 Ola C | XL | semanas 30-44 (8-12 semanas con dos devs) |
| 7 | F13 Core y apagado | M | semanas 44-48 |

Total: **8-11 meses calendario**, de los cuales 1,5-2 son Paso 1. El cuello de botella es el **QA funcional por módulo** y las decisiones de la persona, no escribir componentes. Con dos devs, F11 y F12 se paralelizan por módulo; nunca dos devs en el mismo módulo con el mismo cutover.

---

## 10. Testing de convivencia y estrategia de estado

**Contrato**: OpenAPI validado en CI (F07); cliente TS regenerado en CI con fallo por drift; esquemas de error y paginación uniformes (`response_model` obligatorio en lo que consume la SPA).

**Backend**: tests de autorización y aislamiento multiempresa por módulo antes de su ola; tests de migraciones Alembic; contract tests de integraciones con fakes.

**SPA**: Vitest + Testing Library para composables, formularios, tablas y diálogos; Playwright para login/2FA, selección de empresa y el happy path de cada módulo migrado.

**Comparación legacy/Vue durante cada ola**: mismo escenario contra ambos mundos; comparar efectos en DB, permisos visibles y efectivos, requests por pantalla y tiempos; screenshots donde ayude.

**Estado**: Pinia solo para auth, empresa, menú, preferencias y contadores globales imprescindibles. Todo lo demás (listados, filtros, paginación, detalle, catálogos locales) vive en TanStack Query por vista o composable de módulo. La URL representa filtros navegables; las mutaciones invalidan explícitamente; no se persisten responses ni datos sensibles.

---

## 11. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Doble mantenimiento eterno: la migración se estanca | Alta | Alta | Olas cortas con fecha; principio 3 (nuevo = Vue); retiro con plazo (§4.3); tablero visible; si en 2 quarters no cerró la Ola A, replantear |
| Regresiones en módulos en producción | Media | Alta | Checklist de paridad antes; canario por cookie; rollback de ruta en segundos; Flask conservado 1 release |
| Auth mal diseñada o puente frágil | Media | Crítica | F07 con DoD; tests de rotación y replay; F08 lo prueba de punta a punta antes de cualquier módulo |
| `soporte` e `innovacion` (46 % del frontend) revientan la estimación | Alta | Alta | Spike en F10; rediseño por secciones, no traducción; dos devs en paralelo en F12; sub-fases desplegables |
| Vue duplica reglas de negocio o permisos | Media | Alta | Principio 4; `/auth/me` como única fuente de permisos; E2E con usuario restringido |
| Muchos requests reemplazan la composición del BFF | Alta | Media | §4.5: paralelismo, cache, bootstrap selectivo; medir requests por pantalla en la comparación legacy/Vue |
| Dos mundos divergen visualmente | Media | Media | Tokens compartidos; PrimeVue temado con esos tokens; shell que replica `base.html` |
| Recibos: cruce de tenant o descarga sin auditoría | Baja | Crítica | E2E con dos empresas; URLs firmadas cortas; auditoría de descarga y firma; sin cache persistente |
| Páginas públicas pierden previews sociales | Media | Alta | `/certificates/*` en FastAPI + Jinja con OG; test que valida las metatags |
| El equipo aprende Vue sobre la marcha | Alta | Media | Piloto 1 chico y descartable; convenciones escritas en F08; patrón CRUD en F09; revisión cruzada |
| Bundle grande | Media | Baja | Lazy loading por módulo; análisis de bundle en CI |

---

## 12. Qué NO hacer

- No big-bang ni rama `feature/vue-migration` de meses.
- No islas Vue dentro de Jinja "mientras tanto"; no HTMX y Vue sobre el mismo DOM.
- No empezar la SPA sin F07 cerrada y probada.
- No tokens en `localStorage` ni `sessionStorage`.
- No HTMX 2/4, no build de Tailwind ni CSP en el legacy (v1-final Decisión 1).
- No traducir 1:1 `mi_path`, `tickets` ni `ticket_detalle`: rediseñar en componentes.
- No dejar rutas Flask "por las dudas" después del plazo de retiro.
- No duplicar reglas de negocio ni permisos en Vue.
- No crear un endpoint por pantalla por reflejo; bootstrap solo con la regla de §4.5.
- No Nuxt ni SSR fuera de las páginas públicas; no SQLAlchemy async; no microservicios; no MariaDB.
- No mezclar el cutover de un módulo con Postgres 18, psycopg 3 o cambios de runtime en el mismo release.

---

## 13. Tablero de avance

Sale de `director resumen`; este bloque es el espejo para lectura:

- [ ] F08 — Fundación (proxy, contenedor `spa`, esqueleto, shell, cliente TS, CI)
- [ ] F09 — Pilotos: sincronizacion · parametros
- [ ] F10 — Ola A: notificaciones · operaciones · llm · hrbp · usuarios · permisos · spike soporte
- [ ] F11 — Ola B: empresa · administracion + recibos · nomina
- [ ] F12 — Ola C: starmiles · soporte · innovacion (+ certificados públicos en FastAPI)
- [ ] F13 — Core migrado, puente invertido, Flask eliminado

Métricas: líneas de template Jinja restantes en `frontend/modulos/` (hoy **33.065**); módulos apagados **/ 16**; requests por pantalla y tasa de errores por módulo comparadas con el legacy; incidentes de permisos o tenant (objetivo: cero); tiempo de rollback de ruta.

---

## 14. Cómo cargarlo en `director`

- Mismo proyecto y misma versión `v1` que el Paso 1; las fases son `F08..F13` con los títulos de §7.
- `F08 depende_de F07`, `F09 depende_de F08`, `F09 depende_de F06` (por 6b), `F10 depende_de F09`, `F11 depende_de F10`, `F12 depende_de F11`, `F13 depende_de F12`.
- Cada módulo es un pendiente de su fase con sub-letras por sub-fase (`F11-P03.a` catálogos, `.b` lista read-only, …) y un pendiente hermano "retiro Flask de <módulo>" con fecha límite (§4.3). El spike de `soporte` es un pendiente de F10 con salida documental.
- Decisiones de §0 (filas 2 a 10 y 16) como `D-##` con `link D-## ejecuta F08` (stack, proxy, canario, retiro) o `F09` (pilotos); el bake-off de componentes nace `abierto` y se cierra en F08 con la evidencia.
- El gate de v1-final §6 se registra como decisión que se cierra cuando F01-F07 están cerradas; `F08` no arranca antes.
- La métrica de líneas Jinja se anota como nota en el pendiente de cada módulo al cerrarlo.
- Documentos: este archivo, `update-techs-v1-final.md` y los cuatro `update-techs*.md` origen, como `documento` para trazabilidad.

---

## 15. Fuentes

Métricas verificadas el 2026-09-07: conteos con `find` y `grep` sobre `frontend/modulos/` en `2d67931`; prefijos tomados de los `Blueprint(...)` de cada `app_module.py`.

Referencias de diseño (heredadas de los documentos origen):

- Vue SFC y escalado: https://vuejs.org/guide/scaling-up/sfc.html
- Vue Router, history mode y lazy loading: https://router.vuejs.org/guide/essentials/history-mode · https://router.vuejs.org/guide/advanced/lazy-loading
- Pinia: https://pinia.vuejs.org/introduction.html
- TanStack Query para Vue: https://tanstack.com/query/latest/docs/framework/vue/overview
- Cliente TS desde OpenAPI: https://heyapi.dev/
- Tailwind 4 con Vite: https://tailwindcss.com/docs/installation/using-vite
- PrimeVue, modo unstyled y Tailwind: https://primevue.org/
- Playwright: https://playwright.dev/
- OWASP, tokens en SPA y almacenamiento: https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html#local-storage
- OWASP, CSRF con cookies y cabeceras custom: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- FastAPI, seguridad JWT: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- Caddy, `reverse_proxy` y `handle_path`: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy · https://caddyserver.com/docs/caddyfile/directives/handle_path
