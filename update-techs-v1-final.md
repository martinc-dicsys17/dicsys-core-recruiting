# Actualización tecnológica — Paso 1 (v1 final)

> **Estado:** propuesta consolidada, sin implementar.
> **Fecha:** 2026-09-07 · rama `feature/upgrade-tech-stack` @ `2d67931` (main mergeado; la rama solo agrega los `.md` de este plan).
> **Consolida:** `update-techs.md` (auditoría corta del 2026-08-06, con orden de PRs) y `update-techs-sol.md` (auditoría ampliada: seguridad de aplicación, supply chain, deploy, operación). Cada hallazgo fue re-verificado contra el código y las versiones "última" se refrescaron al 2026-09-07; lo que cambió está en §0.
> **Relación con v2:** este Paso 1 deja el sistema en condiciones para el Paso 2 — migración incremental del frontend a Vue 3, consolidada en `update-techs-v2-final.md` (que reemplaza a `update-techs-v2.md` y `update-techs-sol-v2.md`). La regla que ordena todo el documento: **inversión mínima en el frontend Flask/HTMX (seguridad y pines), inversión completa en el backend FastAPI (queda) y en el puente hacia la SPA.**
> **Destino:** base para cargar el plan en `director` (fases §5 → `F01..F07`, decisiones §4 → `D-##`, checkboxes → pendientes; ver §10). El Paso 2 continúa la numeración en `update-techs-v2-final.md` (`F08..F13`); los dos documentos se ejecutan en ese orden y comparten el gate de §6. Una vez importado, el estado vive en `director`; este archivo queda como auditoría y fundamento.

---

## 0. Qué cambia respecto a los documentos origen

| # | Tema | Decían los docs | Verificado en el repo (2026-09-07) | Decisión en v1-final |
|---|---|---|---|---|
| 1 | Flask dev server + `debug=True` | P0, `app.py:359` | Confirmado, hoy en `frontend/app.py:361`. Además: `SECRET_KEY` con fallback hardcodeado (`app.py:15`); `frontend/Dockerfile` sin `USER` no-root ni `HEALTHCHECK` (el healthcheck vive en el compose) | **P0**, F01 |
| 2 | python-jose "abandonada, 4 CVEs" | P0 (v1) / P2 "PyJWT si solo se usa JWT" (sol) | Inexacto: última 3.5.0 (2025-05-28), clasificada Production/Stable; los CVE de 2024 se corrigieron en 3.4/3.5. Cierto: 15 meses sin release y FastAPI documenta PyJWT. Uso mínimo: 2 archivos, `encode/decode`, y el claim `sub` ya es string | **P1**, F02: migrar a PyJWT 2.13. Cambio trivial, no es urgencia de seguridad |
| 3 | `admin@admin.com / admin` en instalación vacía | P0 (sol) | Solo corre con `ENVIRONMENT=development` (`backend/main.py:170-188`); en producción el seed no se ejecuta. El `.env` local está en `development`; el de la VM no se pudo verificar | **P2**, F02: sacar el password del código y verificar el `.env` de la VM. Baja de P0 |
| 4 | CSRF, cookies y CORS en Flask | P0 CSRF global (sol); flask-cors 4 → 6 (ambos) | Confirmado: sin CSRF, sin `SESSION_COOKIE_SECURE/SAMESITE` explícitos, `CORS(app)` abierto (`app.py:26`). No hay consumidor cross-origin (los 77 `fetch()` de los templates van a rutas Flask propias). No se encontraron GET mutantes (búsqueda heurística). Tamaño: 281 rutas (170 mutantes), 100 `<form>`, 101 `hx-post/put/delete` | F01: cookies `Secure/HttpOnly/SameSite=Lax` + chequeo de `Origin` en métodos mutantes + **eliminar** flask-cors. Tokens CSRF completos: decisión abierta (§4, Decisión 3) por costo y regresión en código a extinguir |
| 5 | Builds no reproducibles | Sin lock, CDN flotantes, Python 3.12 vs 3.14 | Confirmado. Agregado: en producción **el código no viene de la imagen** — el compose monta `./backend` y `./frontend` desde el checkout, y el deploy usa ese mismo compose | F03: uv + `uv.lock` por servicio, Python 3.14 unificado, compose base apto para producción + override de desarrollo |
| 6 | Migraciones ad hoc | 3 scripts (v1) | Son **5**, todos ejecutados en cada arranque bajo advisory lock (`main.py:107-132`): `innovacion/migrations/licencias.py`, `notificaciones_internas/migration.py`, `starmiles/migrations/dic_144.py`, `recibos/migration.py`, `soporte/temp_migration_matriz_estado.py` | F04: Alembic con baseline que los absorbe |
| 7 | Credencial JSON de GCS montada | P1, "sustituir por ADC" (sol) | Confirmado el mount (`docker-compose.yml`, `secrets/`). Pero `backend/core/storage.py:123-127` **ya cae en ADC** si `GCS_CREDENTIALS_PATH` está vacío: el cambio es IAM + configuración, no código | F06, esfuerzo S |
| 8 | Deploy mutable en la VM | `git reset --hard` + build en la VM (sol) | Confirmado (`deploy.yml`). Agregado: el token `CODE_TOKEN` queda **persistido en `.git/config` de la VM** (`git remote set-url origin https://x-access-token:…`). El puerto de Postgres se publica en el host (`6000`) | F06: primero lo barato (token, `-f` explícito, paso de migración); después imágenes por digest |
| 9 | Crons en threads por worker | P1 → Cloud Scheduler / Cloud Run Jobs (sol) | Confirmado: 2 crons (`notificaciones` cumpleaños, `sincronizacion` Webex) como threads en cada uno de los 5 workers con `pg_try_advisory_lock` (`main.py:154-164`), más un thread fire-and-forget para certificados (`innovacion/services.py:236`) | F06: servicio `scheduler` separado en el mismo compose con flag `CRON_ENABLED`. Cloud Scheduler: diferido (§7) |
| 10 | Tailwind Play CDN | v1: build con Tailwind 4; v2: descartado en legacy; sol-v2: compilar + tokens | 3 templates lo usan (`base.html:16`, `certificate_public.html`, `certificate_not_found.html`). `https://cdn.tailwindcss.com/3.4.17` responde con el build de esa versión (verificado). Los tokens son ~40 líneas inline (`base.html:18-60`) | Decisión 2: **no compilar en legacy**; pinear la versión del Play CDN y documentar los tokens para Vue |
| 11 | HTMX 1.9 → 2.x | v1: migrar; v2: diferir | htmx 4.0.0 salió el 2026-08-28 (tag `next`; 2.x sigue como `latest` hasta inicios de 2027 y con soporte indefinido) | No se toca en legacy (Decisión 1). 1.9.10 ya está pineado |
| 12 | Argon2id, KMS para TOTP, Secret Manager, OpenTelemetry, SBOM, CodeQL, Trivy, Cloud Run, Terraform | Fases 4-6 (sol) | Sin driver de compliance; equipo de 1-2 devs; buena parte toca el frontend que se apaga | Diferidos con motivo (§7). Se conservan los baratos: hash de backup codes y magic links, Dependabot, auditoría de dependencias |
| 13 | "Dockerfiles multistage con usuario no-root, healthchecks" (v1 §5) | — | Solo el backend. El frontend no tiene `USER` ni `HEALTHCHECK` | Corregido; F01 |
| 14 | "El JWT nunca llega al navegador" (v2 §3.3) | — | Incorrecto: Flask usa la sesión por defecto (cookie firmada, client-side; no hay flask-session). El access token viaja **dentro** de la cookie de sesión (HttpOnly, firmada con `SECRET_KEY`, legible por el cliente). Con "recordarme" la cookie dura 30 días (`app.py:24`) pero el JWT expira a los 30 min | Corrección para el diseño de auth del Paso 2 (F07 y v2-final §3) |
| 15 | httpx | 0.26 → 0.28 (ambos); "HTTPX2 piloto" (sol) | 0.28.1 (2024-12-06) es la última 0.x, sin releases hace 21 meses. httpx2 2.12.0 (2026-08-18) es la continuación mantenida; el backend ya la usa en tests (`requirements-test.txt`) | Frontend: 0.28.1 y listo. Backend: httpx2 en código propio (Decisión 8), después del lock |
| 16 | Versiones "última" | corte 2026-08-06 | Refrescadas al 2026-09-07 (§2). Cambios relevantes: gunicorn 26.2, PyJWT 2.13, Alembic 1.19, uv 0.12, ruff 0.16, scalar-fastapi 1.9, PostgreSQL 18.6/16.15, Python 3.14.7; SQLAlchemy sigue en 2.0.52 (2.1 no salió) | — |
| 17 | Métricas del frontend (v2) | ~30.700 líneas | Creció: 33.065 líneas de template en `frontend/modulos/`, 164 templates, 692 atributos `hx-*`, 151 `x-data`; soporte 8.792, innovación 6.436 (licencias) | Actualizadas en §2.2 y en v2-final §2; el orden de olas quedó fijado en v2-final §0, filas 2, 3 y 12 |
| 18 | Documentación | — | `README` dice "JWT con python-jose" y enlaza `docs/Plan-Implementacion-TDD-Core.md` (no existe); `docs/Arquitectura-Deploy.md` y `Arquitectura-FrontEnd.md` desactualizados (puertos 5000, 3 módulos) | F05 |

---

## 1. Resumen ejecutivo

El stack (FastAPI + SQLAlchemy 2 + Pydantic 2 + PostgreSQL 16; Flask + HTMX + Alpine) está vigente y funciona. La deuda no está en los frameworks sino en **cómo corre en producción**: servidor de desarrollo de Flask con debugger expuesto, dependencias sin lock (cada build instala "lo último de ese día"), código montado desde el checkout en vez de la imagen, esquema creado con `create_all()` más cinco migraciones sueltas en el arranque, crons dentro de los workers web y un deploy que hace `git reset --hard` y construye en la VM.

La decisión estratégica de migrar el frontend a Vue (Paso 2) cambia las prioridades respecto de las auditorías originales: **no se moderniza lo que se va a apagar**. El frontend legacy recibe solo seguridad y pines; el backend, que se queda, recibe el trabajo completo (reproducibilidad, Alembic, calidad, operación) y el puente de auth/contrato para la SPA.

Siete fases, cada una un PR (o pocos) con criterio de salida y rollback:

| Fase | Qué | Esfuerzo | Bloquea al Paso 2 |
|---|---|---|---|
| F01 | Frontend legacy: gunicorn, debug off, cookies, sin CORS abierto, pines de CDN, bumps | S (2-3 días) | Sí |
| F02 | Backend: PyJWT, hash de backup codes y magic links, admin por defecto, guardas de entorno | S (2-3 días) | Sí |
| F03 | Reproducibilidad: uv + lock, Python 3.14, imagen = código, compose prod/dev | M (1 semana) | Sí |
| F04 | Esquema: Alembic baseline, migraciones fuera del lifespan | M (1-2 semanas) | Sí: F07 crea la tabla de refresh tokens como revisión Alembic |
| F05 | Calidad y CI: Ruff, gates, Dependabot, docs | S (2-3 días) | Sí |
| F06 | Operación: scheduler separado, ADC para GCS, deploy (token, migración, imágenes) | M (1-2 semanas; 6b diferible) | 6a sí; 6b recomendado antes del piloto |
| F07 | Puente a v2 (la Fase 0 de v2-final): Scalar/OpenAPI, `/auth/me`, refresh token en cookie, descargas, rate limit | M (2-3 semanas) | Sí — es el gate |

Total orientativo: **6-9 semanas calendario** con 1-2 devs asistidos por IA, con F03 y F04 en paralelo. El calendario completo Paso 1 + Paso 2 está en `update-techs-v2-final.md` §9 (8-11 meses).

---

## 2. Inventario verificado (2026-09-07)

### 2.1 Backend (FastAPI) — permanece

| Tecnología | En uso | Última (2026-09-07) | Estado / decisión |
|---|---|---|---|
| Python (Docker/CI) | 3.12 (`backend/Dockerfile:4,25`, `test.yml`) · local 3.14.2 (`__pycache__` 100 % `cpython-314`) | 3.14.7 (2026-08-05) · 3.13.15 | Unificar en **3.14** (F03) |
| FastAPI | `>=0.104.0` flotante | 0.141.1 (2026-07-29) | OK; lockear (F03) |
| Uvicorn | `>=0.24.0`, 5 workers (`Dockerfile:65`) | flota | OK |
| SQLAlchemy | `>=2.0.0` sync | 2.0.52 (2026-08-11); 2.1 no liberada | Lockear 2.0.x; 2.1 diferida |
| Driver PG | `psycopg2-binary>=2.9.0` | psycopg 3.3.5 | Diferido a después de F03/F04 (§7) |
| Pydantic / pydantic-settings | `>=2.5` / `>=2.1` | flota | OK |
| JWT | `python-jose[cryptography]>=3.3.0` (`dependencies.py:8`, `auth/routers.py:8`) | python-jose 3.5.0 (2025-05) · PyJWT 2.13.0 (2026-05) | **PyJWT** (F02) |
| Passwords | bcrypt, truncado a 72 bytes documentado (`usuarios/models.py:56-68`) | — | OK; Argon2id diferido (§7) |
| 2FA | pyotp + qrcode; secreto y backup codes en claro (`auth/routers.py:481`, `520-525`) | — | Hashear backup codes (F02); cifrar el secreto diferido |
| Magic link | token en claro en `magic_link_token`, índice único (`usuarios/models.py:38`) | — | Guardar hash (F02) |
| Reset de password | JWT `type=reset` de 1 h (`auth/routers.py:739-759`) | — | OK |
| HTTP client | `httpx>=0.25.0`; tests con `httpx2>=2.0.0` | httpx 0.28.1 (2024-12) · httpx2 2.12.0 (2026-08) | httpx2 en código propio, después del lock (Decisión 8) |
| PDF / imagen | Pillow, pypdf, PyMuPDF (AGPL) | flota | OK (licencia: uso interno) |
| Email / Webex / LLM / GCS | sendgrid, httpx, google-genai, google-cloud-storage | flota | OK; GCS ya soporta ADC (`storage.py:123-127`) |
| Docs API | Swagger + ReDoc (`main.py:623-624`, `config.py:42-43`) | scalar-fastapi 1.9.0 | Scalar en F07 |
| Migraciones | `create_all()` + 5 scripts en el lifespan (`main.py:107-132`); tests con `create_all` (`tests/conftest.py:24`) | Alembic 1.19.2 | **Alembic** (F04) |
| Logging | texto a stdout, `LOG_LEVEL` (`core/logging_config.py`) | — | Se mantiene; `X-Request-ID` (F06a, requerido por el DoD de v2-final §8) |
| Crons | threads por worker + advisory lock (`main.py:154-164`) | — | Servicio `scheduler` (F06) |
| Tests | pytest 8 + pytest-cov 5; backend 24 archivos (18 integration, 5 services, 1 smoke), frontend 7 smoke; 231 funciones de test; 106 marcas `deploy_gate` | al día | OK |

### 2.2 Frontend (Flask + HTMX) — se apaga en el Paso 2

| Tecnología | En uso | Última | Decisión |
|---|---|---|---|
| Flask | 3.0.0 pineada | 3.1.3 (2026-02-19) | Bump (F01) |
| flask-cors | 4.0.0; `CORS(app)` sin restricciones (`app.py:26`) | 6.0.5 | **Eliminar** (F01) |
| httpx | 0.26.0 | 0.28.1 (última 0.x) | Bump (F01) |
| gunicorn | 21.2.0 instalado, **no usado** | 26.2.0 (2026-08-24) | Usar (F01) |
| Servidor | `python app.py` → `app.run(debug=True)` (`Dockerfile:32`, `app.py:361`) | — | **P0** (F01) |
| Imagen | `python:3.12-slim`, sin `USER`, sin `HEALTHCHECK` | — | F01 / F03 |
| HTMX | 1.9.10 + ext `response-targets` (`base.html:71-72`) | 2.0.10 `latest` · 4.0.0 (2026-08-28, `next`) | No se toca |
| Alpine.js | 3.14.8 + collapse (`base.html:75,132`) | 3.17.2 | No se toca |
| Tailwind | Play CDN sin versión, config inline (`base.html:16-60`) + 2 templates de certificados | 4.3.3 · Play CDN v3 pineable en `…/3.4.17` | Pinear, no compilar (Decisión 2) |
| Lucide | `@latest` (`base.html:68`) | 1.42.0 | **Pinear** (F01) |
| Google Fonts | Plus Jakarta Sans / Inter / Playfair (CDN) | — | Se mantiene |
| qrcodejs 1.0.0 · html2canvas 1.4.1 · jspdf 2.5.1 · pdf-lib 1.17.1 | certificados y `mis_recibos` | sin mantenimiento | Congelar; rediseñar en Vue (v2, ola B) |
| Sesión | cookie firmada client-side con el JWT adentro; 30 días con "recordarme" (`app.py:24`); JWT de 30 min sin refresh | — | Cookies seguras (F01); modelo nuevo en F07 |
| Tamaño | 16 módulos · 164 templates · 33.065 líneas · 281 rutas (170 mutantes) · 692 `hx-*` · 151 `x-data` · 100 `<form>` · 77 `fetch()` | — | Insumo de v2 |

### 2.3 Datos, infraestructura y CI

| Componente | En uso | Última | Decisión |
|---|---|---|---|
| PostgreSQL | `postgres:16-alpine` (flota dentro de 16.x); extensiones `uuid-ossp` y `pgcrypto` (`database/init.sql`) | 16.15 (EOL 2028-11-09) · 17.11 · 18.6 | Pinear 16.15 (F03); 18 después de Vue (§7) |
| Compose | un solo archivo para dev y prod; monta código `:ro`; publica `6000` de Postgres; monta `secrets/*.json` | — | Base apto para prod + override dev (F03); sin secreto montado (F06) |
| CI | `actions/checkout@v5`, `setup-python@v6`, Python 3.12, pytest con Postgres real; sin lint, sin auditoría de dependencias, sin Dependabot | — | F03 / F05 |
| CD | `release: published` → WIF → IAP → `git reset --hard origin/main` → `docker compose up -d --build` en la VM; token persistido en `.git/config` | — | F06 |
| Gestión de dependencias | pip + `requirements.txt` con `>=`; sin `pyproject.toml`, sin lock | uv 0.12.10 | **uv** (F03) |
| Lint / format | ninguno | ruff 0.16.6 | **Ruff** (F05) |
| Tooling local | Python 3.14.2, Docker 29.7.2, Node 24; **sin uv ni ruff instalados** | — | Prerrequisito de la persona (F03) |

### 2.4 Lo que está bien y no se toca

- FastAPI + Pydantic v2 + SQLAlchemy 2 sync; `google-genai` (SDK vigente); SendGrid.
- Backend Dockerfile multistage con usuario no-root, healthcheck y stage de test.
- Advisory locks para serializar el arranque entre workers (se conservan como segunda defensa aunque los crons salgan del proceso web).
- Deploy por túnel IAP sin IPs públicas; auth de CI a GCP por Workload Identity Federation.
- Suite de tests con Postgres real y marcador `deploy_gate`.
- La abstracción de storage (`local_storage` / `cloud_storage`) con fallback a ADC.
- La apuesta HTMX en sí para el legacy: no se invierte, pero tampoco se rompe.

---

## 3. Hallazgos con evidencia

### P0 — corregir primero

**3.1 Frontend en producción con el dev server de Werkzeug y debugger activo.**
`frontend/Dockerfile:32` ejecuta `python app.py`; `frontend/app.py:361` llama `app.run(host='0.0.0.0', port=port, debug=True)` sin mirar la env var; `app.py:16` defaultea `DEBUG` a `True`. Riesgo: el debugger de Werkzeug permite ejecución remota de código a quien alcance el puerto; el dev server no tiene concurrencia real. Agravantes: `SECRET_KEY` con fallback `'frontend-secret-key'` (`app.py:15`) — si la env var faltara, las sesiones serían forjables; el contenedor corre como root.
Fix (F01): gunicorn con workers gthread y `--timeout` mayor a los 120 s que usa `api_request` (`app.py:87`) para subidas y PDFs; `DEBUG` default `False`; fallar el arranque sin `SECRET_KEY` fuera de tests; `USER` no-root y `HEALTHCHECK` en la imagen; `python app.py` solo en el override de desarrollo.

### P1 — antes de empezar el Paso 2

**3.2 Sesión Flask sin endurecer y CORS abierto.** No hay `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE` ni `PREFERRED_URL_SCHEME`; `CORS(app)` (`app.py:26`) habilita cualquier origen sin necesidad (todos los `fetch()` de los templates apuntan a rutas Flask propias); no hay protección CSRF. Mitiga hoy: Chrome y Edge tratan las cookies sin `SameSite` como `Lax` (Firefox y Safari no), y no se encontraron rutas GET que muten. Fix (F01): flags explícitos, `SameSite=Lax`, chequeo de `Origin`/`Referer` en `POST/PUT/PATCH/DELETE` como `before_request`, eliminar flask-cors. Tokens CSRF completos: Decisión 3.

**3.3 Builds no reproducibles y producción que no corre la imagen.** `backend/requirements.txt` con `>=` sin lock: cada `docker build` resuelve versiones distintas sin cambio en el repo. El compose monta `./backend:/app/backend:ro` y `./frontend:/app:ro` también en producción (el deploy usa el mismo archivo): la imagen construida no es lo que corre. Python 3.12 en Docker/CI contra 3.14.2 local: los tests locales no prueban el runtime de producción. `lucide@latest` y el Play CDN sin versión cambian sin tocar el repo. Fix: F01 (pines), F03 (uv + lock + 3.14 + compose).

**3.4 Esquema gestionado en el arranque web.** `Usuario.metadata.create_all()` (`main.py:113`) más cinco migraciones ad hoc ejecutadas en cada arranque bajo advisory lock (`main.py:107-132`), incluida una marcada "TEMPORAL … eliminar después de implementar Alembic". `create_all()` no altera columnas ni constraints; no hay historial ni rollback; cada worker intenta DDL. Fix: F04.

**3.5 python-jose.** Ver §0 fila 2. Migración a PyJWT en `dependencies.py` y `auth/routers.py`: `jwt.encode/decode` mantienen la firma; `JWTError` → `jwt.PyJWTError`; el claim `sub` ya es el email (string), requisito de PyJWT ≥ 2.10. Fix: F02.

**3.6 Secretos de auth recuperables desde la DB.** Backup codes 2FA en JSON en claro (`auth/routers.py:520-525`, verificación en `581-585`); magic links en claro con índice único (`usuarios/models.py:38`); secreto TOTP en claro (`routers.py:481`) — este último tiene que ser recuperable para validar, así que cifrarlo requiere gestión de claves (diferido, §7). Fix (F02): hash de backup codes y de magic links.

**3.7 Deploy y secretos de infraestructura.** `deploy.yml` clona con `https://x-access-token:${CODE_TOKEN}@github.com/…` y hace `git remote set-url origin` con esa URL: el token queda en `.git/config` de la VM. El JSON de la service account de GCS se monta desde `secrets/` aunque `storage.py` ya soporta ADC. El deploy mezcla build y release (`git reset --hard` + `--build` en la VM), sin artefacto identificable ni rollback de un comando. Fix: F06.

### P2 — cuando haya ventana dentro del Paso 1

**3.8 Crons dentro de los workers web.** Cinco workers arrancan cinco threads por cron (`main.py:154-164`); el advisory lock evita el trabajo duplicado pero no el acoplamiento al ciclo de vida web (un `restart` o un escalado cambia el scheduler) ni los logs repetidos. Fix (F06): flag `CRON_ENABLED` y servicio `scheduler` de una réplica.

**3.9 Admin por defecto y defaults del template.** `admin@admin.com / admin` solo en `development` (`main.py:170-188`, y `main.py:186` imprime el password en el log); `.env.template` trae `DEBUG=True`, `ENVIRONMENT=development` y `RECIBOS_ADMIN_ALLOWED_EMAILS=admin@admin.com`. Fix (F02): password del seed desde variable o aleatoria impresa una vez; template con defaults seguros; verificar el `.env` de la VM (persona).

**3.10 Postgres publicado en el host y sin pin de patch.** `ports: "${POSTGRES_EXTERNAL_PORT}:5432"` en el mismo compose de producción (la VM no tiene IP pública: riesgo bajo); `postgres:16-alpine` flota dentro de 16.x. Fix (F03): sin puerto en el archivo base; `postgres:16.15-alpine`.

**3.11 Sin lint ni auditoría de dependencias; documentación desactualizada.** Fix: F05.

---

## 4. Decisiones de alcance (candidatas a `D-##` en director)

Cada una con la alternativa descartada, para que quede registrada y se pueda revertir con motivo.

**Decisión 1 — Inversión mínima en el frontend legacy.** No se migra HTMX (ni a 2.x ni a 4.0), no se actualiza Alpine, no se arma build de Tailwind en Jinja, no se vendorean assets, no se agrega CSP. Solo seguridad (F01) y pines de versión. Motivo: el frontend se apaga en el Paso 2 (v2 §2.3 y §5); htmx 2.x sigue soportado indefinidamente; todo lo demás sería trabajo descartado. Alternativa descartada: `update-techs-sol-v2.md` §9 (compilar Tailwind + tokens en legacy) — los tokens son ~40 líneas inline que se portan a `@theme` de Vue en minutos, y un build sobre 164 templates Jinja con clases dinámicas tiene riesgo de regresión (safelist) que no se justifica.

**Decisión 2 — Tailwind: pinear el Play CDN, no compilar.** Reemplazar `https://cdn.tailwindcss.com` por `https://cdn.tailwindcss.com/3.4.17` en los 3 templates (verificado que sirve una versión fija) y documentar los tokens de `base.html:18-60` en `docs/Design-Tokens.md` como insumo del theme Vue. Riesgo residual aceptado: el CSS se compila en el navegador en cada carga (rendimiento, no seguridad). Alternativa: self-hostear el mismo script en `frontend/static/vendor/` si se quiere eliminar el CDN en runtime (S).

**Decisión 3 — CSRF en legacy: mitigación por cabeceras ahora, tokens solo si se pide.** F01 aplica `SameSite=Lax` + `Secure` + rechazo de métodos mutantes cuyo `Origin`/`Referer` no coincida con el host (defensa reconocida por OWASP, un `before_request`, sin tocar templates). Los tokens (Flask-WTF `CSRFProtect` + `hx-headers` en `<body>` + hidden input en 100 formularios + cabecera en 77 `fetch()`) son M con riesgo de regresión en una app con 7 tests de smoke. **Depende del usuario**: aceptar el riesgo residual hasta el apagado o pagar los tokens. Si se pagan, van en un PR propio después de F01.

**Decisión 4 — flask-cors se elimina, no se actualiza.** No hay consumidor cross-origin del Flask. Si en el PR aparece uno (verificar Webex y certificados públicos), se reinstala 6.0.5 con allowlist exacta.

**Decisión 5 — Python 3.14 unificado.** Docker, CI y local en 3.14 (local ya está en 3.14.2; latest 3.14.7). Un PR previo con matriz 3.12/3.14 en CI para detectar wheels faltantes (PyMuPDF, Pillow, psycopg2-binary, bcrypt, cryptography, pydantic-core, grpc de GCS). Alternativa descartada: 3.13 (obligaría a bajar el local y no gana nada).

**Decisión 6 — uv con `pyproject.toml` + `uv.lock` por servicio (dos proyectos, no workspace).** Backend y frontend son imágenes distintas con dependencias distintas, y el frontend desaparece; un workspace agregaría acoplamiento sin beneficio. El primer lock reproduce lo que hoy resuelve pip (capturar `pip freeze` de las imágenes actuales); las subidas de versión van después, por familia y en PRs separados.

**Decisión 7 — Alembic con baseline; `create_all()` solo en tests.** Las 5 migraciones ad hoc se absorben en la baseline (ya están aplicadas en producción) y se eliminan. La migración corre como paso de release (una vez), no en el lifespan. Las extensiones de `init.sql` pasan a la baseline (`CREATE EXTENSION IF NOT EXISTS`).

**Decisión 8 — httpx2 para el código propio del backend, después del lock.** httpx 0.28.1 no tiene releases desde 2024-12; httpx2 es la continuación mantenida y ya está en tests. Condición: que `google-genai`, `sendgrid` y `google-cloud-storage` no fijen `httpx<1`. Frontend: solo bump a 0.28.1.

**Decisión 9 — PostgreSQL se queda en 16 durante el Paso 1 y el Paso 2.** 16.15 con soporte hasta 2028-11. 18.6 se evalúa después de apagar Flask, con ensayo de dump/restore (nunca montar un volumen 16 en una imagen 18). psycopg 3 sí puede entrar antes (S), después de F03/F04.

**Decisión 10 — Scheduler: servicio separado en el mismo compose, no Cloud Scheduler.** Mismo código, flag `CRON_ENABLED=true` solo en el servicio `scheduler` (1 réplica, `--workers 1`); los workers web arrancan con el flag en `false`. Cloud Scheduler / Cloud Run Jobs quedan para el ADR "VM vs Cloud Run" (§7).

**Decisión 11 — Deploy en dos tramos.** 6a (barato, ahora): no persistir el token en la VM, `docker compose -f docker-compose.yml` explícito (sin override de dev), paso `alembic upgrade head` antes de `up`, guardar la imagen anterior. 6b (recomendado antes del piloto Vue): CI construye y publica en Artifact Registry, la VM hace `pull` por digest, rollback de un comando. Las dos son compatibles con seguir en la VM.

**Decisión 12 — Auth de navegador para la SPA: refresh token rotativo en cookie `httpOnly` + access token en memoria.** Es el diseño consolidado en `update-techs-v2-final.md` §3; se construye en F07 sin cambiar el login de Flask (puente de sesión). Corrección al diseño: hoy el JWT ya viaja en la cookie de sesión de Flask (§0 fila 14); el puente debe emitir la cookie de refresh desde FastAPI y dejar de depender de la sesión Flask para la SPA.

**Decisión 13 — Diferidos explícitos (§7):** Argon2id, cifrado del secreto TOTP, Secret Manager, OpenTelemetry/logs JSON, SBOM/CodeQL/Trivy/actions por SHA, Cloud Run/Cloud SQL, Terraform, consolidar Flask en FastAPI/Jinja (superada por Vue), MariaDB (no).

---

## 5. Plan por fases

Convenciones: cada fase es un PR (o una serie corta) que pasa `test.yml` completo y una prueba manual de humo (login + 2FA, selección de empresa, permisos con un usuario restringido, carga y descarga de recibos, un ticket de soporte). Los ítems marcados **(persona)** dependen del usuario (accesos, decisiones, VM) y en `director` van con `destraba=usuario` o `infra`.

### F01 — Frontend legacy: seguridad mínima

Esfuerzo S (2-3 días) · P0/P1 · bloquea el Paso 2.

- [ ] `frontend/Dockerfile`: stage `runtime` con `CMD ["sh","-c","gunicorn --bind 0.0.0.0:${FLASK_PORT} --worker-class gthread --workers 2 --threads 8 --timeout 180 --access-logfile - app:app"]`; `USER` no-root; `HEALTHCHECK` contra `/health` (`core/app_module.py:501`); `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`. Calibrar workers/threads con la VM real, no adoptar los valores a ciegas.
- [ ] `frontend/app.py:16`: `DEBUG` default `False`; `app.py:361`: `debug=app.config['DEBUG']`. `python app.py` con reload queda solo en el override de desarrollo (F03); hasta entonces, `command:` en el compose local.
- [ ] `app.py:15`: sin fallback de `SECRET_KEY` fuera de `TESTING` (fallar al arrancar con mensaje claro).
- [ ] Cookies: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, `SESSION_COOKIE_SECURE` según `ENVIRONMENT` (ProxyFix ya está, `app.py:32`), `PREFERRED_URL_SCHEME='https'` en producción.
- [ ] `before_request` que rechaza `POST/PUT/PATCH/DELETE` cuando `Origin` (o `Referer` si no hay `Origin`) no coincide con el host; exceptuar `/health` y cualquier webhook entrante que se identifique en el PR.
- [ ] Eliminar `CORS(app)` y `flask-cors` de `requirements.txt` (Decisión 4). Verificar en el PR que ningún cliente externo llama al Flask cross-origin.
- [ ] Pinear `lucide@latest` → `lucide@1.42.0` (`base.html:68`); Play CDN → `/3.4.17` en `base.html:16`, `certificate_public.html` y `certificate_not_found.html` (Decisión 2).
- [ ] Bumps: Flask 3.0.0 → 3.1.3 (revisar changelog 3.1), httpx 0.26.0 → 0.28.1, gunicorn 21.2.0 → 26.2.0.
- [ ] `docs/Design-Tokens.md` con los tokens de `base.html:18-60` (colores `primary/accent/dark`, fuente, sombras, animaciones) como insumo del theme Vue; lo consume v2-final F08.
- [ ] **(persona)** Confirmar qué termina TLS delante del contenedor `frontend` en la VM (fuera del compose): condiciona `SESSION_COOKIE_SECURE` y el proxy único de v2-final F08, que toma el puerto 80.
- [ ] **(persona)** Decisión 3: ¿tokens CSRF completos en legacy? Si sí, PR propio a continuación (M).

No incluir: HTMX/Alpine/Tailwind build, cambios visuales, Python 3.14 (va en F03).

Criterio de salida: la imagen de producción no arranca Werkzeug ni el debugger; `/health` responde bajo gunicorn; `docker compose up` local funciona con la imagen y con el modo dev; `frontend/tests` verde; humo manual completo; un `POST` con `Origin` ajeno devuelve 403.

Rollback: revertir el PR (solo imagen). Las cookies nuevas invalidan sesiones previas: avisar que hay que volver a loguearse.

### F02 — Backend: auth y secretos baratos

Esfuerzo S (2-3 días) · P1/P2 · bloquea el Paso 2.

- [ ] python-jose → PyJWT 2.13 en `backend/dependencies.py:8` y `backend/modules/auth/routers.py:8`: `from jose import jwt, JWTError` → `import jwt` / `jwt.PyJWTError`; conservar `algorithms=[…]`; tests de token expirado, firma inválida y `sub` string. Quitar `python-jose[cryptography]` de `requirements.txt`; actualizar `README` ("JWT con PyJWT").
- [ ] Backup codes 2FA: hoy son `token_hex(4)`, 8 hex, 32 bits, guardados en claro (`auth/routers.py:520-525`). Guardar HMAC-SHA256 con un pepper del servidor (`BACKUP_CODES_PEPPER`, fuera de la DB) o bcrypt, nunca sha256 pelado, que con 32 bits se fuerza en segundos; comparar contra hash al verificar (`581-585`); **migración de datos única** que hashea en el lugar los códigos existentes, así nadie regenera nada; al regenerar, códigos de 10 caracteres. El secreto TOTP no se toca: **ningún usuario re-enrola el 2FA**.
- [ ] Magic links: guardar hash del token en `magic_link_token` y buscar por hash (`usuarios/models.py:38`, `usuarios/services.py`); la expiración ya existe. Los pendientes se hashean en la misma migración de datos, o se dejan vencer y se reenvían.
- [ ] Seed de admin (`core/seed_data.py:22-23`, `main.py:184-186`): password desde `SEED_ADMIN_PASSWORD` o aleatoria impresa una sola vez; no imprimir el password en el log; `.env.template` con `DEBUG=False`, `RECIBOS_ADMIN_ALLOWED_EMAILS=` vacío y comentario de qué setear en producción.
- [ ] Guarda de arranque: si `ENVIRONMENT=production` y (`DEBUG=true` o `SECRET_KEY`/`JWT_SECRET_KEY` con valores del template), abortar con mensaje.
- [ ] **(persona)** Verificar en el `.env` de la VM: `ENVIRONMENT=production`, `DEBUG=False`, secretos distintos del template.

No incluir: Argon2id, cifrado del secreto TOTP, rate limiting (va en F07 con la auth nueva), refresh tokens.

Criterio de salida: suite backend verde; login, 2FA (código y backup code), magic link y reset de password probados a mano con un usuario enrolado **antes** del deploy, cuyos códigos viejos tienen que seguir valiendo; `python-jose` ausente de la imagen.

Rollback: revertir el PR. Los hashes no son reversibles, pero la migración parte de valores en claro y nada se pierde: los backup codes ya emitidos siguen valiendo, los magic links pendientes también (o se reenvían) y el 2FA de nadie se resetea. Revertir el código después de la migración de datos exige restaurar esas dos columnas desde el backup previo al deploy, que es parte del paso de release.

### F03 — Reproducibilidad: uv, lock, Python 3.14, imagen = código

Esfuerzo M (1 semana) · P1 · bloquea el Paso 2 · paralelizable con F04.

- [ ] **(persona)** Instalar `uv` (y `ruff`, para F05) en la máquina de desarrollo.
- [ ] Capturar baseline: `docker compose run --rm backend pip freeze` y lo mismo para `frontend`; guardar en `docs/upgrade/baseline-2026-09.txt` para que el primer lock reproduzca lo que hoy corre.
- [ ] `backend/pyproject.toml` (`[project]` con las dependencias actuales, `[dependency-groups] test`) + `uv lock`; ídem `frontend/`. Mantener `requirements.txt` solo hasta que CI y Dockerfiles usen uv; después eliminarlos.
- [ ] Dockerfiles: builder con `uv sync --frozen --no-dev` (imagen `ghcr.io/astral-sh/uv` copiada o `pip install uv`), runtime copia el venv; base `python:3.14-slim` pineada por tag (digest opcional).
- [ ] CI `test.yml`: `astral-sh/setup-uv` + `uv sync --frozen`; `uv lock --check` como gate; matriz `3.12`/`3.14` en un PR previo, luego solo `3.14`.
- [ ] Unificar Python 3.14 en `backend/Dockerfile`, `frontend/Dockerfile` y `test.yml`; verificar wheels (Decisión 5) y warnings de deprecación.
- [ ] Compose: `docker-compose.yml` apto para producción (sin mounts de código, sin `ports` de Postgres, `postgres:16.15-alpine`; el mount de `secrets/` se retira en F06) + `docker-compose.override.yml` de desarrollo (mounts `:ro`, reload, `python app.py`, puerto 6000), que Compose carga solo localmente. `deploy.yml` pasa a `docker compose -f docker-compose.yml …` (F06a).
- [ ] Actualizar `README` (comandos) y `docs/Arquitectura-Deploy.md`.
- [ ] Subidas de versión por familia, cada una su PR: tooling de test → FastAPI/Starlette/Pydantic → SQLAlchemy/driver → Flask/Werkzeug/Jinja → clientes HTTP e integraciones → PDF/imagen.

No incluir: psycopg 3, SQLAlchemy 2.1, Postgres 18, httpx2 (Decisión 8: PR propio después del lock).

Criterio de salida: dos builds del mismo commit producen el mismo árbol de dependencias; CI falla si `uv.lock` está desactualizado; la imagen de producción contiene el código (sin mounts); Python 3.14 en Docker, CI y local; suite verde.

Rollback: revertir por PR; `requirements.txt` sigue existiendo hasta el último PR de la fase.

### F04 — Esquema: Alembic

Esfuerzo M (1-2 semanas, según drift) · P1 · **bloquea a F07**: la tabla de refresh tokens nace como revisión Alembic, no como sexta migración a mano · paralelizable con F03.

- [ ] `alembic init backend/alembic`; `env.py` con `Base.metadata` y un módulo `backend/models_registry.py` que importe todos los modelos (hoy los importa `main.py:19-46`); URL desde `settings.database_url`.
- [ ] Baseline: DB limpia levantada con el flujo actual (`create_all` + 5 migraciones) → `alembic revision --autogenerate`; incluir `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` y `"pgcrypto"` (hoy en `database/init.sql`).
- [ ] **(persona)** `pg_dump --schema-only` de producción (y de un dev representativo) para comparar con la baseline; reconciliar diferencias antes de marcar la revisión.
- [ ] Absorber y eliminar las 5 migraciones ad hoc y sus llamadas en `main.py:107-132`; `create_all()` queda solo en `tests/conftest.py`.
- [ ] Paso de release: `docker compose run --rm backend alembic upgrade head` antes de `up` (F06a); `alembic stamp head` una única vez en producción y en cada dev existente (documentar en runbook).
- [ ] CI: `alembic upgrade head` sobre DB vacía + `alembic check` (modelos == migraciones) como gate.
- [ ] Runbook `docs/Migraciones.md`: crear revisión, expand/contract para cambios sin downtime, migraciones no reversibles y recuperación por backup.
- [ ] **(persona)** Verificar el backup actual de `postgres_data` en la VM y ensayar un restore antes del primer `upgrade` productivo.

Criterio de salida: DB vacía → `upgrade head` OK; copia de producción `stamp` + `check` limpio; ningún worker web ejecuta DDL; los tests siguen usando `create_all` (rápido) y CI prueba la cadena de migraciones.

Rollback: `alembic downgrade` para revisiones reversibles; para la baseline, restore del backup (documentado).

### F05 — Calidad, CI y documentación

Esfuerzo S (2-3 días) · P2 · bloquea el Paso 2 (gates mínimos) · después de F03 para no chocar con el lock y el formateo.

- [ ] Ruff en `pyproject.toml` raíz: `ruff check` (E, F, I; B y UP progresivos) + `ruff format`; un commit de formateo del repo completo (coordinar con PRs abiertos); `pre-commit` opcional, CI obligatorio.
- [ ] CI: jobs `lint` (ruff check + format --check), `lock` (`uv lock --check`), `tests` (los existentes), `audit` (`pip-audit` sobre `uv export` o equivalente), cobertura como artefacto sin umbral (fijar umbral cuando haya baseline).
- [ ] `.github/dependabot.yml`: `github-actions`, `docker`, `uv` (semanal, PRs agrupados).
- [ ] Docs: `README` (python-jose → PyJWT, enlace roto a `docs/Plan-Implementacion-TDD-Core.md`, comandos con uv y compose), `docs/Arquitectura-Deploy.md` (puertos, compose prod/dev, scheduler), `docs/Arquitectura-FrontEnd.md` marcada como legacy con puntero a v2, `backend/TODO LIST.md` (vaciar o eliminar).

Criterio de salida: CI con lint + lock + tests + audit verdes en `main`; Dependabot abriendo PRs; documentación consistente con el compose y el deploy nuevos.

### F06 — Operación: scheduler, identidad GCS, deploy

Esfuerzo M (1-2 semanas) · P1/P2 · 6a bloquea el Paso 2; 6b recomendado antes del piloto Vue.

**6a — barato, ahora**

- [ ] Crons fuera de los workers web: `settings.cron_enabled` (default `False`); `iniciar_cron_notificaciones()` e `iniciar_cron_sincronizacion()` (`main.py:154-164`) solo si está en `True`; servicio `scheduler` en el compose con la misma imagen, `--workers 1`, `CRON_ENABLED=true`, sin puerto publicado. Los advisory locks se conservan.
- [ ] El thread de certificados (`innovacion/services.py:236`) se documenta como fire-and-forget conocido; pasarlo a `BackgroundTasks` es opcional.
- [ ] GCS por ADC: **(persona)** adjuntar a la VM una service account con `roles/storage.objectAdmin` acotado al bucket; `GCS_CREDENTIALS_PATH=` vacío; quitar el mount de `secrets/` del compose; **(persona)** revocar y borrar la clave JSON. En desarrollo: `gcloud auth application-default login` o el fallback local que ya existe.
- [ ] `deploy.yml`: no persistir el token (fetch con `git -c http.extraHeader="AUTHORIZATION: bearer …"` por comando, o deploy key de solo lectura; limpiar `remote.origin.url` en la VM actual); `docker compose -f docker-compose.yml` explícito; paso `alembic upgrade head` antes de `up`; `docker image prune` solo después de confirmar `healthy`.
- [ ] **(persona)** Confirmar backup periódico de `postgres_data` (o `pg_dump` nocturno a GCS) y ensayar un restore.
- [ ] Middleware `X-Request-ID` en FastAPI y propagación desde el BFF (S; requerido: el DoD por módulo de v2-final §8 exige logs correlacionables): facilita correlacionar errores cuando conviva la SPA.

**6b — recomendado antes del piloto Vue**

- [ ] CI construye `backend` y `frontend` (después, las imágenes `spa` y `proxy` de v2-final §4.1) y publica en Artifact Registry con tag `sha` + digest; **(persona)** crear el repositorio de AR y dar `roles/artifactregistry.reader` a la SA de la VM.
- [ ] Compose de producción con `image: …@sha256:…` (o tag inmutable) en vez de `build:`; deploy = `pull` + `alembic upgrade head` + `up -d`; rollback = volver al digest anterior (guardado en la VM).
- [ ] SBOM y escaneo de imagen: diferidos (§7) salvo requisito.

Criterio de salida (6a): reiniciar o escalar `backend` no arranca crons; `scheduler` corre los dos crons con logs únicos; GCS funciona sin JSON; `.git/config` de la VM sin tokens; el deploy corre migraciones antes de levantar. (6b): la release desplegada es exactamente la imagen probada en CI; rollback de un comando probado.

### F07 — Puente hacia v2: contrato API y auth de navegador

Esfuerzo M (2-3 semanas) · es la Fase 0 del Paso 2 y el gate para arrancarlo · depende de F02, F03 y F04 · el modelo de auth consolidado está en `update-techs-v2-final.md` §3 y la convivencia en §4; este bloque es la lista de trabajo.

- [ ] Scalar: `scalar-fastapi` 1.9 en `/reference` (`docs_url=None`, `redoc_url=None`, o mantener Swagger en paralelo un tiempo); test que genera `/openapi.json` sin errores; agente y proxy externo de Scalar deshabilitados.
- [ ] `GET /api/v1/auth/me`: usuario, empresa activa, empresas disponibles, permisos efectivos y menú. Reutilizar `permisos/mis-permisos` y `menu_routers`; una sola llamada para el shell de la SPA.
- [ ] Refresh token rotativo: tabla `auth_refresh_tokens` (jti, usuario, empresa, expira, revocado) creada con una revisión Alembic (F04); cookie `httpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`; `POST /auth/refresh` (rota y devuelve un access token corto: el JWT actual de 30 min) y `POST /auth/logout` (revoca). Access token solo en memoria del cliente. Compatibilidad total con el Bearer que usa Flask.
- [ ] CSRF para los endpoints con cookie (`refresh`, `logout`): cabecera custom obligatoria (`X-Requested-With`) + `SameSite`; documentar.
- [ ] Puente de sesión: `POST /auth/login` (y `seleccionar-empresa`, 2FA) emiten la cookie de refresh; Flask reenvía el `Set-Cookie` al navegador en su respuesta de login, detrás del flag `AUTH_REFRESH_ENABLED`. El origen único lo aporta el proxy de v2-final F08; hasta entonces el puente se prueba con la página de prueba servida por FastAPI y, de punta a punta, en F08.
- [ ] Descargas: los GET de archivos (`/storage/*`, PDFs de recibos, fotos, exports) aceptan auth por cookie o devuelven URL firmada de corta duración (GCS ya lo permite; helper en `storage.py`).
- [ ] Rate limiting en login, 2FA, forgot/reset y magic link (`slowapi` o equivalente; por IP y por usuario). Con 5 workers el límite es por proceso salvo backend compartido: aceptable para empezar.
- [ ] Auditoría de endpoints acoplados al BFF para `parametros` y `sincronizacion` (los pilotos de v2): `response_model` completos, errores con forma estable, paginación uniforme. El resto se audita módulo por módulo antes de su ola.
- [ ] `operationId` legibles y estables en los routers que consumen los pilotos: el cliente TypeScript los usa como nombres de función. La generación del cliente (`@hey-api/openapi-ts`) y su check de drift viven en v2-final F08, porque necesitan el toolchain Node de la SPA.
- [ ] `CORS_ORIGINS` para el entorno de desarrollo con Vite.
- [ ] `docs/Auth-Navegador.md`: flujo, cookies, rotación, revocación, riesgos.

Criterio de salida (DoD del gate, tomado de v2 §3.3): una página HTML de prueba fuera de Flask puede loguearse por cookie, refrescar el token, pedir `/auth/me`, listar usuarios con un usuario restringido (403 donde corresponde) y descargar un PDF de recibo; Flask sigue funcionando sin cambios para el usuario; suite verde con tests de rotación y revocación.

Rollback: feature flag `AUTH_REFRESH_ENABLED`; sin la cookie, todo sigue como hoy.

---

## 6. Gate para empezar el Paso 2

Mínimo para abrir `frontend-vue/` (v2-final F08). Es el mismo gate que figura en `update-techs-v2-final.md` §1; si cambia en un lado, cambia en el otro.

- [ ] F01, F02, F03, F04, F05 y F06a cerradas y en producción.
- [ ] F07 con su DoD cumplido (F04 es prerrequisito de F07 por la tabla de refresh tokens).
- [ ] F06b se cierra dentro de v2-final F08, antes del primer piloto (F09): ahí entra a CI el build de la SPA.

Postgres 18, psycopg 3, httpx2 y SQLAlchemy 2.1 **no** bloquean el Paso 2.

---

## 7. Diferido explícitamente (con motivo y cuándo reconsiderar)

| Ítem | Origen | Motivo para diferir | Reconsiderar cuando |
|---|---|---|---|
| HTMX 2/4, Alpine 3.17, Tailwind compilado en Jinja, vendorear assets, CSP | v1 §4.2-4.3, sol §4.7, sol-v2 §9 | El legacy se apaga (Decisión 1); htmx 2.x soportado indefinidamente | La convivencia supere 12 meses o aparezca un bug/CVE concreto |
| Tokens CSRF en legacy | sol §4.3 | M con riesgo de regresión; mitigado por SameSite + Origin (F01) | Decisión 3 del usuario |
| Argon2id (`pwdlib`) con rehash on-login | sol §4.8 | bcrypt vigente y aceptado por OWASP; cambio transversal | Al rediseñar el login en Vue (ola C de v2) |
| Cifrado del secreto TOTP (KMS); Secret Manager para SendGrid/Webex | sol §4.8-4.9 | Requiere gestión de claves e infra; el secreto TOTP tiene que ser recuperable | ADR "VM vs Cloud Run" |
| Logs JSON + OpenTelemetry + Cloud Logging/Trace, SLOs | sol §4.12, sol-v2 §11 | Sin dolor operativo declarado; equipo chico; `X-Request-ID` (F06a) alcanza para correlacionar | Después del shell Vue, si hay incidentes que no se puedan diagnosticar |
| SBOM, CodeQL, Trivy, actions pineadas por SHA, gitleaks | sol §4.4, §4.12 | Dependabot + `pip-audit` cubren lo esencial para el tamaño del equipo | Requisito de compliance o de cliente |
| psycopg 3 (`postgresql+psycopg://`) | v1 §4.3, sol §5 | Cambiar driver mientras cambian lock, Python y migraciones suma variables | Después de F03 y F04; S; antes de PG 18 |
| PostgreSQL 18.6 | v1, sol | 16.15 soportado hasta 2028-11; upgrade mayor requiere ensayo | Después de apagar Flask |
| SQLAlchemy 2.1 | v1 | No liberada (2.0.52 al 2026-09-07) | Cuando salga estable |
| httpx2 en backend | sol §5 | Después del lock (Decisión 8) | PR propio post-F03 |
| Cloud Run + Cloud SQL + Cloud Scheduler; Terraform/OpenTofu | sol §9.2, §13 | Cambio de plataforma en medio de una migración de frontend | ADR post-Vue con TCO |
| Consolidar Flask en FastAPI/Jinja | sol §8 | Superada por la decisión Vue | — |
| MariaDB | sol §6.1 | No: UUID, advisory locks, integraciones PG | — |
| Pyright/mypy | sol §4.12 | El valor real llega con el cliente TS y los contratos; empezar por `response_model` (F07) | Paso 2 |

---

## 8. Riesgos y mitigaciones

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| gunicorn cambia comportamiento (timeouts en subidas de PDF, `ProxyFix`, streaming de descargas) | Media | Media | `--timeout 180` ≥ 120 s de `api_request`; humo de recibos y fotos; misma imagen en dev antes de mergear |
| El primer lock resuelve versiones distintas a producción | Alta | Media | Baseline `pip freeze` de las imágenes actuales; subir por familias en PRs separados |
| Python 3.14 sin wheel para algún paquete nativo | Media | Alta | PR previo con matriz 3.12/3.14 en CI |
| Baseline de Alembic ≠ esquema productivo (drift de 5 migraciones a mano) | Alta | Alta | Comparar contra `pg_dump --schema-only` real antes de `stamp`; restore ensayado |
| Cookies nuevas cierran sesiones y el chequeo de `Origin` bloquea un flujo legítimo (Webex, certificados) | Media | Media | Inventario de entradas externas antes del PR; excepción explícita por ruta; ventana de deploy |
| Refresh tokens mal diseñados (rotación, revocación, cookie en `/api`) | Media | Alta | DoD del gate; tests de rotación/replay; `Path` acotado; revisión cruzada |
| El Paso 1 se estira y compite con features | Alta | Media | Fases pequeñas con criterio de salida; F04 y F06b pueden solaparse con v2; tablero en `director` |
| Deploy nuevo rompe la VM sin rollback probado | Media | Alta | 6a antes que 6b; guardar imagen anterior; ensayo en horario controlado |

---

## 9. Estimación y orden

| Orden | Fase | Esfuerzo | Calendario (1-2 devs con IA) | Depende de |
|---|---|---|---|---|
| 1 | F01 | S | semana 1 | — |
| 2 | F02 | S | semanas 1-2 | — |
| 3 | F03 | M | semanas 2-3 | — |
| 3' | F04 | M | semanas 2-4 (en paralelo) | — |
| 4 | F05 | S | semana 4 | F03 |
| 5 | F06a | S/M | semanas 4-5 | F03, F04 |
| 6 | F07 | M | semanas 5-7 | F02, F03, F04 |
| 7 | F06b | M | semanas 7-9 (se cierra dentro de v2-final F08) | F03 |

El cuello de botella no es escribir código sino **QA manual sobre flujos críticos** y los ítems que dependen de la persona (VM, IAM, backups, decisiones). Conviene pedirlos en la semana 1.

---

## 10. Cómo cargarlo en `director`

- Hoy `director status` desde este repo resuelve a `proyecto`, un plan global de ejemplo (FastAPI + Vue + Docker, módulos clientes/facturas): antes de crear fases hay que asegurarse de que el proyecto activo sea el de `ops-sistema-gestion` (alta propia o `--proyecto`).
- Versión: `director version abrir v1 --motivo "arranque del plan Paso 1 (update-techs-v1-final)"`.
- Fases: `F01..F07` con los títulos de §5 (una `new --tipo fase` por cada una); F06 puede llevar los pendientes de 6a y 6b con sub-letras.
- Pendientes: cada checkbox de §5 es un `new --tipo pendiente --padre F0x`; los marcados **(persona)** con `--destraba usuario` o `--destraba infra`; el resto `--destraba claude --trabajo construccion`.
- Decisiones: §4 → `new --tipo decision` (D-01..D-13), con `link D-0x ejecuta F0y`; la Decisión 3 (CSRF) nace `abierto` con `destraba=usuario`.
- Dependencias: `F05 depende_de F03`, `F06 depende_de F03`, `F06 depende_de F04`, `F07 depende_de F02`, `F07 depende_de F03`, `F07 depende_de F04`; el Paso 2 arranca con `F08 depende_de F07` (v2-final §14).
- El gate §6 se registra como decisión («arranque del Paso 2») que se cierra cuando F01..F07 están cerradas; las fases del Paso 2 son `F08..F13` y están en `update-techs-v2-final.md` §14, en el mismo plan y la misma versión.
- Este archivo, `update-techs-v2-final.md` y los cuatro `update-techs*.md` origen se cargan como documentos (`director docs`) para trazabilidad; no se editan para cambiar estado.

---

## 11. Fuentes

Verificadas el 2026-09-07:

- PyPI: FastAPI 0.141.1 · Flask 3.1.3 · flask-cors 6.0.5 · httpx 0.28.1 · httpx2 2.12.0 · gunicorn 26.2.0 · python-jose 3.5.0 · PyJWT 2.13.0 · SQLAlchemy 2.0.52 · psycopg 3.3.5 · Alembic 1.19.2 · uv 0.12.10 · Ruff 0.16.6 · scalar-fastapi 1.9.0 — `https://pypi.org/project/<paquete>/`
- npm: htmx.org 2.0.10 (`latest`) · alpinejs 3.17.2 · tailwindcss 4.3.3 · lucide 1.42.0 — `https://registry.npmjs.org/<paquete>/latest`
- htmx 4.0.0 (2026-08-28): https://four.htmx.org/announcements/2026-08-28-htmx-4.0.0-is-released
- Python 3.14.7 / 3.13.15: https://www.python.org/downloads/
- PostgreSQL 18.6 / 17.11 / 16.15 y fechas de fin de soporte: https://www.postgresql.org/support/versioning/
- Tailwind Play CDN (solo desarrollo) y URL versionada: https://v3.tailwindcss.com/docs/installation/play-cdn · https://cdn.tailwindcss.com/3.4.17

Heredadas de los documentos origen (2026-08-06):

- FastAPI release notes: https://fastapi.tiangolo.com/release-notes/
- FastAPI security tutorial (PyJWT + pwdlib): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- Migración python-jose → PyJWT: https://github.com/jpadilla/pyjwt/issues/942
- Flask deploying: https://flask.palletsprojects.com/en/stable/deploying/
- uv sync/lock: https://docs.astral.sh/uv/concepts/projects/sync/
- Alembic: https://alembic.sqlalchemy.org/en/latest/index.html
- psycopg 3: https://www.psycopg.org/psycopg3/docs/basic/install.html
- Scalar FastAPI: https://scalar.com/products/api-references/integrations/fastapi
- OWASP CSRF (verificación de Origin/Referer): https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP Password Storage: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- OWASP tokens en SPA: https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html#local-storage
- GCP ADC con service account adjunta: https://cloud.google.com/docs/authentication/set-up-adc-attached-service-account
- Dependabot para Actions: https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/auto-update-actions
