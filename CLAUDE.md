# ops-sistema-gestion (Dicsys Core)

## Idioma

- Responder siempre en español rioplatense (voseo), aunque el contexto, las herramientas, los logs o un
  resumen estén en inglés.
- Todo CLAUDE.md del repo lleva esta sección debajo del título.

## Balance de sobre-ingeniería

- **Antes de proponer o construir, evaluar si la complejidad se paga.** Cada servicio, bandera, tabla, abstracción,
  dependencia o caso de QA nuevo tiene que resolver un problema real de este proyecto: un equipo de 1-2 devs, una VM
  con Docker Compose y uso interno. Lo que solo sirve «por si algún día» se anota como alternativa, no se construye.
- **Preferir la solución más simple que resuelve el problema de hoy.** Si hay una más barata que alcanza, va esa, y la
  más completa queda descrita en una línea para cuando haga falta.
- **Al proponer, decir en una línea qué agrega y qué gana.** Si el balance es dudoso, avisar y preguntar antes de
  construir.
- **Cuando cambia el contexto, revisar lo que quedó.** Si otra decisión o fase resolvió el problema que justificaba
  una pieza, decirlo y proponer simplificarla o actualizar el motivo. Ejemplo: D-10 (el scheduler aparte) nació por los
  crons duplicados en cada worker; F19 lo resolvió con su candado y el servicio quedó justificado por otras razones.

## Esquema de la base: migraciones con Alembic

- **Todo cambio de modelos lleva su revisión** en `backend/migraciones/versions`, en el mismo commit:
  `docker compose run --rm migraciones alembic revision --autogenerate -m "..."`, leerla y corregir lo que
  autogenerate no ve (CHECK, defaults de servidor, renames), aplicarla y dejar `alembic check` limpio.
- El backend no crea ni altera tablas: lo hace el servicio `migraciones` del compose (`alembic upgrade head`) antes de
  que arranque. Un archivo de modelos nuevo va en `backend/models_registry.py`. Los tests usan `create_all` y
  `backend/tests/integration/test_migraciones.py` prueba la cadena.
- Runbook (release, expand/contract, adopción de bases de antes de Alembic, vuelta atrás): `docs/Migraciones.md`.

## Validación de los cambios

- **Todo cambio** (pendiente de construcción, fix, refactor, migración) **se valida con las pruebas propias del
  proyecto**; no se da por terminado sin una corrida verde de lo que toca:
  - Tests unitarios y de integración de backend (`backend/tests`).
  - Tests de frontend (`frontend/tests`).
  - Playwright E2E cuando el cambio afecta un recorrido de pantalla.
  - Verificación funcional en Docker, con el stack del compose.
- **Se prueba lo que cambiamos**: los tests nuevos cubren las operaciones de API y las rutas que el cambio toca. No hay
  meta de cobertura global ni backlog por módulo; lo que nadie toca se prueba el día que un cambio lo toque.
- Los tests se escriben en este repo, junto al código. Las pruebas no modifican datos reales: los tests usan su base
  propia (compose de tests) y las verificaciones en Docker no crean ni borran datos de la base habitual sin
  autorización.
- Al cerrar el pendiente en `director`, el as-built lleva la evidencia: los tests agregados y el resultado de las
  corridas.
- Los comandos `director ...` se corren en este repo.
