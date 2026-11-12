# Arquitectura de Despliegue - Dicsys Core

## Arquitectura General

```
+------------------------------------------------------------------+
|                        HOST / SERVIDOR                            |
|                                                                   |
|  +------------------------------------------------------------+  |
|  |                    Docker Engine                            |  |
|  |                                                             |  |
|  |  +------------------+  +------------------+  +------------+ |  |
|  |  |    frontend      |  |     backend      |  | postgresql | |  |
|  |  |------------------|  |------------------|  |------------| |  |
|  |  | Flask + HTMX     |  | FastAPI + Uvicorn|  | PostgreSQL | |  |
|  |  | Alpine.js        |  | Python 3.14      |  | 16.15      | |  |
|  |  | gunicorn         |  |                  |  | alpine     | |  |
|  |  | Python 3.14      |  |                  |  |            | |  |
|  |  | Puerto: 80       |  | Puerto: 6001     |  | Puerto:5432| |  |
|  |  +--------|---------+  +--------|----^----+  +------|-----+ |  |
|  |           |                     |    |              |       |  |
|  |           |   HTTP API          |    |   TCP/SQL    |       |  |
|  |           +-------------------->+    +--------------+       |  |
|  |                                                             |  |
|  |  +-------------------------------------------------------+  |  |
|  |  |                   ops_network (bridge)                |  |  |
|  |  +-------------------------------------------------------+  |  |
|  +------------------------------------------------------------+  |
|                                                                   |
+------------------------------------------------------------------+
        |              |              |
        | :80          | :6001        | :6000 (solo desarrollo)
        v              v              v
   +----------+   +----------+   +----------+
   | Usuario  |   | API Docs |   | DB Admin |
   | Browser  |   | /docs    |   | (local)  |
   +----------+   +----------+   +----------+
```

## Compose base y override de desarrollo

| Archivo | Uso | Qué tiene |
|---------|-----|-----------|
| `docker-compose.yml` | Producción y base de todo | Imágenes con el código adentro (target `runtime`), sin mounts de código, Postgres sin publicar |
| `docker-compose.override.yml` | Desarrollo local | Mounts de código `:ro`, `ENVIRONMENT=development` (uvicorn `--reload` y `python app.py`), Postgres en el 6000 |
| `docker-compose.test.yml` | Tests de los devs | Targets `test` de cada Dockerfile y un Postgres efímero |

Compose carga `docker-compose.override.yml` solo, junto al base, cuando no se pasa `-f`. Por eso en local alcanza
con `docker compose up`, y el deploy (`.github/workflows/deploy.yml`) usa `docker compose -f docker-compose.yml`:
el checkout de la VM también trae el override y así no se lee.

El deploy no deja el token de GitHub en la VM (F06-P05): lo pasa por stdin al script y cada `git` lo recibe en un header
por variables de entorno; el remote de `.git/config` queda sin credenciales.

El ambiente de test es una VM aparte que corre la rama `dev` y la QA, con un `.env` sin credenciales productivas: [Ambiente-Test.md](Ambiente-Test.md) (D-101).

En la rama `feature/upgrade-tech-stack` el job de `deploy.yml` está apagado (`if: ${{ false }}`): la rama no va a
producción. Se prueba en un ambiente de test con una copia de la base de producción (fase F23 del plan).

## Servicios Docker

| Servicio | Imagen | Puerto Int | Puerto Ext | Healthcheck |
|----------|--------|------------|------------|-------------|
| postgresql | postgres:16.15-alpine | 5432 | sin publicar (6000 en desarrollo) | pg_isready |
| migraciones | la del backend, `alembic upgrade head` | — | — | corre y termina |
| backend | python:3.14.9-slim + `backend/uv.lock` | 6001 | 6001 | curl /health |
| scheduler | la del backend, `CRON_ENABLED=true`, un worker | 6001 | sin publicar | curl /health |
| frontend | python:3.14.9-slim + `frontend/uv.lock` | 80 | 80 | curl /health |

Los puertos salen del `.env` (`BACKEND_PORT`, `FRONTEND_PORT`, `POSTGRES_EXTERNAL_PORT`); los de la tabla son los
de `.env.template`.

## Imágenes y dependencias

- Cada proyecto (`backend/`, `frontend/`) declara sus dependencias en `pyproject.toml` y las fija en `uv.lock`.
- Los Dockerfiles copian uv (`ghcr.io/astral-sh/uv:0.13.5`) y corren `uv sync --frozen --no-dev` en una etapa de
  build; el runtime copia el venv (`/opt/venv`) y el código. Dos builds del mismo commit instalan exactamente lo
  mismo.
- El target `test` suma el grupo `test` del lock; el target `runtime` es el último y el que usa producción.
- La versión de Python sale de `.python-version` en local y en CI, y de la etiqueta `python:3.14.9-slim` en las
  imágenes.

## URLs de acceso

### Interno (entre contenedores)
- Frontend → Backend: `http://backend:6001`
- Backend → Database: `postgresql://postgresql:5432/dicsys_core`

### Externo (desde host)
- Frontend Web: http://localhost:80
- API REST: http://localhost:6001
- API Docs (Scalar): http://localhost:6001/reference
- API Docs (Swagger): http://localhost:6001/docs
- API Docs (ReDoc): http://localhost:6001/redoc
- PostgreSQL: localhost:6000 (solo desarrollo, con el override). En producción: `docker compose exec postgresql psql`.

## Volúmenes

| Nombre | Tipo | Path contenedor | Descripción |
|--------|------|-----------------|-------------|
| postgres_data | volume | /var/lib/postgresql/data | Datos PostgreSQL |
| ./data/files | bind | /data/files | Archivos subidos |
| ./data/nomina/fotos | bind | /data/nomina/fotos | Fotos de empleados |
| ./data/llm | bind | /data/llm | Logs raw de LLM |
| ./data/cv | bind | /data/cv | CV archivados de Recruiting (carga masiva e individual) |
| ./data/innovacion/certificados | bind | /data/innovacion/certificados | Banners og:image de certificados |
| ./secrets/sheets-lectura.json | bind (ro) | /app/secrets/sheets-service-account.json | Service account de solo lectura de Sheets. GCS no lleva JSON: usa la identidad de la VM (F06-P04) |
| ./secrets/oidc | bind (ro) | /app/secrets/oidc | Claves de firma del proveedor OpenID Connect; dueño uid 1000 ([OIDC.md](OIDC.md)) |
| ./backend | bind (ro), solo override | /app/backend | Código backend en desarrollo |
| ./backend | bind, solo override | /app/backend (migraciones) | Revisiones nuevas creadas desde el contenedor |
| ./frontend | bind (ro), solo override | /app | Código frontend en desarrollo |

## Variables de entorno principales

| Variable | Servicio | Descripción |
|----------|----------|-------------|
| POSTGRES_USER | postgresql | Usuario de base de datos |
| POSTGRES_PASSWORD | postgresql | Password de base de datos |
| POSTGRES_DB | postgresql | Nombre de la base de datos |
| DATABASE_URL | backend | URL conexión PostgreSQL |
| ENVIRONMENT | backend, frontend | `development` cambia el comando a reload / `python app.py`; producción usa `production` |
| SECRET_KEY | all | Clave secreta para sesiones |
| JWT_SECRET_KEY | backend | Clave para tokens JWT |
| API_URL | frontend | URL interna del backend |
| DEBUG | all | Modo debug (True/False) |
| SENDGRID_API_KEY | backend | API key para envío de emails |

## Comandos de despliegue

```bash
# Producción (lo que corre deploy.yml en la VM, F06-P05): solo el compose base, migraciones antes de levantar
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml run --rm migraciones   # si falla, el deploy corta y lo que corre sigue igual
docker compose -f docker-compose.yml up -d --remove-orphans
# ...espera que backend, scheduler y frontend queden healthy y recién ahí: docker image prune -f

# Desarrollo local: base + override
docker compose up --build -d

# Ver logs de todos los servicios
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs -f backend

# Detener servicios
docker compose down

# Reconstruir imágenes
docker compose build --no-cache

# Reiniciar un servicio
docker compose restart frontend
```

## Orden de inicio

```
postgresql (healthcheck: pg_isready)
    ↓
migraciones (depends_on: postgresql healthy; alembic upgrade head y termina)
    ↓
backend (depends_on: migraciones completed successfully)
    ↓
frontend (depends_on: backend healthy)
```

El esquema es solo de `migraciones`: el backend no crea ni altera tablas al arrancar. Si la migración falla, el
backend no arranca. Como `up` recrea el backend (si cambió la imagen) antes de correr `migraciones`, un release
corre primero `docker compose -f docker-compose.yml run --rm migraciones`: si falla, el backend que estaba corriendo
sigue. Las extensiones de Postgres (`uuid-ossp`, `pgcrypto`) las crea la baseline; ya no hay `init.sql`. Detalle en
[Migraciones.md](Migraciones.md).

## Tareas programadas

El motor de tareas (F19, `backend/modules/tareas/programador.py`) corre en el servicio **`scheduler`** del compose:
la misma imagen del backend con `CRON_ENABLED=true`, un solo worker y sin puerto publicado (F06-P01, D-10). Corre los
saludos de cumpleaños, la Actualización de Datos y los avisos de proveedores, y despacha la cola de envíos. Los
horarios, cuáles están activas y el room de alertas se configuran en Parámetros.

- El servicio `backend` tiene `CRON_ENABLED=false`: reiniciarlo o escalarlo no arranca tareas, y los logs de las
  tareas salen una sola vez, en `docker logs scheduler`.
- Al arrancar, el scheduler asegura los parámetros `tarea_*` y el room de alertas, en cualquier entorno: sin ellos no
  corre ninguna tarea. Los demás seeds (admin, datos de ejemplo, procesos, soporte) siguen siendo solo de desarrollo.
- Si hubiera más de un proceso con `CRON_ENABLED=true`, uno solo hace de líder (advisory lock de Postgres): no se
  corre nada dos veces.
- «Ejecutar ahora» en Configuración → Tareas programadas deja la corrida pendiente y la toma el scheduler. Si el
  scheduler está caído, queda pendiente.
- El aviso de certificación completada de Innovación no es una tarea: sale en un hilo del backend, sin registro ni
  reintento (fire-and-forget, F06-P02). Si el backend se reinicia en esos segundos, el aviso se pierde
  (`CertificacionService._notificar_completada_async`).

## Red Docker

- **Nombre**: ops_network
- **Driver**: bridge
- Todos los servicios comparten esta red para comunicación interna
