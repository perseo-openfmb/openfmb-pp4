#!/bin/sh
# Provisiona el usuario de solo lectura de Grafana y el tema de la organizacion.
#
# Grafana solo provisiona por archivo datasources, dashboards, alertas y
# plugins: los usuarios hay que crearlos por la API de administracion. Este
# script corre en el servicio `grafana-init` (un solo uso) despues de que el
# healthcheck de Grafana pasa, y es idempotente: si el usuario ya existe se
# limita a re-sincronizar su clave y su rol.
#
# El admin no se toca aqui: lo fija Grafana en cada arranque a partir de
# GF_SECURITY_ADMIN_USER / GF_SECURITY_ADMIN_PASSWORD.
set -eu

: "${GRAFANA_URL:=http://grafana:3000}"
: "${GRAFANA_VIEWER_NAME:=Consulta PERSEO}"
: "${GRAFANA_THEME:=light}"

log() { echo "[grafana-init] $*"; }
die() { echo "[grafana-init] ERROR: $*" >&2; exit 1; }

for v in GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_VIEWER_USER GRAFANA_VIEWER_PASSWORD; do
    eval "val=\${$v:-}"
    [ -n "$val" ] || die "falta la variable $v (definila en el .env del proyecto)"
done

AUTH="${GRAFANA_ADMIN_USER}:${GRAFANA_ADMIN_PASSWORD}"

# `api` METODO RUTA [BODY] -> imprime el cuerpo, devuelve el codigo HTTP en la
# ultima linea para poder distinguir "ya existia" de un error real.
api() {
    _method=$1; _path=$2; _body=${3:-}
    if [ -n "$_body" ]; then
        curl -sS -u "$AUTH" -X "$_method" \
            -H 'Content-Type: application/json' \
            -w '\n%{http_code}' \
            -d "$_body" "${GRAFANA_URL}${_path}"
    else
        curl -sS -u "$AUTH" -X "$_method" \
            -H 'Content-Type: application/json' \
            -w '\n%{http_code}' "${GRAFANA_URL}${_path}"
    fi
}

status() { printf '%s' "$1" | tail -n 1; }
body()   { printf '%s' "$1" | sed '$d'; }

# Espera de cortesia: depends_on: service_healthy ya garantiza que Grafana
# responde, pero un reinicio del stack puede dejar la API un instante ocupada
# aplicando el provisioning de dashboards.
i=0
until curl -sf "${GRAFANA_URL}/api/health" >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -lt 30 ] || die "Grafana no respondio en ${GRAFANA_URL} tras 60s"
    sleep 2
done

# Verifica que las credenciales de admin del .env sirven de verdad. Si el
# volumen trae una clave vieja, Grafana la reescribe al arrancar, asi que un
# 401 aqui casi siempre significa que el .env y el contenedor no coinciden.
resp=$(api GET /api/org)
[ "$(status "$resp")" = "200" ] || die "no pude autenticarme como '${GRAFANA_ADMIN_USER}' (HTTP $(status "$resp")). Revisa GRAFANA_USER/GRAFANA_PASSWORD en el .env."

# --- Usuario de solo lectura -------------------------------------------------
resp=$(api GET "/api/users/lookup?loginOrEmail=${GRAFANA_VIEWER_USER}")
code=$(status "$resp")

if [ "$code" = "200" ]; then
    uid=$(body "$resp" | sed -n 's/.*"id":[ ]*\([0-9]*\).*/\1/p')
    log "el usuario '${GRAFANA_VIEWER_USER}' ya existe (id=${uid}); re-sincronizando clave y rol"
    resp=$(api PUT "/api/admin/users/${uid}/password" \
        "{\"password\":\"${GRAFANA_VIEWER_PASSWORD}\"}")
    [ "$(status "$resp")" = "200" ] || log "aviso: no pude actualizar la clave (HTTP $(status "$resp"))"
elif [ "$code" = "404" ]; then
    log "creando el usuario de solo lectura '${GRAFANA_VIEWER_USER}'"
    resp=$(api POST /api/admin/users \
        "{\"name\":\"${GRAFANA_VIEWER_NAME}\",\"login\":\"${GRAFANA_VIEWER_USER}\",\"password\":\"${GRAFANA_VIEWER_PASSWORD}\"}")
    [ "$(status "$resp")" = "200" ] || die "no pude crear el usuario (HTTP $(status "$resp")): $(body "$resp")"
    uid=$(body "$resp" | sed -n 's/.*"id":[ ]*\([0-9]*\).*/\1/p')
else
    die "consulta de usuario fallida (HTTP ${code}): $(body "$resp")"
fi

[ -n "${uid:-}" ] || die "no pude determinar el id del usuario '${GRAFANA_VIEWER_USER}'"

# Rol Viewer en la organizacion 1: puede ver y explorar dashboards, pero no
# guardarlos, editarlos ni tocar datasources.
resp=$(api PATCH "/api/org/users/${uid}" '{"role":"Viewer"}')
case "$(status "$resp")" in
    200) log "rol Viewer asignado a '${GRAFANA_VIEWER_USER}'" ;;
    *)   die "no pude asignar el rol Viewer (HTTP $(status "$resp")): $(body "$resp")" ;;
esac

# Nunca debe ser admin de instancia (por si el usuario venia de una version
# anterior del stack creado a mano).
api PUT "/api/admin/users/${uid}/permissions" '{"isGrafanaAdmin":false}' >/dev/null 2>&1 || true

# --- Tema de la organizacion -------------------------------------------------
# GF_USERS_DEFAULT_THEME cubre a los usuarios nuevos; esto fija ademas la
# preferencia de la organizacion para que el tema no dependa de grafana.db.
resp=$(api PUT /api/org/preferences "{\"theme\":\"${GRAFANA_THEME}\",\"homeDashboardUID\":\"\",\"timezone\":\"\"}")
[ "$(status "$resp")" = "200" ] && log "tema de la organizacion: ${GRAFANA_THEME}" \
    || log "aviso: no pude fijar el tema (HTTP $(status "$resp"))"

log "listo. admin='${GRAFANA_ADMIN_USER}' (edicion) | viewer='${GRAFANA_VIEWER_USER}' (solo lectura)"
