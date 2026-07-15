#!/usr/bin/env bash
# Restore a TimescaleDB dump (created by the db-backup service or `pg_dump -Fc`)
# into the running `timescaledb` container.
#
# DESTRUCTIVE: it drops and recreates the target database before loading the
# dump, so the result is exactly the dump's contents. Run it on a fresh clone
# *before* starting the adapter, or whenever you want to roll the DB back to a
# snapshot.
#
# TimescaleDB hypertables require the pre/post-restore dance, which this script
# performs automatically.
#
# Usage:
#   scripts/db_restore.sh backups/openfmb_2026-06-26_03-00-00.dump
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here"

DUMP="${1:-}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
    echo "Uso: $0 <archivo.dump>" >&2
    echo "Dumps disponibles en ./backups:" >&2
    ls -1t backups/*.dump 2>/dev/null | sed 's/^/  /' >&2 || echo "  (ninguno)" >&2
    exit 1
fi

# Connection settings come from .env (DB_NAME / DB_PASS).
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi
DB="${DB_NAME:-openfmb}"
PASS="${DB_PASS:-password}"

if ! docker ps --format '{{.Names}}' | grep -qx timescaledb; then
    echo "El contenedor 'timescaledb' no está corriendo." >&2
    echo "Inícialo primero con:  docker compose up -d timescale" >&2
    exit 1
fi

echo "ADVERTENCIA: se BORRARÁ y recreará la base '$DB' con el contenido de:"
echo "    $DUMP"
printf "Escribe 'si' para continuar: "
read -r ans
[ "$ans" = "si" ] || { echo "Cancelado."; exit 1; }

dump_dir="$(cd "$(dirname "$DUMP")" && pwd)"
dump_file="$(basename "$DUMP")"

# Share the timescaledb container's network namespace so we reach Postgres on
# 127.0.0.1 without needing to know the compose network name. `-i` keeps stdin
# open so the container's `sh -s` actually receives the heredoc script.
docker run --rm -i \
    --network "container:timescaledb" \
    -e PGHOST=127.0.0.1 -e PGPORT=5432 -e PGUSER=postgres -e PGPASSWORD="$PASS" \
    -v "$dump_dir:/restore:ro" \
    postgres:12-alpine sh -s "$DB" "$dump_file" <<'INNER'
set -eu
DB="$1"; FILE="$2"

echo ">> cerrando conexiones a '$DB' ..."
psql -d postgres -v ON_ERROR_STOP=1 -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB' AND pid<>pg_backend_pid();" >/dev/null || true

echo ">> recreando base '$DB' ..."
psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB\";"
psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$DB\";"

echo ">> preparando TimescaleDB (pre_restore) ..."
psql -d "$DB" -v ON_ERROR_STOP=1 -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
psql -d "$DB" -v ON_ERROR_STOP=1 -c "SELECT timescaledb_pre_restore();"

echo ">> restaurando datos ..."
# pg_restore puede devolver avisos no fatales (p.ej. la extensión ya existe);
# son normales en TimescaleDB, así que no abortamos por ellos.
pg_restore --no-owner --dbname="$DB" "/restore/$FILE" \
    || echo ">> pg_restore terminó con avisos (revisa arriba); continúo."

echo ">> finalizando (post_restore) ..."
psql -d "$DB" -v ON_ERROR_STOP=1 -c "SELECT timescaledb_post_restore();"
echo ">> OK."
INNER

echo "Restauración completada en la base '$DB'."
