#!/usr/bin/env bash
# Deploy de Dicsys Core en una VM (F06-P05, D-101). Lo corren por IAP .github/workflows/deploy.yml (producción, rama
# main) y .github/workflows/deploy-test.yml (la VM de test, rama dev u otra a mano).
#
#   uso: desplegar.sh <carpeta del proyecto> <URL del repo, sin token> <rama> [carpeta de QA]
#
# El token de GitHub llega por stdin (una línea): no queda en la línea de comandos del ssh ni en .git/config. Cada git
# que va a GitHub lo recibe en un header por variables de entorno, que solo ve el propio proceso. Con la carpeta de QA
# (la VM de test corre Dicsys Core y la QA), al final rearma la QA contra el checkout nuevo: prueba lo desplegado.
set -euo pipefail

PROJECT_DIR=$(echo "$1" | tr -d '\r')
REPO_URL=$(echo "$2" | tr -d '\r')
RAMA=$(echo "$3" | tr -d '\r')
QA_DIR=$(echo "${4:-}" | tr -d '\r')

IFS= read -r CODE_TOKEN
ENCABEZADO="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$CODE_TOKEN" | base64 -w0)"
con_token() { GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader GIT_CONFIG_VALUE_0="$ENCABEZADO" "$@"; }

echo "PROJECT_DIR=[${PROJECT_DIR}] RAMA=[${RAMA}]"

if [ ! -d "$PROJECT_DIR" ]; then
  sudo mkdir -p "$(dirname "$PROJECT_DIR")"
  sudo chown "$(id -un):$(id -gn)" "$(dirname "$PROJECT_DIR")"
  con_token git clone "$REPO_URL" "$PROJECT_DIR"
fi

cd "$PROJECT_DIR"
# la URL del remote sin token: limpia la que dejaban en .git/config los deploys anteriores
git remote set-url origin "$REPO_URL"
con_token git fetch origin "$RAMA"
sudo chown -R "$(id -un):$(id -gn)" .
git reset --hard "origin/$RAMA"

sudo chown -R 1000:1000 data/
# La clave de firma OpenID Connect la lee el backend como el usuario 1000 (docs/OIDC.md) y el chown -R de
# arriba se la saca: sin esto, despues de cada deploy todo /oidc/* da 500
if [ -d secrets/oidc ]; then sudo chown -R 1000:1000 secrets/oidc; fi

# Solo el compose base: el checkout trae docker-compose.override.yml (desarrollo) y sin -f Compose lo carga
COMPOSE="docker compose -f docker-compose.yml"
$COMPOSE build --pull
# Migraciones antes de tocar lo que corre (F04, docs/Migraciones.md): `up` recrea el backend antes de migrar,
# así que si la migración falla acá el deploy corta y el backend que está corriendo sigue igual
$COMPOSE run --rm migraciones
$COMPOSE up -d --remove-orphans

# Esperar a que todo quede sano (healthcheck) antes de limpiar: si algo no levanta, el deploy falla y las
# imágenes anteriores siguen en la VM para volver atrás
for servicio in backend scheduler frontend; do
  for intento in $(seq 1 36); do
    estado=$(docker inspect -f '{{.State.Health.Status}}' "$servicio" 2>/dev/null || echo ausente)
    [ "$estado" = healthy ] && break
    [ "$intento" -eq 36 ] && { echo "❌ $servicio no quedó sano ($estado)"; $COMPOSE ps; exit 1; }
    sleep 5
  done
  echo "✅ $servicio sano"
done
docker image prune -f
echo "Deploy de ${RAMA} completado en $(hostname)"

# La VM de test corre también la QA (D-101): se rearma contra este checkout, sin tocar su git
if [ -n "$QA_DIR" ] && [ -f "$QA_DIR/despliegue/desplegar.sh" ]; then
  bash "$QA_DIR/despliegue/desplegar.sh" "$QA_DIR" "" "$PROJECT_DIR" < /dev/null
fi
