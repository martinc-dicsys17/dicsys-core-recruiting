# ops-sistema-gestion (Dicsys Core)

## Idioma

- Responder siempre en español rioplatense (voseo), aunque el contexto, las herramientas, los logs o un
  resumen estén en inglés.
- Todo CLAUDE.md del repo lleva esta sección debajo del título.

## Documentación obligatoria antes de modificar código

- **Antes de generar o modificar código, leer y cumplir `docs/` según corresponda:**
  - Backend: `docs/Arquitectura-Backend.md` (estructura y contrato de la API), `docs/Modulos-Python.md` (dependencias y
    módulos nuevos) y `docs/Stack-Trace-Flujos.md` (flujos, manejo de errores y propagación de errores HTTP).
  - Frontend: `frontend-vue/README.md` (Vue 3, stack y convenciones de las pantallas nuevas) y
    `docs/Arquitectura-FrontEnd.md` (Flask con Blueprints, Jinja2, HTMX, Alpine.js y Tailwind; frontend legacy, solo
    para las pantallas existentes).
  - Base de datos: `docs/Migraciones.md`.
  - Ambiente de test y deploy: `docs/Ambiente-Test.md`.
  - Módulos con documentación propia: `docs/modulos/` y `docs/modulo/`, cuando exista la del módulo que se toca.
- **Si el pedido contradice la documentación, o la documentación no coincide con el código, decirlo antes de seguir.**
  No se resuelve en silencio ni se elige por cuenta propia.

## Balance de sobre-ingeniería

- **Antes de proponer o construir, evaluar si la complejidad se paga.** Cada servicio, bandera, tabla, abstracción,
  dependencia o prueba nueva tiene que resolver un problema real de este proyecto: un equipo de 1-2 devs, una VM
  con Docker Compose y uso interno. Lo que solo sirve «por si algún día» se anota como alternativa, no se construye.
- **Preferir la solución más simple que resuelve el problema de hoy.** Si hay una más barata que alcanza, va esa, y la
  más completa queda descrita en una línea para cuando haga falta.
- **Al proponer, decir en una línea qué agrega y qué gana.** Si el balance es dudoso, avisar y preguntar antes de
  construir.
- **Cuando cambia el contexto, revisar lo que quedó.** Si otra decisión o fase resolvió el problema que justificaba
  una pieza, decirlo y proponer simplificarla o actualizar el motivo. Ejemplo: D-10 (el scheduler aparte) nació por los
  crons duplicados en cada worker; F19 lo resolvió con su candado y el servicio quedó justificado por otras razones.

## Arquitectura en capas

- **Un módulo, cuatro archivos** (`backend/modules/<modulo>/`): `models.py`, `routers.py`, `schemas.py` y `services.py`.
  En el frontend, `frontend/modulos/<modulo>/app_module.py` (Blueprint) y sus templates. Un módulo nuevo se registra en
  `main.py` y `frontend/app.py`, y sus modelos en `backend/models_registry.py`.
- **Routers anoréxicos**: solo inyección de dependencias (`get_db`, `get_empresa_activa`, `get_current_user` y los
  permisos `require_modulo`, `require_submodulo` o `require_admin`), validación de la entrada y armado de la respuesta.
  Sin consultas ORM propias y sin transacciones (commit o rollback). Única excepción, documentada: la paginación
  uniforme, `paginar(Servicio.consulta(...), pagina, por_pagina)`; el service arma la consulta y el router solo la pagina.
- **La lógica de negocio, las consultas y la persistencia viven en los services**, incluidas las transacciones.
- **Pydantic v2 en toda la frontera de la API**: esquemas estrictos de request y de response, `response_model` en todo
  y sin diccionarios sueltos. El resto del contrato (errores `{"detail": ...}`, `operation_id` `<módulo>_<acción>`,
  ids de path `uuid.UUID`, paginación) está en `docs/Arquitectura-Backend.md`.
- **Multitenancy**: las tablas de datos de negocio llevan `empresa_id` y toda consulta filtra por la empresa activa del
  JWT (`get_empresa_activa`), nunca por una que mande el cliente. Los catálogos globales (por ejemplo, skills y
  habilidades de Recruiting) no la llevan; todo lo que tiene la columna se filtra siempre.
- **Pantallas nuevas en Vue (regla de arquitectura frontend).** Toda pantalla nueva se desarrolla con el frontend
  nuevo (Vue 3, `frontend-vue/`), tomando como referencia la implementación de Blacklist
  (`frontend-vue/src/modules/recruiting/blacklist/`): mismo stack (TypeScript, PrimeVue, TanStack Query, Pinia,
  Tailwind), misma estructura por pantalla (`api/`, `composables/`, `components/`), mismos estilos y mismo mecanismo de
  integración (host `frontend/modulos/vue_app`, entrada en `PANTALLAS_VUE` y compilado en `frontend/static/vue`). Se
  reutiliza lo existente antes de crear algo nuevo. **No se crean pantallas nuevas con Flask/Jinja2/HTMX/Alpine.** Las
  pantallas legacy siguen funcionando como están y se migran solo cuando el usuario lo pide. El diseño de Recruiting
  sigue siendo solo para escritorio (sin mobile-first ni responsive).
- **El frontend no toca la base**: habla con el backend por su API (`get_api_request_func()`) y protege sus rutas con
  `require_permiso`. El backend es el que valida el acceso de verdad; el frontend solo orienta la interfaz.
- **No inventar helpers, wrappers ni librerías fuera de los estándares documentados.** Antes de crear uno, buscar si ya
  existe (`backend/core`, `frontend/modulos/auth_helpers.py`). Una dependencia nueva sigue `docs/Modulos-Python.md`.

## Interfaz en español y datos nuevos sin tildes

- **Toda la interfaz está en español**: etiquetas, opciones de catálogos, enums visibles y mensajes. Sin anglicismos
  innecesarios en lo visible (por ejemplo «Líder» y no «Lead», «Reclutador» y no «Recruiter»). Se conservan los nombres
  de producto y de menú ya establecidos (Dashboard, Pipeline, Recruiting, Star Miles) y los términos técnicos
  universales.
- **Todo dato nuevo se escribe sin tildes ni acentos gráficos**: provincias y ciudades, catálogos, semillas, registros
  que inserta una migración, datos de prueba, altas manuales e importaciones automáticas (como la carga de CV).
  Ejemplos: `Cordoba`, `Neuquen`, `Rio Cuarto`, `San Sebastian`. No se insertan ni se guardan variantes con tilde.
- **No se normalizan en masa los datos existentes** por aplicar esta regla, ni se toca nada fuera del alcance de la
  tarea.
- **Alcance**: la regla es de *datos*. Los textos fijos de la interfaz, los mensajes de error de la API (castellano para
  mostrar tal cual), los comentarios, los docstrings y los docs siguen escritos en castellano correcto, con tildes,
  como el resto del código.

## Esquema de la base: migraciones con Alembic

- **Aviso y autorización previos.** Antes de crear, modificar o eliminar tablas, columnas, índices, claves foráneas,
  restricciones u otros elementos del esquema (es decir, antes de tocar modelos o crear la revisión), avisar qué se
  cambia y por qué, y esperar la confirmación del usuario. Sin autorización el cambio se propone, no se aplica; con más
  razón si es destructivo o puede afectar datos existentes.
- **Todo cambio de modelos lleva su revisión** en `backend/migraciones/versions`, en el mismo commit:
  `docker compose run --rm migraciones alembic revision --autogenerate -m "..."`, leerla y corregir lo que
  autogenerate no ve (CHECK, defaults de servidor, renames), aplicarla y dejar `alembic check` limpio.
- **Persistencia**: el esquema nunca depende de cambios hechos a mano en una base. Todo cambio queda en una revisión y,
  cuando corresponda, en los seeds y datos iniciales idempotentes del proyecto.
- El backend no crea ni altera tablas: lo hace el servicio `migraciones` del compose (`alembic upgrade head`) antes de
  que arranque. Un archivo de modelos nuevo va en `backend/models_registry.py`. Los tests usan `create_all` y
  `backend/tests/integration/test_migraciones.py` prueba la cadena.
- **Compatibilidad entre instalaciones**: levantar el proyecto desde cero, reconstruir los contenedores o desplegarlo
  en otra PC o servidor deja la base en el esquema correcto, sin perder datos ni duplicar cambios. Se verifica con
  `alembic check` y con `test_migraciones.py` (upgrade desde cero, downgrade y vuelta, adopción de una base anterior,
  una sola cabeza). Un cambio que rompe compatibilidad se reparte en expand y contract.
- **Informe final de una tarea que toca la base**: qué objetos cambiaron, qué archivos de migración se agregaron o
  modificaron, cómo se aplican y cómo se garantiza la persistencia entre instalaciones.
- Actualizar documentación no autoriza a modificar el esquema ni los datos.
- Runbook (release, expand/contract, adopción de bases de antes de Alembic, vuelta atrás): `docs/Migraciones.md`.

## Git, Docker y ejecución segura

- **Git**: el control de versiones lo gestiona el usuario. Nada de commit ni push por cuenta propia, ni de reset,
  checkout destructivo u otra operación que pueda descartar cambios del usuario. Staging solo si el usuario lo pide, y
  solo de lo que pide. Se pueden consultar `git status`, `git diff` y `git log`.
- **Docker**: no modificar, detener, reiniciar, eliminar ni reconstruir contenedores, imágenes o volúmenes del stack
  sin autorización explícita. Se puede consultar su estado y usar el entorno existente para validar. Quedan permitidos
  sin pedir permiso el compose de tests (`docker-compose.test.yml`, con `run --rm` y su base propia, aunque arme su
  imagen de test) y `docker compose run --rm migraciones` para correr `alembic check`. Generar una revisión o aplicar
  una migración a la base local requiere antes la autorización de la regla de esquema de arriba. Release y deploy los
  hacen el usuario o CI.
- **Pruebas seguras**: nunca se ejecutan operaciones destructivas ni se modifican datos reales para probar. Los tests
  usan su base propia; las verificaciones funcionales en Docker no crean, modifican ni borran datos de la base habitual
  sin autorización.

## Validación de los cambios

- **Todo cambio** (pendiente de construcción, fix, refactor, migración) **se valida con las pruebas propias del
  proyecto**; no se da por terminado sin una corrida verde de lo que toca:
  - Tests unitarios y de integración de backend (`backend/tests`).
  - Tests de frontend (`frontend/tests`).
  - Playwright E2E cuando el cambio afecta un recorrido de pantalla.
  - Verificación funcional en Docker, con el stack del compose.
- **Se prueba lo que cambiamos**: los tests nuevos cubren las operaciones de API y las rutas que el cambio toca. No hay
  meta de cobertura global ni backlog por módulo; lo que nadie toca se prueba el día que un cambio lo toque.
- **Se ejecuta solo lo pertinente al cambio** y se cierra la tarea: sin ciclos de verificación innecesarios.
- Los tests se escriben en este repo, junto al código.
- Al cerrar el pendiente en `director`, el as-built lleva la evidencia: los tests agregados y el resultado de las
  corridas.
- Los comandos `director ...` se corren en este repo.

## Comunicación e informes

- **Honestidad verificable**: informar qué pruebas pasaron, cuáles fallaron y cuáles no se pudieron ejecutar. Nunca
  afirmar que algo funciona si no se verificó.
- **Respuestas breves**: sin explicaciones largas ni desgloses paso a paso, salvo que el usuario pida un informe más
  detallado.
- **La respuesta final informa**: archivos modificados, pruebas ejecutadas con sus resultados y pruebas pendientes con
  su motivo.
