# Dicsys-Core Stack tech v2

Stack tecnológico v2 de Dicsys Core: una SPA en Vue 3 y una API en FastAPI sobre PostgreSQL,
desplegadas con Docker Compose en una VM de un proyecto de GCP propio, detrás del Traefik de la
plataforma de servicios de Dicsys.

La plataforma (Traefik, Shared VPC, Cloud NAT, IAP y el deploy por WIF) está documentada en el
repo `dicsys-services-public`: `docs/00.arquitectura.md`, `docs/01.setup_gcp.md`,
`docs/02.setup_github.md` y `docs/presentacion-arquitectura.html`.

Las versiones son de referencia a 2026-09; las exactas las fijan los lockfiles.

## Arquitectura

```
Internet
   │  app.dicsys.ai → 34.134.238.74 (DNS externo)
   ▼
Traefik v3 · dicsys-www-public-vm (proyecto host de la plataforma)
   TLS Let's Encrypt · HTTP → HTTPS · HSTS · rate limit · health checks
   │  Shared VPC vpc-shared-dicsys, por IP interna
   ├─ Host(app.dicsys.ai) && PathPrefix(/api) ──► 10.50.0.2:8000
   └─ Host(app.dicsys.ai)                      ──► 10.50.0.2:8080
                                                      │
   VM app-vm · proyecto GCP propio · sin IP externa · salida por Cloud NAT
     ├─ web        nginx sin privilegios que sirve el build de la SPA   :8080
     ├─ backend    FastAPI + uvicorn                                    :8000
     ├─ scheduler  misma imagen del backend, sin puerto
     ├─ migrate    Alembic, corre una vez en cada deploy
     └─ postgres   PostgreSQL 18, sin puerto publicado
```

El nombre `app`, el rango `10.50.0.0/24` y los puertos son valores de ejemplo. El rango es un
/24 libre de la Shared VPC: del `10.10` al `10.40` ya están en uso.

## Principios

- **Un solo origen:** la SPA y la API viven bajo el mismo host, así la cookie de sesión
  funciona sin CORS.
- **Sin proxy propio:** Traefik ya termina TLS, pone las cabeceras de seguridad, limita el
  tráfico, controla la salud de cada servicio y rutea por host y por path. Dentro de la VM no
  hace falta Caddy ni un nginx que rutee: nginx solo sirve archivos estáticos.
- **El backend impone:** negocio, permisos y datos se resuelven en FastAPI; la SPA presenta.
- **Contrato primero:** el cliente TypeScript se genera del OpenAPI del backend.
- **La imagen es el código:** en producción corre exactamente la imagen que probó CI.
- **Reproducible:** todo con lockfile, nada flotante.

## Frontend

| Pieza | Elección |
|---|---|
| Framework | Vue 3, Composition API con `<script setup>` |
| Build | Vite |
| Lenguaje | TypeScript estricto, verificado con `vue-tsc` |
| Routing | Vue Router con `createWebHistory`, guards por permiso y carga diferida por módulo |
| Estado propio | Pinia, solo para sesión, permisos, menú y preferencias; nunca respuestas completas |
| Estado del servidor | TanStack Query (`@tanstack/vue-query`): cache, reintentos e invalidación por mutación |
| Cliente de API | Generado con `@hey-api/openapi-ts` desde el OpenAPI; no se escriben fetchers a mano |
| Estilos | Tailwind 4 con su plugin de Vite y los tokens de diseño en `@theme` |
| Componentes | PrimeVue 4 sin estilos, con tema Tailwind y envoltorios propios (`AppTable`, `AppDialog`, `AppForm`) |
| Iconos | Lucide (`lucide-vue-next`) |
| Fuentes | Empaquetadas en el build (por ejemplo con Fontsource), sin CDN |
| Formularios | VeeValidate con Zod; los errores 422 de FastAPI se muestran en cada campo |
| Tests | Vitest con Testing Library; Playwright para los flujos de punta a punta |
| Lint | ESLint con `eslint-plugin-vue` y typescript-eslint; Prettier |
| Node | 24 LTS en local, en CI y en el stage de build (`node:24-alpine`) |
| Servido por | Contenedor `web`: `nginxinc/nginx-unprivileged:alpine` con `dist/` y fallback a `index.html` |

- nginx cachea un año los assets con hash, sirve `index.html` sin cache, comprime con gzip y
  agrega las cabeceras de seguridad propias de la SPA (ver Seguridad).
- Los tokens de diseño salen de [Design-Tokens.md](Design-Tokens.md).
- No se usan Nuxt ni SSR (es una app interna autenticada), micro-frontends ni otro framework
  por módulo.

## Backend

| Pieza | Elección |
|---|---|
| Lenguaje | Python 3.14 |
| Dependencias | uv con `pyproject.toml` y `uv.lock`; `uv sync --frozen` en la imagen y en CI |
| Framework | FastAPI |
| Validación y configuración | Pydantic 2 y pydantic-settings |
| ORM | SQLAlchemy 2.0, sincrónico |
| Driver | psycopg 3 (`postgresql+psycopg://`) |
| Migraciones | Alembic desde la primera tabla |
| Tokens | PyJWT |
| Contraseñas | Argon2id con `pwdlib` |
| 2FA | TOTP con pyotp |
| Rate limiting | slowapi en login, 2FA, reset de contraseña y magic link |
| Cliente HTTP | httpx2 |
| Servidor | uvicorn con varios workers, `--proxy-headers` y `--forwarded-allow-ips` con la IP de Traefik (`10.10.0.2`) |
| Tareas programadas | Proceso `scheduler` aparte (misma imagen, otro comando) con advisory locks de Postgres; nunca dentro de los workers web |
| Referencia de API | Scalar sobre el OpenAPI |
| Imagen | `python:3.14-slim` multistage: el builder corre `uv sync --frozen --no-dev` y el runtime copia el venv; usuario no root y healthcheck |
| Logs | stdout, con `X-Request-ID` en cada request y en su respuesta |
| Integraciones disponibles | SendGrid (email), google-genai (Gemini) y google-cloud-storage (archivos, por ADC) |

Convenciones:
- Todo el backend cuelga de `/api`, incluidos el OpenAPI y Scalar. Los endpoints van
  versionados (`/api/v1/...`).
- `/health` queda fuera de `/api`: lo consultan Traefik y el healthcheck de Docker.
- `response_model` en cada endpoint, errores con forma estable y `operationId` legibles, que el
  cliente TypeScript usa como nombres de función.

## Datos

- **Motor:** PostgreSQL 18, imagen `postgres:18-alpine` con la versión menor fijada. Corre en la
  VM con un volumen persistente en el disco SSD y sin puerto publicado: solo lo alcanzan
  `backend`, `scheduler` y `migrate` por la red del compose.
- **Claves:** UUID v7 generados con `uuidv7()`, que trae PostgreSQL 18 y quedan ordenados por
  tiempo.
- **Esquema:** Alembic. El deploy corre `alembic upgrade head` antes de levantar la versión
  nueva. Los cambios sin downtime se hacen en dos pasos: primero se agrega lo nuevo y después
  se quita lo viejo.
- **Diagnóstico:** `pg_stat_statements` habilitado.
- **Backups:** `pg_dump` diario a un bucket de GCS del proyecto con retención por lifecycle, más
  snapshots programados del disco de la VM. El restore se ensaya y queda documentado.
- **Archivos:** bucket de GCS del proyecto, accedido por ADC con la service account de la VM,
  sin claves JSON. Las descargas van con URLs firmadas de corta duración.
- **Multiempresa:** cada tabla de negocio lleva la empresa y el backend filtra por ella en cada
  consulta.

## Autenticación y sesión

- **Login:** la SPA llama a `POST /api/v1/auth/login`, con un segundo paso de 2FA si el usuario
  lo tiene activo.
- **Access token:** JWT corto, de 15 a 30 minutos, que vive solo en memoria. Nunca en
  `localStorage` ni en `sessionStorage`.
- **Refresh token:** rotativo, en cookie `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`, y
  registrado en la tabla `auth_refresh_tokens` (jti, usuario, vencimiento y si está revocado).
  Cada `refresh` lo rota y `logout` lo revoca.
- **CSRF:** los endpoints que usan la cookie (`refresh` y `logout`) exigen la cabecera
  `X-Requested-With`. El resto va con Bearer.
- **Permisos:** `GET /api/v1/auth/me` devuelve usuario, permisos efectivos y menú en una sola
  llamada. La SPA muestra u oculta; el backend valida cada request. La empresa activa viaja en
  el token y cambiarla emite uno nuevo.
- **Credenciales guardadas:** contraseñas con Argon2id. Códigos de respaldo del 2FA, magic links
  y tokens de reset se guardan como hash y vencen.
- **Primer admin:** se crea con una contraseña aleatoria o tomada del entorno, y nunca se
  imprime en los logs.

## Seguridad

**Borde (Traefik, lo provee la plataforma)**
- TLS con Let's Encrypt y redirección de HTTP a HTTPS.
- HSTS de un año con subdominios y preload, `X-Content-Type-Options: nosniff` y
  `X-Frame-Options: SAMEORIGIN`.
- Rate limiting por IP: 100 solicitudes por segundo de promedio, con ráfagas de 50.

**Red y VM**
- La VM no tiene IP externa y sale a Internet por Cloud NAT.
- SSH solo por túnel IAP con OS Login, sin claves SSH en la metadata.
- Solo se publican los puertos de `web` y `backend`; Postgres nunca. La regla
  `shared-allow-internal` de la plataforma abre todo el tráfico entre subredes: para que esos
  puertos solo los alcance Traefik hace falta una regla de firewall propia.
- La VM corre con una service account propia con roles mínimos (lectura de Artifact Registry,
  objetos del bucket y escritura de logs), no con la default de Compute Engine.

**Contenedores**
- Usuario no root, healthcheck, límites de memoria y CPU, y `restart: unless-stopped`.
- Imágenes base con tag fijo y logs con rotación (`json-file`, 10 MB × 3).

**Aplicación**
- Validación de entrada con Pydantic y autorización en el backend en cada endpoint, con el
  filtro por empresa.
- En producción el backend no arranca con `DEBUG` activo ni con los secretos del template.
- El contenedor `web` agrega CSP estricta (`default-src 'self'` más lo mínimo para las URLs
  firmadas de GCS), `Referrer-Policy` y `Permissions-Policy`. La CSP puede ser estricta porque
  la SPA no carga nada de CDNs.

**Secretos**
- Nunca en el repo ni en la imagen. Viven en el Environment `prod` de GitHub (o en Secret
  Manager del proyecto), y el deploy los escribe en el `.env` de la VM con permisos 600.
- `SECRET_KEY`, `JWT_SECRET_KEY` y el pepper de los códigos de respaldo se generan al azar para
  cada entorno.

**CI/CD y dependencias**
- Deploy por Workload Identity Federation, sin claves de service account en GitHub.
- Service account de deploy propia, que solo se puede impersonar desde su repositorio
  (`attribute.repository`), y no desde todo el owner `Dicsys-SA` como el binding compartido de
  la plataforma.
- Lockfiles en backend y frontend, Dependabot semanal (github-actions, docker, uv y npm), y
  `pip-audit` y `npm audit` en CI.

## Infraestructura en GCP

El servicio corre en su propio proyecto de GCP, como uno más de la plataforma. El paso a paso de
la red, la VM y la IAM está en `dicsys-services-public/docs/01.setup_gcp.md`.

| Recurso | Configuración |
|---|---|
| Proyecto | Service project propio, asociado a la Shared VPC del host `dicsys-www-public-489718` |
| Subred | `/24` propia en `vpc-shared-dicsys`, región `us-central1`, con `networkUser` para la service account de la VM |
| VM | e2-medium con disco SSD de 30 GB, IP interna estática `.2`, sin IP externa, OS Login, Docker Engine con Compose |
| Salida a Internet | Cloud NAT `nat-shared-dicsys`, que cubre todas las subredes |
| Imágenes | Artifact Registry (Docker) en el proyecto |
| Archivos y backups | Bucket de GCS en el proyecto |
| Ingreso | Routers y services en `dicsys-services-public/dynamic/services.yml.template` |
| DNS | Registro A `app.dicsys.ai → 34.134.238.74` en el registrador externo |
| Certificado | Automático: Traefik lo pide a Let's Encrypt en el primer acceso |

Su entrada en el template de Traefik, en las secciones `routers` y `services`:

```yaml
http:
  routers:
    app-api:
      rule: "Host(`app.dicsys.ai`) && PathPrefix(`/api`)"
      entryPoints:
        - websecure
      service: app-api
      middlewares:
        - rate-limit
        - security-headers
      tls:
        certResolver: letsencrypt

    app-web:
      rule: "Host(`app.dicsys.ai`)"
      entryPoints:
        - websecure
      service: app-web
      middlewares:
        - rate-limit
        - security-headers
      tls:
        certResolver: letsencrypt

  services:
    app-api:
      loadBalancer:
        healthCheck:
          path: "/health"
          interval: "10s"
          timeout: "3s"
        servers:
          - url: "http://10.50.0.2:8000"

    app-web:
      loadBalancer:
        healthCheck:
          path: "/"
          interval: "10s"
          timeout: "3s"
        servers:
          - url: "http://10.50.0.2:8080"
```

La regla con `PathPrefix` es más larga y Traefik le da prioridad: `/api/...` va al backend y
todo lo demás a la SPA.

## Contenedores

| Servicio | Imagen | Puerto | Rol |
|---|---|---|---|
| `web` | Build del frontend sobre `nginxinc/nginx-unprivileged:alpine` | 8080 | Sirve la SPA |
| `backend` | Build del backend sobre `python:3.14-slim` | 8000 | API |
| `scheduler` | La del backend, con otro comando | — | Tareas programadas |
| `migrate` | La del backend, con `alembic upgrade head` | — | Corre una vez en cada deploy |
| `postgres` | `postgres:18-alpine` | — | Base de datos, con volumen persistente |

- **Producción:** `docker-compose.yml` usa las imágenes de Artifact Registry por tag inmutable,
  sin `build` y sin código montado.
- **Desarrollo:** `docker-compose.override.yml`, que Compose carga solo en local, levanta Vite
  con recarga en caliente en el 5173 y reenvía `/api` al backend con `server.proxy`. El backend
  corre con `--reload` y el código montado, y Postgres se publica solo en `127.0.0.1`.
- **Herramientas locales:** Docker con Compose, uv y Node 24 LTS.

## CI/CD con GitHub Actions

**CI, en cada PR y en `main`**

| Job | Qué hace |
|---|---|
| backend | `uv lock --check`, `ruff check` y `ruff format --check`, pytest contra un Postgres real, `alembic upgrade head` sobre una base vacía más `alembic check`, y `pip-audit` |
| frontend | `npm ci`, ESLint, `vue-tsc`, Vitest, el build, y regenera el cliente de API para verificar que coincida con el OpenAPI; `npm audit` |

La QA en caja negra tiene su propio CI en el repo `innovacion-qa-engine`: clona la app, levanta el stack con las
imágenes de producción y corre el seed, la API en caja negra, Playwright y la matriz de cobertura con gate.

**CD, al publicar un release (o a mano), en el Environment `prod`**
1. Construye las imágenes `web` y `backend` y las publica en Artifact Registry con el tag del
   release.
2. Se autentica por WIF con la service account de deploy.
3. Por túnel IAP copia `docker-compose.yml` y el `.env` a la VM.
4. En la VM: `docker compose pull`, `docker compose run --rm migrate` y `docker compose up -d`.
   Espera a que todo esté `healthy` y recién ahí corre `docker image prune`.
5. Rollback: volver al tag anterior y repetir `up -d`.

La VM no clona el repo, no construye imágenes y no guarda tokens de GitHub.

## Observabilidad y operación

- Logs a stdout con rotación, el access log de Traefik en el borde y `X-Request-ID` para seguir
  un request de punta a punta.
- `/health` del backend, que consultan el healthcheck de Docker y Traefik cada 10 segundos.
- Backups diarios con restore ensayado (ver Datos).
- Deploy y rollback siempre por release, con un comando.

## Calidad y QA

- **Backend:** pytest con pytest-cov contra un Postgres real. Los tests crean el esquema con
  `create_all` por velocidad y CI prueba aparte la cadena de migraciones.
- **Frontend:** Vitest con Testing Library y Playwright para los flujos críticos.
- **QA en caja negra:** vive en su propio repo, `innovacion-qa-engine`, clonado al lado de este. Tiene un
  entorno con las imágenes de producción de la app, seed determinista, casos escritos en markdown y
  automatizados con pytest y Playwright, evidencia por paso, matriz de cobertura con gate, la CLI `qa`, la
  consola y el MCP. Ningún trabajo se cierra sin sus casos de prueba. Ver el README de ese repo.
- **Estilo:** Ruff en Python; ESLint y Prettier en TypeScript.

## Estructura del repositorio

```
backend/                     FastAPI: app/, alembic/, tests/, pyproject.toml, uv.lock, Dockerfile
frontend/                    Vue: src/, tests/, package.json, package-lock.json, nginx.conf, Dockerfile
docker-compose.yml           producción
docker-compose.override.yml  desarrollo
.github/workflows/           ci.yml y deploy.yml
.github/dependabot.yml
docs/
```

## Versiones de referencia (2026-09)

| Pieza | Versión |
|---|---|
| Python | 3.14 |
| FastAPI | 0.141 |
| SQLAlchemy | 2.0.52 |
| psycopg | 3.3 |
| Alembic | 1.19 |
| PyJWT | 2.13 |
| httpx2 | 2.12 |
| scalar-fastapi | 1.9 |
| uv / Ruff | 0.12 / 0.16 |
| PostgreSQL | 18.6 |
| Node | 24 LTS |
| Tailwind | 4.3 |
| Traefik de la plataforma | 3.6.10 |

Vue, Vite, PrimeVue 4, TanStack Query y el resto del frontend: la última estable, fijada por
`package-lock.json`.

## Fuera del stack, a propósito

- Kubernetes, Cloud Run, Cloud SQL y Terraform: la plataforma es una VM con Compose por
  servicio, armada con gcloud.
- Nuxt, SSR y micro-frontends.
- Logs en JSON con OpenTelemetry y SLOs, hasta que haya una necesidad operativa concreta.
- SBOM, CodeQL, escaneo de imágenes y actions pineadas por SHA, salvo que lo pida un cliente o
  compliance.
- Cifrado del secreto TOTP con KMS: se evalúa junto con Secret Manager.
