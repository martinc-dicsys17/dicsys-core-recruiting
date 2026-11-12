#!/usr/bin/env bash
#
# Copia saneada de la base de producción a la VM de test (F23-P01, docs/Ambiente-Test.md, «La copia de la base»).
# TOCA PRODUCCIÓN, aunque solo para leer: la corre el usuario, con CONFIRMAR=1.
#
# Va después del primer deploy de test (la VM ya tiene el checkout, el .env y el stack). Pasos:
#   1. En producción: pg_dump (formato custom) dentro del contenedor de Postgres, a /tmp de la VM.
#   2. El dump pasa de producción a test por esta máquina (gcloud compute scp por IAP) y se borra de los tres lugares
#      al terminar. Tiene datos de personas: no se guarda en ningún otro lado.
#   3. En test: baja la app, recrea la base vacía, restaura, la adopta para Alembic si producción es de antes de F04
#      (stamp 0001 + upgrade head, docs/Migraciones.md), la sanea con sanear-copia.sql y levanta todo.
# Para refrescar la copia más adelante se corre de nuevo: pisa la base de test entera.
#
# Uso, primero en seco:
#   DRY_RUN=1 ./despliegue/test/copiar-base-produccion.sh
#   CONFIRMAR=1 ./despliegue/test/copiar-base-produccion.sh
#
# Variables (todas con valor por defecto):
#   PROJECT_ID   dicsys-core-public (las dos VMs)
#   ZONE         us-central1-a
#   PROD_VM      dicsys-core-vm
#   PROD_DIR     /dicsys/ops-sistema-gestion (el PROJECT_DIR del environment PROD)
#   TEST_VM      dicsys-core-qa-vm
#   TEST_DIR     /dicsys/ops-sistema-gestion
#   ACCOUNT      cuenta de gcloud a usar (opcional)
#   CONFIRMAR    1 para correrlo de verdad
#   DRY_RUN      1 para imprimir los pasos sin ejecutarlos

set -euo pipefail
# Sin MSYS_NO_PATHCONV: en Git Bash, gcloud necesita que se conviertan las rutas (la suya y el archivo temporal del scp).
# Ningún argumento de acá empieza con / del lado de las VMs.

PROJECT_ID="${PROJECT_ID:-dicsys-core-public}"
ZONE="${ZONE:-us-central1-a}"
PROD_VM="${PROD_VM:-dicsys-core-vm}"
PROD_DIR="${PROD_DIR:-/dicsys/ops-sistema-gestion}"
TEST_VM="${TEST_VM:-dicsys-core-qa-vm}"
TEST_DIR="${TEST_DIR:-/dicsys/ops-sistema-gestion}"
DUMP=/tmp/copia-dicsys-core.dump

GC=(gcloud)
[ -n "${ACCOUNT:-}" ] && GC+=("--account=$ACCOUNT")
DONDE=(--project="$PROJECT_ID" --zone="$ZONE" --tunnel-through-iap)

if [ "${DRY_RUN:-0}" != "1" ] && [ "${CONFIRMAR:-0}" != "1" ]; then
  echo "Esto lee la base de producción ($PROD_VM) y pisa la de test ($TEST_VM)."
  echo "Para correrlo: CONFIRMAR=1 $0 (o DRY_RUN=1 para ver los pasos)."
  exit 1
fi

run() {
  echo "+ $*"
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

LOCAL="$(mktemp)"
limpiar() {
  rm -f "$LOCAL"
  if [ "${DRY_RUN:-0}" != "1" ]; then
    "${GC[@]}" compute ssh "$PROD_VM" "${DONDE[@]}" --command "rm -f $DUMP" >/dev/null 2>&1 || true
    "${GC[@]}" compute ssh "$TEST_VM" "${DONDE[@]}" --command "rm -f $DUMP" >/dev/null 2>&1 || true
  fi
}
trap limpiar EXIT

echo "== Copia de $PROD_VM:$PROD_DIR a $TEST_VM:$TEST_DIR"
[ "${DRY_RUN:-0}" = "1" ] && echo "   MODO SECO: no se ejecuta nada"
echo

# 1. Dump en producción. Usuario y base salen del propio contenedor: no se lee el .env de producción.
run "${GC[@]}" compute ssh "$PROD_VM" "${DONDE[@]}" --command \
  "cd $PROD_DIR && umask 077 && sudo docker compose exec -T postgresql sh -c 'pg_dump -U \"\$POSTGRES_USER\" -Fc \"\$POSTGRES_DB\"' > $DUMP && ls -lh $DUMP"

# 2. De producción a test, por esta máquina
run "${GC[@]}" compute scp "$PROD_VM:$DUMP" "$LOCAL" "${DONDE[@]}"
run "${GC[@]}" compute scp "$LOCAL" "$TEST_VM:$DUMP" "${DONDE[@]}"

# 3. En test: restaurar, adoptar, sanear y levantar. Viaja como archivo, igual que en preparar-vm-test.sh.
EN_TEST="$(mktemp)"
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  printf 'TEST_DIR=%q\nDUMP=%q\n' "$TEST_DIR" "$DUMP"
  cat <<'EN_LA_VM'
cd "$TEST_DIR"
C=(sudo docker compose -f docker-compose.yml)
# Usuario y base salen del contenedor, como en producción
pg() { "${C[@]}" exec -T postgresql sh -c "$1"; }

"${C[@]}" stop backend scheduler frontend || true
"${C[@]}" up -d postgresql
until pg 'pg_isready -U "$POSTGRES_USER" -d postgres' >/dev/null 2>&1; do sleep 2; done

# Base vacía y la copia encima: sin las tablas que el primer deploy creó con las migraciones
pg 'dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
pg 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges' < "$DUMP"

# Producción todavía es de antes de F04 (sin alembic_version): se adopta desde la 0001 (docs/Migraciones.md)
# (\$\$...\$\$: comillas de dólar de Postgres, escapadas para el sh del contenedor)
SIN_ALEMBIC="$(pg 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT to_regclass(\$\$public.alembic_version\$\$) IS NULL"')"
if [ "$SIN_ALEMBIC" = "t" ]; then
  "${C[@]}" run --rm migraciones alembic stamp 0001
fi
"${C[@]}" run --rm migraciones

pg 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < despliegue/test/sanear-copia.sql
rm -f "$DUMP"
"${C[@]}" up -d
EN_LA_VM
} > "$EN_TEST"
trap 'limpiar; rm -f "$EN_TEST"' EXIT

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "+ ${GC[*]} compute scp $EN_TEST $TEST_VM:/tmp/copiar-base.sh ${DONDE[*]}"
  echo "+ ${GC[*]} compute ssh $TEST_VM ${DONDE[*]} --command 'bash /tmp/copiar-base.sh', que corre:"
  sed 's/^/    /' "$EN_TEST"
else
  "${GC[@]}" compute scp "$EN_TEST" "$TEST_VM:/tmp/copiar-base.sh" "${DONDE[@]}"
  "${GC[@]}" compute ssh "$TEST_VM" "${DONDE[@]}" \
    --command 'bash /tmp/copiar-base.sh; codigo=$?; rm -f /tmp/copiar-base.sh; exit $codigo'
fi

echo
echo "Listo. El resumen del saneo tiene que dar 0 en las tres filas (docs/Ambiente-Test.md)."
