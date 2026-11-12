#!/usr/bin/env bash
#
# Apaga la VM de test (dicsys-core-qa-vm, F23). Apagada no cobra la máquina, solo el disco; los datos (la base de test,
# los archivos y el .env) quedan en el disco. Se prende con prender-vm-test.sh.
#
# Con la VM apagada, un push a dev (app) o a main (QA) dispara igual el deploy de test, que falla porque no hay a dónde
# conectarse: se vuelve a correr después de prender, o se apaga DEPLOY_TEST mientras tanto.
#
# Uso:
#   ./despliegue/test/apagar-vm-test.sh
#   DRY_RUN=1 ./despliegue/test/apagar-vm-test.sh
#
# Variables (todas con valor por defecto):
#   PROJECT_ID   dicsys-core-public
#   VM           dicsys-core-qa-vm
#   ZONE         us-central1-a
#   ACCOUNT      cuenta de gcloud a usar (opcional)
#   DRY_RUN      1 para imprimir los comandos sin ejecutarlos

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-dicsys-core-public}"
VM="${VM:-dicsys-core-qa-vm}"
ZONE="${ZONE:-us-central1-a}"

GC=(gcloud)
[ -n "${ACCOUNT:-}" ] && GC+=("--account=$ACCOUNT")

run() {
  echo "+ $*"
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

# El apagado es ordenado: Docker frena los contenedores (Postgres incluido) antes de que se apague la máquina.
# gcloud espera a que la operación termine: vuelve con la VM en TERMINATED.
run "${GC[@]}" compute instances stop "$VM" --zone="$ZONE" --project="$PROJECT_ID" --quiet
[ "${DRY_RUN:-0}" = "1" ] && exit 0

echo "✅ $VM: $("${GC[@]}" compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID" --format='value(status)')"
