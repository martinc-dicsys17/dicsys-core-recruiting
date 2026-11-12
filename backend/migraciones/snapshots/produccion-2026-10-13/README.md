# Esquema de producción del 2026-10-13

Foto de la estructura de la base de producción (`core.dicsys.ai`, con `main` en 25d87f2) para probar la cadena de
Alembic contra la base real sin tocarla: la adopción de una base de antes de Alembic (`0002`), `upgrade head` y
`alembic check` (F04-P03, F04-P09; ver `docs/Migraciones.md`).

- `esquema.sql`: solo la estructura (`pg_dump --schema-only --no-owner --no-privileges`). Ninguna fila.
- `core_schema_migrations.sql`: las filas de `core_schema_migrations`, las migraciones ad hoc que ya corrieron en
  producción. La adopción las revisa. No tienen datos personales.

Se sacaron así, en la VM:

```bash
docker exec postgresql sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema-only --no-owner --no-privileges' > esquema.sql
docker exec postgresql sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --data-only --no-owner --no-privileges --table=core_schema_migrations' > core_schema_migrations.sql
```

Para cargarlos en una base descartable hace falta `psql` 16.10 o más nuevo (entiende `\restrict`):

```bash
psql -d copia -f esquema.sql
psql -d copia -f core_schema_migrations.sql
```

Una foto nueva va en otra carpeta con su fecha; esta no se edita.
