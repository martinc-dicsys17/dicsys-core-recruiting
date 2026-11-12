# Migraciones del esquema (Alembic)

Desde F04 el esquema de la base lo versiona Alembic. Este documento es el runbook: cómo se crea y se aplica una
revisión, cómo se cambia el esquema sin cortar el servicio, qué hacer con una base de antes de Alembic y cómo se
vuelve atrás.

## Cómo funciona

- Las revisiones viven en `backend/migraciones/versions` y van numeradas en orden: `0001_baseline.py`,
  `0002_adopcion_de_las_bases_anteriores.py`, `0003_secretos_de_usuario_a_hash.py`... La configuración está en
  `backend/alembic.ini` y `backend/migraciones/env.py`.
- El esquema esperado es `Base.metadata` con todos los modelos, que importa `backend/models_registry.py`. Un archivo
  de modelos nuevo (`models.py` o `*_models.py`) se agrega ahí. Si falta, `test_migraciones.py` falla.
- **El backend no toca el esquema.** Cada `docker compose up` corre primero el servicio `migraciones`
  (`alembic upgrade head`, con la imagen del backend) y recién cuando termina bien arranca el backend. Si la migración
  falla, el backend no arranca. En un release la migración va como paso propio, antes del `up` (ver [Release](#release)).
- La base es la de la app (`DATABASE_URL`). En la imagen, `ALEMBIC_CONFIG` apunta a `backend/alembic.ini`, así que
  `alembic <comando>` anda tal cual dentro del contenedor.
- Los tests de los devs crean el esquema con `create_all`, que es más rápido. `backend/tests/integration/test_migraciones.py`
  prueba aparte la cadena de migraciones sobre bases nuevas:
  - upgrade desde cero;
  - `alembic check`;
  - downgrade y vuelta;
  - adopción de una base de antes de Alembic;
  - una sola cabeza.

## Crear una revisión

Todo cambio de modelos lleva su revisión, en el mismo commit.

1. Cambiar los modelos.
2. Generar la revisión contra la base de desarrollo, que tiene que estar en `head`:

   ```bash
   docker compose run --rm migraciones alembic revision --autogenerate -m "descripcion del cambio"
   ```

   El override monta `./backend` con escritura, así que el archivo queda en `backend/migraciones/versions` con el
   número siguiente. Si los modelos y la base ya coinciden, no se crea nada.
3. **Leer la revisión antes de aplicarla.** Autogenerate compara tablas, columnas, tipos, nulabilidad, índices,
   unique y foreign keys, pero:
   - no ve los cambios en un `CheckConstraint`, en un `server_default` ni en una columna `Computed`: se escriben a mano;
   - un rename de tabla o de columna lo genera como borrar y crear, y eso pierde los datos. Se reemplaza por
     `op.rename_table` / `op.alter_column(..., new_column_name=...)`;
   - las foreign keys entre tablas que se referencian en ciclo hay que crearlas después de las tablas. Por ejemplo,
     `nomina_departamentos.manager_id` va con `use_alter`.
4. Aplicarla y verificar:

   ```bash
   docker compose run --rm migraciones                       # alembic upgrade head
   docker compose run --rm migraciones alembic check         # "No new upgrade operations detected."
   docker compose -f docker-compose.test.yml run --build --rm backend-tests \
     pytest backend/tests/integration/test_migraciones.py -q -o cache_dir=/tmp/pytest_cache
   ```

**Revisiones de datos.** Se escriben con SQL sobre `op.get_bind()`, sin importar modelos ORM: los modelos cambian con
el tiempo y la revisión tiene que seguir corriendo igual que el día que se escribió. Funciones puras de la app se
pueden usar, como `0003` con `backend.modules.usuarios.secretos`, sabiendo que la revisión queda atada a ellas.

**Ramas en paralelo.** Si dos ramas crean la misma revisión (dos `0005`), la que se integra segunda la renumera:
cambia `revision` y `down_revision` y el nombre del archivo. `test_migraciones.py` falla mientras haya dos cabezas o
números salteados.

## Release

`up` recrea el backend con la imagen nueva **antes** de correr `migraciones`. Si la migración falla en ese momento, el
backend queda abajo. Por eso un release migra primero, con `run`, que no toca el backend que está corriendo:

```bash
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml run --rm migraciones     # si falla, se corta acá y no cambió nada
docker compose -f docker-compose.yml up -d --remove-orphans   # migraciones ya está en head y no hace nada
```

En desarrollo alcanza con `docker compose up`.

## Cambios sin cortar el servicio (expand/contract)

Durante un deploy el código viejo y la base nueva conviven unos segundos. Si hay que volver atrás, conviven todo lo
que dure el rollback. Por eso un cambio que rompe compatibilidad se reparte en dos releases:

1. **Expand.** La revisión solo agrega: tablas, columnas que admiten NULL o tienen default, índices. El código nuevo
   escribe en lo viejo y en lo nuevo, o lee de lo nuevo con respaldo en lo viejo. Si hace falta completar datos, va
   en una revisión de datos o en un proceso aparte, en tandas si la tabla es grande.
2. **Contract.** En un release posterior, cuando ningún código en producción usa lo viejo, otra revisión borra
   columnas, pone `NOT NULL` o renombra.

Reglas:

- Nunca borrar ni renombrar algo en el mismo release en el que el código deja de usarlo.
- Un índice sobre una tabla grande se crea con `CREATE INDEX CONCURRENTLY` dentro de
  `with op.get_context().autocommit_block():`, porque no puede correr en una transacción.
- Un `NOT NULL` sobre una tabla grande se puede poner sin bloquearla mucho: primero un `CHECK (col IS NOT NULL) NOT VALID`,
  después `VALIDATE CONSTRAINT` y recién ahí el `SET NOT NULL`.
- Postgres hace el DDL en la transacción: si una revisión falla a la mitad, toda la corrida de `upgrade` se revierte
  y la base queda como estaba.

## Revisiones que no se pueden revertir

Una revisión que pierde información (borra columnas con datos, convierte a hash, unifica registros) no tiene un
`downgrade` real. Su `downgrade` lo dice en el docstring y no hace nada, como `0002` y `0003`, o levanta un error si
volver atrás dejaría la base inconsistente. Antes de aplicar una así en producción tiene que haber un backup
verificado (ver [Volver atrás](#volver-atrás)).

## Adopción de una base de antes de Alembic

Antes de F04 el backend armaba el esquema al arrancar: `create_all` y migraciones ad hoc anotadas en
`core_schema_migrations`. Una base de esa época no tiene la tabla `alembic_version`. Si le corre `upgrade head`, la
baseline se corta sin tocar nada, con un mensaje que manda acá. Se adopta **una sola vez por base**: producción, cada
base de desarrollo y cualquier backup de antes de F04 que se restaure.

1. Precondición: la base corrió la última versión sin Alembic, así que aplicó todas sus migraciones ad hoc.
   Producción ya la corre. Si falta alguna, la revisión `0002` lo detecta y corta: levantar una vez el backend de esa
   versión y repetir desde el paso 3.
2. En producción, backup verificado antes de seguir (ver [Volver atrás](#volver-atrás)).
3. Marcar la baseline como aplicada, sin ejecutarla, porque el esquema ya existe:

   ```bash
   docker compose run --rm migraciones alembic stamp 0001
   ```

   En producción va con `-f docker-compose.yml` en todos los comandos.
4. Llevarla a `head`:

   ```bash
   docker compose run --rm migraciones
   ```

   - `0002` controla las migraciones ad hoc y alinea lo que `create_all` nunca cambió en las bases existentes:
     - la unicidad del número de ticket y de pedido pasa a ser por empresa;
     - la PK y las FK de `innovacion_licencias` toman su nombre actual;
     - se borran los defaults de servidor de los ALTER ad hoc;
     - se borra `core_schema_migrations`.
   - `0003` pasa a hash los códigos de respaldo del 2FA y los magic links que estuvieran en claro.
   - `0004` crea lo de OpenID Connect (F21) y `core_usuarios.email_secundario` (F22) si no están. Al agregar la
     columna copia el email de cada cuenta a sus fichas, como la migración ad hoc `usuarios_email_secundario_v1` de
     `main`. Una base que ya tenía F21 y F22 queda como estaba.
5. Verificar y arrancar:

   ```bash
   docker compose run --rm migraciones alembic check          # "No new upgrade operations detected."
   docker compose up -d
   ```

`alembic check` no ve los `CHECK`, los defaults de servidor ni los nombres de las constraints. Para comparar eso en
una base que se adopta por primera vez (en producción, F04-P03), se crea al lado una base nueva con `upgrade head` y
se comparan las dos con la misma consulta:

```bash
docker compose exec postgresql createdb -U "$POSTGRES_USER" referencia
docker compose run --rm -e DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgresql:5432/referencia" migraciones
for base in "$POSTGRES_DB" referencia; do
  docker compose exec -T postgresql psql -U "$POSTGRES_USER" -d "$base" -At -c "
    SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint
    WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2;
    SELECT table_name, column_name, column_default FROM information_schema.columns
    WHERE table_schema = 'public' AND column_default IS NOT NULL ORDER BY 1, 2;" > "esquema_$base.txt"
done
diff "esquema_$POSTGRES_DB.txt" esquema_referencia.txt
docker compose exec postgresql dropdb -U "$POSTGRES_USER" referencia
```

La tabla va como texto: ordenada por `regclass` sale por OID, que cambia con el orden en que se crearon las tablas, y
el diff se llena de líneas iguales en otro orden. Una diferencia que no sea de forma se corrige con una revisión nueva
antes de dar la adopción por terminada.

Para probar la adopción de producción sin tocarla hay fotos de su esquema, con fecha, en
`backend/migraciones/snapshots/` (estructura y filas de `core_schema_migrations`, sin datos; cada carpeta tiene su
README).

## Volver atrás

**Si `upgrade` falla**, no hay nada que deshacer: la corrida se revierte entera. Con el orden del [release](#release),
el backend anterior sigue corriendo. Se corrige la revisión y se vuelve a desplegar.

**Si la migración terminó pero algo quedó mal**, en este orden:

1. Corregir hacia adelante, con una revisión nueva que arregle el esquema o los datos. Es lo más seguro y lo normal.
2. `alembic downgrade <revisión anterior>`, solo si la revisión es reversible y no perdió datos. Después se despliega
   la versión anterior del código.
3. Restaurar el backup previo a la migración. Se pierde lo que se escribió después.

Backup antes de una migración riesgosa, y restauración:

```bash
# Backup (formato custom, para pg_restore)
docker compose -f docker-compose.yml exec -T postgresql \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "backup_$(date +%F_%H%M).dump"

# Restauración: sin backend ni frontend escribiendo
docker compose -f docker-compose.yml stop frontend backend
docker compose -f docker-compose.yml exec -T postgresql dropdb -U "$POSTGRES_USER" --force "$POSTGRES_DB"
docker compose -f docker-compose.yml exec -T postgresql createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose -f docker-compose.yml exec -T postgresql \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner < backup_AAAA-MM-DD_HHMM.dump
# desplegar la versión del código que corresponde al backup
```

El backup trae su `alembic_version`. Si es de antes de F04, no la tiene y se adopta como se explica más arriba.
Falta definir el backup periódico de la VM y ensayar el restore (F04-P08).

## Referencia

| Para | Comando (en el contenedor `migraciones`) |
|------|-------------------------------------------|
| Llevar la base a la última revisión | `alembic upgrade head` (el comando por defecto del servicio) |
| Ver en qué revisión está la base | `alembic current` |
| Ver la cadena de revisiones | `alembic history` |
| Comprobar que modelos y migraciones coinciden | `alembic check` |
| Nueva revisión desde los modelos | `alembic revision --autogenerate -m "..."` |
| Nueva revisión vacía (datos o SQL a mano) | `alembic revision -m "..."` |
| Volver una revisión | `alembic downgrade -1` |
| Marcar una revisión sin ejecutarla | `alembic stamp <revisión>` |

Desde el host, sin Docker: `uv run --project backend alembic -c backend/alembic.ini <comando>` con `DATABASE_URL`
apuntando a la base (en desarrollo, `localhost:6000`).
