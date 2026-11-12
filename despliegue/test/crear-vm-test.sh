#!/usr/bin/env bash
#
# VM del ambiente de test de Dicsys Core (F23-P05, D-101, docs/Ambiente-Test.md).
#
# Variante de 03 - Plantillas/gcp/alta-servicio-gcp.sh de machete-v9. Cambia:
#   - El proyecto es el de producción, dicsys-core-public (decisión del usuario,
#     2026-10-23), que ya existe, ya está en la Shared VPC y ya tiene los permisos
#     del deploy de GitHub: no se crea proyecto, ni se asocia, ni se dan esos roles.
#   - La VM va en subnet-core, la subred de producción, con otra IP interna: no
#     hace falta un rango nuevo en el registro de traefik ni reglas de firewall
#     nuevas. Lleva las mismas network tags que dicsys-core-vm, así que el proxy
#     le llega igual que a producción.
#   - Suma lo que pide el runbook de test: un bucket de test con objectAdmin para
#     la cuenta de la VM, y que esa cuenta pueda firmar URLs por IAM (F06-P04).
#   - Las etiquetas salen de las de dicsys-core-vm, con entorno=staging; como hoy no
#     tiene ninguna, van servicio=core y repo=ops-sistema-gestion.
#
# Se puede correr de nuevo: lo que ya existe se saltea.
#
# Uso, primero en seco:
#   DRY_RUN=1 ./despliegue/test/crear-vm-test.sh
#   ./despliegue/test/crear-vm-test.sh
#
# Variables (todas con valor por defecto):
#   PROJECT_ID   dicsys-core-public
#   VM           dicsys-core-qa-vm
#   PROD_VM      dicsys-core-vm (de donde salen las tags y las etiquetas)
#   INTERNAL_IP  10.20.0.3, en subnet-core (libre, confirmado por el usuario)
#   MACHINE      e2-standard-4: Core y la QA con Playwright en la misma VM
#   DISK_GB      50: dos juegos de imágenes de la app más las de la QA
#   BUCKET       dicsys-core-public-qa
#   ACCOUNT      cuenta de gcloud a usar (opcional)
#   DRY_RUN      1 para imprimir los comandos sin ejecutarlos
#
# La VM se prende y se apaga a mano; apagada no cobra la máquina, solo el disco:
#   gcloud compute instances stop  dicsys-core-qa-vm --zone=us-central1-a --project=dicsys-core-public
#   gcloud compute instances start dicsys-core-qa-vm --zone=us-central1-a --project=dicsys-core-public

set -euo pipefail
# Sin MSYS_NO_PATHCONV: en Git Bash, gcloud necesita que se conviertan las rutas (la suya y el startup script temporal).

PROJECT_ID="${PROJECT_ID:-dicsys-core-public}"
VM="${VM:-dicsys-core-qa-vm}"
PROD_VM="${PROD_VM:-dicsys-core-vm}"
INTERNAL_IP="${INTERNAL_IP:-10.20.0.3}"
MACHINE="${MACHINE:-e2-standard-4}"
DISK_GB="${DISK_GB:-50}"
DISK_TYPE="${DISK_TYPE:-pd-balanced}"
IMAGE_FAMILY="${IMAGE_FAMILY:-debian-13}"
IMAGE_PROJECT="${IMAGE_PROJECT:-debian-cloud}"
BUCKET="${BUCKET:-dicsys-core-public-qa}"
REGION="${REGION:-us-central1}"
ZONE="${ZONE:-us-central1-a}"
HOST_PROJECT="${HOST_PROJECT:-dicsys-www-public-489718}"
SUBNET="${SUBNET:-subnet-core}"
VM_SA="vm-core-qa@$PROJECT_ID.iam.gserviceaccount.com"
DIRECCION="$VM-ip"

GC=(gcloud)
[ -n "${ACCOUNT:-}" ] && GC+=("--account=$ACCOUNT")

run() {
  echo "+ $*"
  if [ "${DRY_RUN:-0}" != "1" ]; then "$@"; fi
}

# En seco se da todo por inexistente, para mostrar todos los comandos.
existe() {
  [ "${DRY_RUN:-0}" = "1" ] && return 1
  "$@" >/dev/null 2>&1
}

# Tags y etiquetas de producción: así el firewall trata igual a las dos VMs.
if [ "${DRY_RUN:-0}" = "1" ]; then
  TAGS="TAGS_DE_${PROD_VM}"
  LABELS="ETIQUETAS_DE_${PROD_VM},entorno=staging"
else
  TAGS="$("${GC[@]}" compute instances describe "$PROD_VM" --zone="$ZONE" \
    --project="$PROJECT_ID" --format='value(tags.items.list(separator=","))')"
  LABELS="$("${GC[@]}" compute instances describe "$PROD_VM" --zone="$ZONE" \
    --project="$PROJECT_ID" --format='value(labels)' \
    | tr ';' '\n' | grep -v '^entorno=' | grep -v '^$' | paste -sd ',' -)" || true
  # dicsys-core-vm no tiene etiquetas (2026-10-23): las de 02-GCP-04 que se conocen
  LABELS="${LABELS:-servicio=core,repo=ops-sistema-gestion},entorno=staging"
fi

echo "== VM de test de Dicsys Core"
echo "   proyecto    $PROJECT_ID"
echo "   instancia   $VM  ip interna $INTERNAL_IP ($SUBNET)  zona $ZONE"
echo "   maquina     $MACHINE, disco ${DISK_GB}GB $DISK_TYPE, $IMAGE_FAMILY, sin IP externa"
echo "   tags        $TAGS (las de $PROD_VM)"
echo "   etiquetas   $LABELS"
echo "   cuenta      $VM_SA"
echo "   bucket      gs://$BUCKET"
[ "${DRY_RUN:-0}" = "1" ] && echo "   MODO SECO: no se ejecuta nada"
echo

# 1. IP interna reservada en subnet-core, para que no la tome otra VM y el
#    router del proxy no cambie
if existe "${GC[@]}" compute addresses describe "$DIRECCION" --region="$REGION" --project="$PROJECT_ID"; then
  echo "+ la dirección $DIRECCION ya existía"
else
  run "${GC[@]}" compute addresses create "$DIRECCION" \
    --region="$REGION" --project="$PROJECT_ID" \
    --subnet="projects/$HOST_PROJECT/regions/$REGION/subnetworks/$SUBNET" \
    --addresses="$INTERNAL_IP" --quiet
fi

# 2. Cuenta de servicio propia de la VM (02-GCP-05): logs, métricas y metadatos
if existe "${GC[@]}" iam service-accounts describe "$VM_SA" --project="$PROJECT_ID"; then
  echo "+ la cuenta $VM_SA ya existía"
else
  run "${GC[@]}" iam service-accounts create vm-core-qa \
    --display-name="VM de test de Dicsys Core" --project="$PROJECT_ID" --quiet
fi
for ROLE in roles/logging.logWriter \
            roles/monitoring.metricWriter \
            roles/stackdriver.resourceMetadata.writer; do
  run "${GC[@]}" projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$VM_SA" --role="$ROLE" \
    --condition=None --quiet --format=none
done
# Firmar URLs de descarga por IAM sin clave JSON (F06-P04): la cuenta firma
# como sí misma.
run "${GC[@]}" iam service-accounts add-iam-policy-binding "$VM_SA" \
  --project="$PROJECT_ID" --member="serviceAccount:$VM_SA" \
  --role=roles/iam.serviceAccountTokenCreator --quiet --format=none

# 3. Bucket de test: nunca el de producción
if existe "${GC[@]}" storage buckets describe "gs://$BUCKET" --project="$PROJECT_ID"; then
  echo "+ el bucket gs://$BUCKET ya existía"
else
  run "${GC[@]}" storage buckets create "gs://$BUCKET" \
    --project="$PROJECT_ID" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention --quiet
fi
run "${GC[@]}" storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$VM_SA" --role=roles/storage.objectAdmin --quiet --format=none

# 4. VM sin IP externa, con Docker y el Ops Agent por startup script (el mismo
#    de la plantilla de machete)
if existe "${GC[@]}" compute instances describe "$VM" --zone="$ZONE" --project="$PROJECT_ID"; then
  echo "+ la VM $VM ya existía"
else
  STARTUP="$(mktemp)"
  cat > "$STARTUP" <<'STARTUP_SCRIPT'
#!/bin/bash
set -e
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi
# git para el checkout de desplegar.sh y openssl para los secretos del .env
# (preparar-vm-test.sh); la imagen de Debian no trae git
if ! command -v git >/dev/null 2>&1 || ! command -v openssl >/dev/null 2>&1; then
  apt-get update && apt-get install -y git openssl
fi
mkdir -p /dicsys
if ! systemctl list-unit-files | grep -q google-cloud-ops-agent; then
  curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
  bash add-google-cloud-ops-agent-repo.sh --also-install
  rm -f add-google-cloud-ops-agent-repo.sh
fi
if ! grep -qs docker_containers /etc/google-cloud-ops-agent/config.yaml; then
  mkdir -p /etc/google-cloud-ops-agent
  cat > /etc/google-cloud-ops-agent/config.yaml <<'OPS_CONFIG'
logging:
  receivers:
    docker_containers:
      type: files
      include_paths:
        - /var/lib/docker/containers/*/*-json.log
  processors:
    envoltorio_docker:
      type: parse_json
    contenido_app:
      type: parse_json
      field: log
  service:
    pipelines:
      docker:
        receivers: [docker_containers]
        processors: [envoltorio_docker, contenido_app]
OPS_CONFIG
  systemctl restart google-cloud-ops-agent
fi
STARTUP_SCRIPT
  run "${GC[@]}" compute instances create "$VM" \
    --project="$PROJECT_ID" --zone="$ZONE" --machine-type="$MACHINE" \
    --subnet="projects/$HOST_PROJECT/regions/$REGION/subnetworks/$SUBNET" \
    --private-network-ip="$INTERNAL_IP" --no-address \
    --image-family="$IMAGE_FAMILY" --image-project="$IMAGE_PROJECT" \
    --boot-disk-size="${DISK_GB}GB" --boot-disk-type="$DISK_TYPE" \
    --service-account="$VM_SA" --scopes=cloud-platform \
    --tags="$TAGS" --labels="$LABELS" \
    --metadata=enable-osconfig=TRUE,enable-oslogin=TRUE \
    --metadata-from-file=startup-script="$STARTUP" --quiet
  rm -f "$STARTUP"
fi
# El disco de arranque lleva las mismas etiquetas que la VM (02-GCP-04).
run "${GC[@]}" compute disks add-labels "$VM" --zone="$ZONE" \
  --project="$PROJECT_ID" --labels="$LABELS" --quiet

echo
echo "== Listo. Para traefik (hilo H-05): core-qa.services.dicsys.ai -> http://$INTERNAL_IP:80, /health"
echo "   En GitHub, environment test: VM_NAME=$VM, VM_ZONE=$ZONE, GCP_PROJECT=$PROJECT_ID"
echo "   En el .env de la VM: GCS_BUCKET_NAME=$BUCKET"
