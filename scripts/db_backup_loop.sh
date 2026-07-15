#!/bin/sh
# Periodic TimescaleDB logical backup loop.
#
# Runs inside the `db-backup` compose service. Every BACKUP_INTERVAL_SECONDS it
# takes a compressed custom-format dump (pg_dump -Fc) of the whole database into
# /backups, then prunes everything but the newest BACKUP_KEEP dumps.
#
# Connection settings come from the standard libpq env vars (PGHOST, PGUSER,
# PGPASSWORD, PGDATABASE, ...), so pg_dump needs no extra flags. Restores are
# handled separately by scripts/db_restore.sh (hypertables need the TimescaleDB
# pre/post-restore steps).
set -eu

: "${PGDATABASE:=openfmb}"
: "${BACKUP_INTERVAL_SECONDS:=86400}"   # one dump per day by default
: "${BACKUP_KEEP:=7}"                   # keep the 7 most recent dumps
BACKUP_DIR=/backups

log() { echo "[db-backup] $(date '+%Y-%m-%dT%H:%M:%S%z') $*"; }

backup_once() {
    ts=$(date +%Y-%m-%d_%H-%M-%S)
    out="${BACKUP_DIR}/${PGDATABASE}_${ts}.dump"
    log "creando ${out} ..."
    # Write to a temp name first so a crash never leaves a half-written dump
    # that the rotation could mistake for a good backup.
    if pg_dump -Fc -f "${out}.partial"; then
        mv "${out}.partial" "${out}"
        log "OK $(du -h "${out}" | cut -f1) -> ${out}"
    else
        log "ERROR: pg_dump falló; se descarta el archivo parcial"
        rm -f "${out}.partial"
        return 1
    fi

    # Rotation: keep only the newest BACKUP_KEEP dumps.
    total=$(ls -1t "${BACKUP_DIR}/${PGDATABASE}_"*.dump 2>/dev/null | wc -l)
    if [ "${total}" -gt "${BACKUP_KEEP}" ]; then
        ls -1t "${BACKUP_DIR}/${PGDATABASE}_"*.dump | tail -n +"$((BACKUP_KEEP + 1))" | while read -r old; do
            log "rotando (elimino) ${old}"
            rm -f "${old}"
        done
    fi
}

log "arranque | base=${PGDATABASE} intervalo=${BACKUP_INTERVAL_SECONDS}s conservar=${BACKUP_KEEP}"
while true; do
    # `|| true` so a transient failure (e.g. DB momentarily down) never kills
    # the loop; it just retries on the next tick.
    backup_once || true
    sleep "${BACKUP_INTERVAL_SECONDS}"
done
