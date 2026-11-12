#!/usr/bin/env bash
#
# Environment `test` de GitHub en los dos repos del ambiente de test (F23-P02, docs/Ambiente-Test.md): la app
# (.github/workflows/deploy-test.yml) y la QA (el deploy-test.yml de innovacion-qa-engine). Va después de
# crear-vm-test.sh: las variables apuntan a la VM que crea ese script.
#
# No hay secrets: cada workflow clona con el github.token del job. GCP_PROJECT_NUMBER y GCP_SERVICE_ACCOUNT son los
# de la federación del deploy de producción (el mismo github-deploy@) y se copian del environment de producción de la
# app.
#
# DEPLOY_TEST=true prende los dos deploys de test (cada push a dev en la app, a main en la QA). Por eso va aparte, con
# PRENDER=1, cuando la VM ya tiene su .env (preparar-vm-test.sh).
#
# Uso, primero en seco:
#   DRY_RUN=1 ./despliegue/test/github-environment-test.sh
#   ./despliegue/test/github-environment-test.sh
#   PRENDER=1 ./despliegue/test/github-environment-test.sh
#
# Variables (todas con valor por defecto):
#   APP_REPO      Dicsys-SA/ops-sistema-gestion
#   QA_REPO       Dicsys-SA/innovacion-qa-engine
#   GCP_PROJECT   dicsys-core-public
#   VM_NAME       dicsys-core-qa-vm
#   VM_ZONE       us-central1-a
#   APP_DIR       /dicsys/ops-sistema-gestion (checkout de la app en la VM)
#   QA_DIR        /dicsys/innovacion-qa-engine (checkout de la QA en la VM)
#   PROD_ENV      PROD (de donde salen GCP_PROJECT_NUMBER y GCP_SERVICE_ACCOUNT)
#   PRENDER       1 para dejar DEPLOY_TEST=true en los dos repos
#   DRY_RUN       1 para imprimir los comandos sin ejecutarlos

set -euo pipefail
# En Git Bash, un argumento que empieza con / se convierte en ruta de Windows al llamar a gh: sin esto, --body
# /dicsys/... quedaba como C:/Program Files/Git/dicsys/... (2026-10-23). En Linux no hace nada. Solo acá, que llama a gh:
# en los scripts que llaman a gcloud rompe gcloud, que necesita la conversión para encontrar sus propios archivos.
export MSYS_NO_PATHCONV=1

APP_REPO="${APP_REPO:-Dicsys-SA/ops-sistema-gestion}"
QA_REPO="${QA_REPO:-Dicsys-SA/innovacion-qa-engine}"
GCP_PROJECT="${GCP_PROJECT:-dicsys-core-public}"
VM_NAME="${VM_NAME:-dicsys-core-qa-vm}"
VM_ZONE="${VM_ZONE:-us-central1-a}"
APP_DIR="${APP_DIR:-/dicsys/ops-sistema-gestion}"
QA_DIR="${QA_DIR:-/dicsys/innovacion-qa-engine}"
PROD_ENV="${PROD_ENV:-PROD}"

run() {
  echo "+ $*"
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

de_produccion() {
  gh api "repos/$APP_REPO/environments/$PROD_ENV/variables/$1" --jq .value
}

if [ "${DRY_RUN:-0}" = "1" ]; then
  GCP_PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-NUMERO_DE_$PROD_ENV}"
  GCP_SERVICE_ACCOUNT="${GCP_SERVICE_ACCOUNT:-CUENTA_DE_$PROD_ENV}"
else
  GCP_PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-$(de_produccion GCP_PROJECT_NUMBER)}"
  GCP_SERVICE_ACCOUNT="${GCP_SERVICE_ACCOUNT:-$(de_produccion GCP_SERVICE_ACCOUNT)}"
fi

echo "== Environment test"
echo "   VM          $VM_NAME ($VM_ZONE, $GCP_PROJECT)"
echo "   federación  $GCP_SERVICE_ACCOUNT, proyecto $GCP_PROJECT_NUMBER (de $PROD_ENV)"
echo "   carpetas    app $APP_DIR · QA $QA_DIR"
[ "${DRY_RUN:-0}" = "1" ] && echo "   MODO SECO: no se ejecuta nada"
echo

variables() {
  local repo="$1"; shift
  run gh api -X PUT "repos/$repo/environments/test" --silent
  for par in "GCP_PROJECT=$GCP_PROJECT" "GCP_PROJECT_NUMBER=$GCP_PROJECT_NUMBER" \
             "GCP_SERVICE_ACCOUNT=$GCP_SERVICE_ACCOUNT" "VM_NAME=$VM_NAME" "VM_ZONE=$VM_ZONE" "$@"; do
    run gh variable set "${par%%=*}" --env test --body "${par#*=}" --repo "$repo"
  done
}

# La app pasa a desplegar.sh su checkout y el de la QA, que rearma al final
variables "$APP_REPO" "PROJECT_DIR=$APP_DIR" "QA_DIR=$QA_DIR"
# La QA prueba la app de test desde su propio checkout
variables "$QA_REPO" "QA_DIR=$QA_DIR" "APP_DIR=$APP_DIR"

if [ "${PRENDER:-0}" = "1" ]; then
  run gh variable set DEPLOY_TEST --body true --repo "$APP_REPO"
  run gh variable set DEPLOY_TEST --body true --repo "$QA_REPO"
else
  echo
  echo "DEPLOY_TEST sigue sin prender: con la VM lista, PRENDER=1 $0"
fi
