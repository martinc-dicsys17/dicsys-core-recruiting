#!/usr/bin/env bash
#
# Prepara la VM de test una vez (docs/Ambiente-Test.md, «Preparar la VM»), antes del primer deploy de la app. Corre
# desde la máquina de quien arma el ambiente y entra a la VM por IAP, como el deploy.
#
# En la VM deja:
#   - el checkout vacío de la app en APP_DIR (git init + origin): el primer deploy (desplegar.sh) lo encuentra, hace el
#     fetch con su token y el reset, y el .env y los secrets, que no están en el repo, quedan;
#   - el .env, armado desde despliegue/test/env.test.template. Los valores PROPIO aleatorios (SECRET_KEY,
#     JWT_SECRET_KEY, POSTGRES_PASSWORD) se generan en la VM y no se muestran ni pasan por esta máquina. Si el .env ya
#     existe no se toca (FORZAR=1 lo rehace, con secretos nuevos);
#   - secrets/oidc y secrets/sheets-lectura.json vacíos: el compose los monta y en test van vacíos;
#   - lo que el deploy necesita para el usuario con el que entra, el de la cuenta de servicio de GitHub por OS Login
#     (sa_<uniqueId>, no el de quien corre esto): dueño del checkout de la app y de la carpeta vacía de la QA, y en el
#     grupo docker, porque los dos desplegar.sh (app y QA) llaman a docker sin sudo. El primer deploy corre git antes de
#     su propio chown, y git no opera en un repo de otro dueño.
#
# Uso, primero en seco:
#   DRY_RUN=1 ./despliegue/test/preparar-vm-test.sh
#   RECIBOS_EMAILS="a@dicsys.ai,b@dicsys.ai" ./despliegue/test/preparar-vm-test.sh
#
# Variables (todas con valor por defecto):
#   PROJECT_ID      dicsys-core-public
#   VM              dicsys-core-qa-vm
#   ZONE            us-central1-a
#   APP_DIR         /dicsys/ops-sistema-gestion
#   QA_DIR          /dicsys/innovacion-qa-engine (la clona el deploy de la QA)
#   REPO_URL        https://github.com/Dicsys-SA/ops-sistema-gestion.git (sin token)
#   DEPLOY_SA       github-deploy@dicsys-www-public-489718.iam.gserviceaccount.com (la del environment test)
#   BUCKET          dicsys-core-public-qa (el de crear-vm-test.sh)
#   RECIBOS_EMAILS  quienes prueban recibos (RECIBOS_ADMIN_ALLOWED_EMAILS); vacío: nadie
#   FORZAR          1 para rehacer el .env
#   ACCOUNT         cuenta de gcloud a usar (opcional)
#   DRY_RUN         1 para mostrar lo que corre en la VM sin entrar

set -euo pipefail
# Sin MSYS_NO_PATHCONV: en Git Bash, gcloud necesita que se conviertan las rutas (la suya y el archivo temporal del scp).
# Ningún argumento de acá empieza con / del lado de la VM.

PROJECT_ID="${PROJECT_ID:-dicsys-core-public}"
VM="${VM:-dicsys-core-qa-vm}"
ZONE="${ZONE:-us-central1-a}"
APP_DIR="${APP_DIR:-/dicsys/ops-sistema-gestion}"
QA_DIR="${QA_DIR:-/dicsys/innovacion-qa-engine}"
REPO_URL="${REPO_URL:-https://github.com/Dicsys-SA/ops-sistema-gestion.git}"
DEPLOY_SA="${DEPLOY_SA:-github-deploy@dicsys-www-public-489718.iam.gserviceaccount.com}"
BUCKET="${BUCKET:-dicsys-core-public-qa}"
RECIBOS_EMAILS="${RECIBOS_EMAILS:-}"
FORZAR="${FORZAR:-0}"
PLANTILLA="$(dirname "$0")/env.test.template"

GC=(gcloud)
[ -n "${ACCOUNT:-}" ] && GC+=("--account=$ACCOUNT")
DONDE=(--project="$PROJECT_ID" --zone="$ZONE" --tunnel-through-iap)

# Con OS Login, una cuenta de servicio entra a la VM como sa_<uniqueId>
if [ "${DRY_RUN:-0}" = "1" ]; then
  DEPLOY_USER="sa_UNIQUEID_DE_${DEPLOY_SA%%@*}"
else
  DEPLOY_USER="sa_$("${GC[@]}" iam service-accounts describe "$DEPLOY_SA" --format='value(uniqueId)')"
fi

# Lo que corre en la VM. La plantilla viaja en base64 dentro del script; los valores de esta máquina van con %q.
REMOTO="$(mktemp)"
trap 'rm -f "$REMOTO"' EXIT
{
  echo '#!/usr/bin/env bash'
  echo 'set -euo pipefail'
  printf 'APP_DIR=%q\nQA_DIR=%q\nREPO_URL=%q\nDEPLOY_USER=%q\nBUCKET=%q\nRECIBOS_EMAILS=%q\nFORZAR=%q\n' \
    "$APP_DIR" "$QA_DIR" "$REPO_URL" "$DEPLOY_USER" "$BUCKET" "$RECIBOS_EMAILS" "$FORZAR"
  # Sin \r: una copia de Windows puede traer la plantilla en CRLF, y en la VM el sed no encontraría «CLAVE=» al final
  # de la línea
  printf 'PLANTILLA_B64=%q\n' "$(tr -d '\r' < "$PLANTILLA" | base64 -w0)"
  cat <<'EN_LA_VM'

# Todo con sudo: lo que queda en la VM es del usuario del deploy, no de quien corre esto
if ! getent passwd "$DEPLOY_USER" >/dev/null; then
  echo "❌ la VM no conoce a $DEPLOY_USER: ¿la cuenta de deploy tiene OS Login en el proyecto?"
  exit 1
fi

# Docker sin sudo para el deploy
if ! id -nG "$DEPLOY_USER" | tr ' ' '\n' | grep -qx docker; then
  sudo gpasswd -a "$DEPLOY_USER" docker >/dev/null
  echo "+ $DEPLOY_USER en el grupo docker"
fi

sudo mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Checkout vacío: el primer deploy hace el fetch y el reset sobre esto
if ! sudo test -d .git; then
  sudo git init -q
  sudo git remote add origin "$REPO_URL"
  echo "+ checkout vacío en $APP_DIR (origin $REPO_URL)"
fi

sudo mkdir -p secrets/oidc
sudo test -e secrets/sheets-lectura.json || sudo touch secrets/sheets-lectura.json

if sudo test -e .env && [ "$FORZAR" != "1" ]; then
  echo "+ el .env ya existía: no se toca (FORZAR=1 lo rehace)"
else
  # 600 desde antes de escribir los secretos
  sudo install -m 600 /dev/null .env.nuevo
  echo "$PLANTILLA_B64" | base64 -d | sudo tee .env.nuevo >/dev/null
  # Aleatorios, distintos de producción; se escriben directo en el archivo y no se muestran
  secreto() { openssl rand -hex 32; }
  CLAVE_POSTGRES="$(secreto)"
  sudo sed -i \
    -e "s|^SECRET_KEY=\$|SECRET_KEY=$(secreto)|" \
    -e "s|^JWT_SECRET_KEY=\$|JWT_SECRET_KEY=$(secreto)|" \
    -e "s|^POSTGRES_PASSWORD=\$|POSTGRES_PASSWORD=$CLAVE_POSTGRES|" \
    -e "s|<POSTGRES_PASSWORD>|$CLAVE_POSTGRES|" \
    -e "s|^GCS_BUCKET_NAME=\$|GCS_BUCKET_NAME=$BUCKET|" \
    -e "s|^RECIBOS_ADMIN_ALLOWED_EMAILS=\$|RECIBOS_ADMIN_ALLOWED_EMAILS=$RECIBOS_EMAILS|" \
    .env.nuevo
  unset CLAVE_POSTGRES
  sudo mv .env.nuevo .env
  echo "+ .env armado desde env.test.template"
fi

# Dueño: el usuario del deploy. La carpeta, .git y el .env alcanzan para que su primer git funcione; después
# desplegar.sh hace su propio chown. No se tocan data/ ni secrets/oidc, que el deploy deja del usuario 1000.
sudo chown "$DEPLOY_USER": "$APP_DIR" .env
sudo chown -R "$DEPLOY_USER": .git
# La carpeta de la QA, vacía y suya: el deploy de la QA clona ahí
if ! sudo test -d "$QA_DIR/.git"; then
  sudo mkdir -p "$QA_DIR"
  sudo chown "$DEPLOY_USER": "$QA_DIR"
fi
echo "+ checkout de la app y carpeta de la QA de $DEPLOY_USER"

# Resumen sin valores: qué quedó lleno
for clave in SECRET_KEY JWT_SECRET_KEY POSTGRES_PASSWORD GCS_BUCKET_NAME RECIBOS_ADMIN_ALLOWED_EMAILS FRONTEND_URL; do
  if [ -n "$(sudo grep "^$clave=" .env | cut -d= -f2-)" ]; then echo "  $clave: lleno"; else echo "  $clave: VACÍO"; fi
done
if sudo grep -q '<POSTGRES_PASSWORD>' .env; then echo "  ATENCIÓN: DATABASE_URL sigue con <POSTGRES_PASSWORD>"; exit 1; fi
echo "Listo: la VM espera el primer deploy de la app (push a dev con DEPLOY_TEST=true) y después el de la QA."
EN_LA_VM
} > "$REMOTO"

echo "== Preparar $VM ($PROJECT_ID) en $APP_DIR, bucket $BUCKET"
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "   MODO SECO: esto es lo que correría en la VM (sin la plantilla en base64):"
  echo
  grep -v '^PLANTILLA_B64=' "$REMOTO"
  echo
  echo "+ ${GC[*]} compute scp $REMOTO $VM:/tmp/preparar-vm-test.sh ${DONDE[*]}"
  echo "+ ${GC[*]} compute ssh $VM ${DONDE[*]} --command 'bash /tmp/preparar-vm-test.sh; rm -f /tmp/preparar-vm-test.sh'"
  exit 0
fi

"${GC[@]}" compute scp "$REMOTO" "$VM:/tmp/preparar-vm-test.sh" "${DONDE[@]}"
"${GC[@]}" compute ssh "$VM" "${DONDE[@]}" \
  --command 'bash /tmp/preparar-vm-test.sh; codigo=$?; rm -f /tmp/preparar-vm-test.sh; exit $codigo'
