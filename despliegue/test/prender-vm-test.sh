#!/usr/bin/env bash
#
# Prende la VM de test (dicsys-core-qa-vm, F23) y espera a que la app conteste. Apagada no cobra la máquina, solo el
# disco: se prende para probar y se apaga con apagar-vm-test.sh.
#
# La app vuelve sola: sus servicios del compose tienen restart: unless-stopped y Docker arranca con la VM. La QA no
# (su compose no tiene restart): su stack se rearma con su próximo deploy o con el de la app.
#
# Uso:
#   ./despliegue/test/prender-vm-test.sh
#   DRY_RUN=1 ./despliegue/test/prender-vm-test.sh
#
# Variables (todas con valor por defecto):
#   PROJECT_ID   dicsys-core-public
#   VM           dicsys-core-qa-vm
#   ZONE         us-central1-a
#   ESPERA       segundos máximos para que conteste /health (180)
#   ACCOUNT      cuenta de gcloud a usar (opcional)
#   DRY_RUN      1 para imprimir los comandos sin ejecutarlos

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-dicsys-core-public}"
VM="${VM:-dicsys-core-qa-vm}"
ZONE="${ZONE:-us-central1-a}"
ESPERA="${ESPERA:-180}"

GC=(gcloud)
[ -n "${ACCOUNT:-}" ] && GC+=("--account=$ACCOUNT")

run() {
  echo "+ $*"
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

# gcloud espera a que la operación termine: vuelve con la VM en RUNNING
run "${GC[@]}" compute instances start "$VM" --zone="$ZONE" --project="$PROJECT_ID" --quiet
[ "${DRY_RUN:-0}" = "1" ] && exit 0

# /health del frontend, desde adentro de la VM (el mismo que mira el proxy). El comando remoto siempre sale bien y
# dice qué pasó: así un /health que no contesta no se confunde con un SSH que no entró.
echo "Esperando que la app conteste /health (hasta ${ESPERA}s)..."
RESPUESTA="$("${GC[@]}" compute ssh "$VM" --zone="$ZONE" --project="$PROJECT_ID" --tunnel-through-iap --command \
  "for i in \$(seq 1 $((ESPERA / 5))); do curl -fs -o /dev/null http://localhost/health && { echo SANA; exit 0; }; sleep 5; done; echo SIN_RESPUESTA" \
  || true)"
case "$RESPUESTA" in
  *SANA*)          echo "✅ $VM prendida y la app contesta" ;;
  *SIN_RESPUESTA*) echo "⚠️  $VM prendida, pero la app no contesta /health: ¿todavía no tuvo su primer deploy?" ;;
  *)               echo "⚠️  $VM prendida, pero no se pudo entrar por SSH para mirar /health" ;;
esac
