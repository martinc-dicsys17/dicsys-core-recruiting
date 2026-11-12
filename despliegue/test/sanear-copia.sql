-- Saneo de la copia de producción en la base de test (D-101, docs/Ambiente-Test.md). Se corre una vez después de
-- restaurar la copia y de adoptarla para Alembic (las tablas nuevas ya existen), antes del primer `up`:
--
--   docker compose -f docker-compose.yml exec -T postgresql psql -U postgres -d dicsys_core < despliegue/test/sanear-copia.sql
--
-- El .env de prueba deja los bordes sin credenciales, pero la base trae algunas guardadas: esto las saca. Idempotente.

BEGIN;

-- Credencial viva: el token OAuth de la cuenta lectora de Webex (lee el room de presentaciones). Sin esto, test podría
-- leer Webex con la cuenta de producción aunque el .env no tenga el client secret.
DELETE FROM core_webex_oauth_tokens;

-- Sesiones del navegador de producción: cerradas en test (sus refresh no se usan acá, pero no tienen por qué valer).
UPDATE auth_refresh_tokens SET revocado_at = now() WHERE revocado_at IS NULL;

-- Tareas programadas apagadas ('0'): en test se prenden de a una, en una prueba puntual. También los activos de los
-- crons viejos, que el scheduler migra a tarea_*_activa la primera vez que arranca (backend/modules/tareas/parametros.py,
-- MIGRACIONES): una copia de una producción sin F19 los trae así. Las tareas continuas no tienen parámetro de activa.
UPDATE core_parametros SET valor = '0', updated_by = 'saneo-test'
 WHERE (key LIKE 'tarea\_%\_activa' ESCAPE '\' OR key IN ('notificaciones_cron_activo', 'sync_webex_cron_activo'))
   AND deleted_at IS NULL;

-- Rooms y destinos de Webex de producción: vacíos, así una prueba puntual elige uno de test a propósito.
UPDATE core_parametros SET valor = NULL, updated_by = 'saneo-test'
 WHERE key LIKE 'webex\_room\_%' ESCAPE '\' OR key IN ('alertas_webex_room_id', 'webex_general_room_id', 'webex_team_dicsys_id', 'webex_sync_espacios');

COMMIT;

-- Lo que queda, para revisar a mano
SELECT 'webex_oauth_tokens' AS que, count(*) FROM core_webex_oauth_tokens
UNION ALL SELECT 'refresh vigentes', count(*) FROM auth_refresh_tokens WHERE revocado_at IS NULL
UNION ALL SELECT 'tareas activas', count(*) FROM core_parametros
 WHERE (key LIKE 'tarea\_%\_activa' ESCAPE '\' OR key IN ('notificaciones_cron_activo', 'sync_webex_cron_activo'))
   AND deleted_at IS NULL AND lower(coalesce(valor, '')) IN ('1', 'true', 'si', 'sí');
