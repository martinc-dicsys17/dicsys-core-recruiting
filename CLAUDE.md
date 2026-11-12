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

## QA: cada cambio inyecta sus tests en la tool de QA

Regla del proyecto (decisión D-26 en `director`):

- **Todo cambio** (pendiente de construcción, fix, refactor, migración) **inyecta sus casos de prueba en la
  tool de QA**, el repo `innovacion-qa-engine`. No se da por terminado sin esos casos, la matriz regenerada y
  una corrida verde.
- **QA cubre solo lo que cambiamos**: los casos son para las operaciones de API y las rutas que el cambio
  toca. No hay meta de cobertura global ni backlog por módulo; lo que nadie toca entra a QA el día que un
  cambio lo toque.
- Los casos de QA **no se escriben en este repo**. `backend/tests` y `frontend/tests` son los tests propios de
  los devs (unitarios e integración) y siguen acá; no reemplazan a los casos de QA.
- Al cerrar el pendiente en `director`, el as-built lleva los ids de los casos (`BE-...`, `FE-...`) y la
  evidencia, la corrida de `qa run`.

## QA engine (`innovacion-qa-engine`)

- Dónde: `D:/Repos/innovacion-qa-engine`, clonado al lado de este repo. Encuentra la app con `QA_APP_ROOT`
  o, sin la variable, en la carpeta hermana `ops-sistema-gestion`, y prueba la rama que esté en ese checkout.
- Qué tiene: casos en caja negra (`backend/<modulo>/` con pytest + httpx, `frontend/<modulo>/` con
  Playwright), CLI `qa` (motor único en local, en la consola y en CI), consola web en `:7000`, MCP `qa`,
  seed determinista y stack de QA (frontend 8090, backend 6011, postgres 6010) armado con las imágenes de
  producción de esta app.
- Cómo se inyecta un caso: desde ese repo, con la skill `qa-casos` (vive ahí) o directamente:

  ```bash
  qa impacto --desde main                             # qué operaciones y rutas toca el cambio y qué casos las cubren
  qa caso faltantes --desde main                      # las tocadas sin caso: cada una necesita uno
  qa caso nuevo --lado BE --modulo <modulo> --titulo "..." --endpoint "POST /api/v1/..." --origen <pendiente> --autor "<quién>"
  qa run --suite all --seed --gate                    # corrida completa contra esta app
  ```

  Nunca a mano: `qa caso nuevo` acuña el id, escribe el caso y su esqueleto y valida contra el inventario.
- Lo que toca un cambio lo dice `qa impacto`, no el criterio de quien cierra: `qa impacto --desde main --gate`
  en verde es condición para cerrar el pendiente.
- El gate de la matriz falla si aparece una operación o ruta nueva sin caso o si alguna deja de estar
  cubierta. La corrida además falla por señales de la app (5xx, tracebacks, errores de JS) y por fallas nuevas
  del recorrido del frontend o del contrato de la API; los bugs que encuentra se registran como pendientes
  globales (PG-NN) antes de permitirlos en la política de QA.
- Los comandos `director ...` se corren en este repo; los `qa ...`, en el de QA.
