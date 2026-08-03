#!/bin/sh
# Sincroniza la clave real del admin de Grafana con la del .env.
#
# POR QUE HACE FALTA
# Grafana aplica GF_SECURITY_ADMIN_PASSWORD solo cuando crea el usuario admin
# por primera vez en un volumen vacio. En arranques posteriores NO la reescribe:
# la clave real vive en grafana.db (volumen `grafana_data`). Por eso se puede
# llegar a la situacion de tener el .env diciendo una cosa y el login rechazando
# esa misma clave, que es justo lo que pasa al editar el .env de un stack que ya
# venia corriendo.
#
# Este script usa `grafana-cli` DENTRO del contenedor, que es la via soportada
# para reescribir la clave sobre una base ya inicializada.
#
# Uso:
#   ./scripts/grafana_reset_admin_password.sh              # toma la clave del .env
#   ./scripts/grafana_reset_admin_password.sh 'otraClave'  # o una explicita
set -eu

RAIZ=$(cd "$(dirname "$0")/.." && pwd)
CONTENEDOR=${GRAFANA_CONTAINER:-grafana}

leer_env() {
    [ -f "$RAIZ/.env" ] || return 1
    sed -n "s/^$1=//p" "$RAIZ/.env" | head -n 1 | tr -d '"'"'"'' | tr -d '\r'
}

CLAVE=${1:-$(leer_env GRAFANA_PASSWORD || true)}
USUARIO=$(leer_env GRAFANA_USER || echo admin)

if [ -z "${CLAVE:-}" ]; then
    echo "ERROR: no hay clave. Define GRAFANA_PASSWORD en el .env o pasala como argumento." >&2
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
    echo "ERROR: el contenedor '$CONTENEDOR' no esta corriendo (docker compose up -d grafana)." >&2
    exit 1
fi

# grafana-cli solo sabe resetear al usuario admin de instancia. Si el login del
# admin se renombro en el .env, avisamos en vez de fallar en silencio.
if [ "$USUARIO" != "admin" ]; then
    echo "Aviso: GRAFANA_USER='$USUARIO'. grafana-cli resetea al admin por id, no por login."
fi

echo "Reescribiendo la clave del admin en $CONTENEDOR ..."
docker exec "$CONTENEDOR" grafana-cli --homepath /usr/share/grafana \
    admin reset-admin-password "$CLAVE"

echo
echo "Listo. Comprobando que el login responde ..."
CODIGO=$(docker exec "$CONTENEDOR" curl -s -o /dev/null -w '%{http_code}' \
    -X POST -H 'Content-Type: application/json' \
    -d "{\"user\":\"${USUARIO}\",\"password\":\"${CLAVE}\"}" \
    http://localhost:3000/login || echo "000")

if [ "$CODIGO" = "200" ]; then
    echo "OK: login correcto como '$USUARIO'."
else
    echo "ATENCION: el login devolvio HTTP $CODIGO. Revisa GRAFANA_USER en el .env." >&2
    exit 1
fi
