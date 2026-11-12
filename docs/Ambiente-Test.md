# Ambiente de test

El ambiente de test oficial (D-101 en director, fase F23) es una VM aparte de producción. Producción sigue en la rama
`main`, en su VM, sin cambios. La VM de test corre dos cosas:

- **Dicsys Core**: la rama `dev`, con todos sus servicios (postgresql, migraciones, backend, scheduler, frontend),
  contra una **copia de la base de producción** y con un **`.env` de prueba sin credenciales productivas**.
- **La QA** (`innovacion-qa-engine`): su stack sembrado y la consola, armados desde el mismo checkout de la app. Prueba
  lo desplegado con su propia base, sin tocar la copia (en el repo de QA, `despliegue/README.md`).

## Los bordes: nada sale hacia afuera

La base de test tiene gente real. Por eso los **bordes**, todo lo que habla con un servicio externo, quedan sin
credencial: Webex (el bot y la cuenta lectora), SendGrid, Odoo, el ingreso con Google, Google Sheets, Gemini, el
proveedor OpenID Connect y el bucket de producción. Lo arma `despliegue/test/env.test.template`, marcando cada uno
`BORDE`.

La copia trae además algunas credenciales guardadas en la base: el token OAuth de la cuenta lectora de Webex, las
sesiones del navegador y las tareas programadas activas. `despliegue/test/sanear-copia.sql` las saca o las apaga.

**Cada borde se prueba con una prueba puntual y controlada**: se pone una credencial de prueba para esa prueba (un
room de Webex de test, un destinatario propio, un cliente OAuth con la URL de vuelta de test), se prueba y se saca.

## Lo que hace infra (F23-P05)

Todo lo de esta sección, salvo el router del proxy, lo hace
[`despliegue/test/crear-vm-test.sh`](../despliegue/test/crear-vm-test.sh) (primero con `DRY_RUN=1`). Lo corre quien
tenga permisos en `dicsys-core-public`.

- La VM `dicsys-core-qa-vm` en el proyecto de producción, `dicsys-core-public`, en `subnet-core` con la IP interna
  `10.20.0.3` y las mismas network tags que `dicsys-core-vm`: no hace falta rango ni firewall nuevos. `e2-standard-4`
  con 50 GB, dimensionada para Dicsys Core y la QA (dos juegos de imágenes de la app, más el runner y la consola de QA
  con Playwright). Se prende para probar y se apaga después:
  [`despliegue/test/prender-vm-test.sh`](../despliegue/test/prender-vm-test.sh) (espera a que la app conteste
  `/health`; la app vuelve sola, la QA con su próximo deploy) y
  [`despliegue/test/apagar-vm-test.sh`](../despliegue/test/apagar-vm-test.sh). Apagada cobra solo el disco, y un push a
  `dev` o al `main` de la QA hace fallar su deploy de test.
- Su service account, `vm-core-qa@`, con `roles/storage.objectAdmin` sobre el **bucket de test**
  `dicsys-core-public-qa` (no el de producción) y `roles/iam.serviceAccountTokenCreator` sobre sí misma, para firmar
  URLs por IAM (F06-P04). Así se verifica en test lo de F06-P03.
- El nombre de test es `core-qa.services.dicsys.ai`. Ya resuelve al proxy por el comodín `*.services.dicsys.ai`, así
  que no hay que pedir nada en GoDaddy: falta el router del proxy hacia el frontend de la VM de test (puerto 80), y
  con eso Let's Encrypt emite el certificado.
- SSH por IAP, y la service account de deploy por Workload Identity de los dos repos (app y QA) con acceso a la VM.

## Preparar la VM (una vez)

1. En GitHub, en los dos repos, el environment `test` con `GCP_PROJECT`, `GCP_PROJECT_NUMBER`, `GCP_SERVICE_ACCOUNT`,
   `VM_NAME`, `VM_ZONE` y las carpetas. En la app van `PROJECT_DIR` y `QA_DIR`; en QA, `QA_DIR` y `APP_DIR`. No hace
   falta token: cada workflow clona con el `github.token` del job. Lo hace
   [`despliegue/test/github-environment-test.sh`](../despliegue/test/github-environment-test.sh).
2. En la VM, [`despliegue/test/preparar-vm-test.sh`](../despliegue/test/preparar-vm-test.sh) deja en `PROJECT_DIR`:
   - el checkout vacío, que el primer deploy completa;
   - el `.env`, armado desde `despliegue/test/env.test.template`, con los secretos `PROPIO` aleatorios generados en
     la VM (no se muestran) y los emails de recibos en `RECIBOS_EMAILS`;
   - `secrets/oidc` y `secrets/sheets-lectura.json` vacíos: el compose los monta, y en test van vacíos;
   - lo que necesita el usuario con el que entra el deploy (la cuenta `github-deploy@` por OS Login, `sa_<uniqueId>`):
     dueño del checkout y de la carpeta vacía de la QA en `QA_DIR`, y en el grupo `docker`, porque los dos
     `desplegar.sh` llaman a docker sin sudo.
3. Prender los deploys de test: `PRENDER=1 despliegue/test/github-environment-test.sh` deja la variable de repo
   `DEPLOY_TEST=true` en los dos repos.
4. El primer deploy de la app (el push a `dev`, ver «Deploy») y **después** el de la QA (desde su repo), que deja su
   checkout en `QA_DIR`. En ese orden: el deploy de la QA necesita el checkout de la app.

## La copia de la base (F23-P01, el usuario)

Toca producción: la hace el usuario o se hace con su sí explícito. Va después del primer deploy de la app, y la hace
entera [`despliegue/test/copiar-base-produccion.sh`](../despliegue/test/copiar-base-produccion.sh)
(`DRY_RUN=1` para ver los pasos, `CONFIRMAR=1` para correrlo). El dump pasa por la máquina de quien lo corre y se borra
de los tres lugares al terminar. Lo que hace:

1. `pg_dump` de producción (formato custom) y llevarlo a la VM de test.
2. En la VM de test, con la app bajada y solo Postgres arriba, recrear `dicsys_core` vacía y restaurar el dump (sin
   las tablas que el primer deploy creó con las migraciones).
3. Adoptarla para Alembic, si producción todavía es de antes de F04
   ([Migraciones.md, adopción](Migraciones.md)): `docker compose -f docker-compose.yml run --rm migraciones alembic stamp 0001`
   y después `docker compose -f docker-compose.yml run --rm migraciones`.
4. Sanear:
   `docker compose -f docker-compose.yml exec -T postgresql psql -U postgres -d dicsys_core < despliegue/test/sanear-copia.sql`.
   El resumen del final tiene que dar 0 en los tres.

5. Levantar la app.

Para refrescar la copia más adelante se corre de nuevo el script: pisa la base de test entera.

## Deploy

- **App**: `.github/workflows/deploy-test.yml`, en cada push a `dev`: lo que se mergea a `dev` queda en test. GitHub
  ofrece el disparo a mano solo cuando el workflow está en la rama por defecto (`main`, que no se toca), así que
  mientras tanto el camino es el push a `dev`. Corre el mismo `despliegue/desplegar.sh` que producción: build,
  migraciones antes del `up`, espera a que backend, scheduler y frontend estén sanos y, al final, rearma la QA con el
  checkout nuevo.
- **QA**: el `deploy-test.yml` de su repo, en cada push a su `main`.

## Probar

- La app, en la URL de test. Primero el humo de F06-P10: login con 2FA, cambio de empresa, permisos con un usuario
  restringido, carga y descarga de recibos y un ticket de soporte. Después las pruebas del usuario (F23-P03).
- El scheduler: `docker logs scheduler` muestra las tareas; reiniciar el backend no arranca ninguna.
- GCS sin JSON: subir y bajar un recibo (la URL firmada sale por IAM).
- La QA, por el túnel: `gcloud compute ssh <VM> --tunnel-through-iap -- -N -L 7000:localhost:7000` y
  `http://localhost:7000`.
