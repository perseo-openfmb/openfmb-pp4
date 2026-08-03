#!/usr/bin/env python3
"""Exporta los dashboards de Grafana a config/grafana/dashboards/*.json.

POR QUE EXISTE ESTE SCRIPT
--------------------------
El provisioning por archivo de Grafana es de una sola via: los JSON de
config/grafana/dashboards/ se cargan hacia Grafana, pero lo que se edita y se
guarda en la interfaz vive solo en grafana.db (el volumen `grafana_data`).
Con `allowUiUpdates: true` la interfaz deja guardar, pero ese cambio NO vuelve
al repositorio: por eso un `git push` se lleva los JSON viejos y las ediciones
se pierden al migrar de maquina o al recrear el volumen.

Este script cierra el circuito. El flujo de trabajo es:

    1. Editar el dashboard en la interfaz de Grafana y guardarlo.
    2. python3 scripts/grafana_export_dashboards.py
    3. git add config/grafana/dashboards && git commit

Ojo con la direccion de la sincronizacion: si cambias un JSON en disco, el
provisioner lo recarga (updateIntervalSeconds: 30) y pisa lo que hubiera en la
interfaz. Exporta ANTES de tocar los archivos a mano.

Uso:
    python3 scripts/grafana_export_dashboards.py            # exporta todo
    python3 scripts/grafana_export_dashboards.py --check    # solo reporta diferencias
    python3 scripts/grafana_export_dashboards.py --url http://localhost:3000
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(RAIZ, "config", "grafana", "dashboards")
ENV = os.path.join(RAIZ, ".env")

# Claves que Grafana agrega al servir un dashboard y que no deben versionarse:
# son estado de la instancia, no del dashboard.
DESCARTAR = ("id", "version")


def leer_env(ruta: str) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not os.path.exists(ruta):
        return valores
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def api(url: str, ruta: str, usuario: str, clave: str):
    cred = base64.b64encode(f"{usuario}:{clave}".encode()).decode()
    req = urllib.request.Request(
        f"{url}{ruta}", headers={"Authorization": f"Basic {cred}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            sys.exit(
                f"ERROR: credenciales rechazadas para '{usuario}'.\n"
                "Revisa GRAFANA_USER / GRAFANA_PASSWORD en el .env.\n"
                "Si el .env cambio despues de crear el volumen, sincroniza la clave con:\n"
                "    ./scripts/grafana_reset_admin_password.sh"
            )
        sys.exit(f"ERROR: {ruta} devolvio HTTP {exc.code}: {exc.read().decode()[:200]}")
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: no pude conectar con {url} ({exc.reason}).")


def slug(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", texto).strip("-") or "dashboard"


def mapa_uid_archivo() -> dict[str, str]:
    """uid -> ruta del JSON ya versionado, para no duplicar archivos."""
    mapa: dict[str, str] = {}
    for nombre in os.listdir(DEST):
        if not nombre.endswith(".json"):
            continue
        ruta = os.path.join(DEST, nombre)
        try:
            with open(ruta, encoding="utf-8") as fh:
                uid = json.load(fh).get("uid")
        except (json.JSONDecodeError, OSError):
            continue
        if uid:
            mapa[uid] = ruta
    return mapa


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", default=None, help="URL de Grafana (por defecto http://localhost:<GRAFANA_PORT>)")
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--check", action="store_true", help="no escribe; solo lista lo que cambiaria")
    args = ap.parse_args()

    env = leer_env(ENV)
    url = (args.url or f"http://localhost:{env.get('GRAFANA_PORT', '3000')}").rstrip("/")
    usuario = args.user or env.get("GRAFANA_USER", "admin")
    clave = args.password or env.get("GRAFANA_PASSWORD", "")
    if not clave:
        return int(bool(sys.stderr.write("ERROR: falta GRAFANA_PASSWORD en el .env.\n")))

    os.makedirs(DEST, exist_ok=True)
    existentes = mapa_uid_archivo()

    encontrados = api(url, "/api/search?type=dash-db&limit=5000", usuario, clave)
    if not encontrados:
        print("Grafana no reporta dashboards.")
        return 0

    cambiados, iguales, nuevos = [], [], []
    for entrada in encontrados:
        uid = entrada["uid"]
        payload = api(url, f"/api/dashboards/uid/{uid}", usuario, clave)
        panel = payload["dashboard"]
        for clave_desc in DESCARTAR:
            panel.pop(clave_desc, None)

        ruta = existentes.get(uid)
        if ruta is None:
            ruta = os.path.join(DEST, f"{slug(panel.get('title', uid))}.json")
            nuevos.append(os.path.basename(ruta))

        texto = json.dumps(panel, indent=2, ensure_ascii=False, sort_keys=False) + "\n"

        anterior = None
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as fh:
                anterior = fh.read()
        # Compara ya normalizado: si solo cambio el `version`, no es un cambio real.
        if anterior is not None:
            try:
                previo = json.loads(anterior)
                for clave_desc in DESCARTAR:
                    previo.pop(clave_desc, None)
                if previo == panel:
                    iguales.append(os.path.basename(ruta))
                    continue
            except json.JSONDecodeError:
                pass

        cambiados.append(os.path.basename(ruta))
        if not args.check:
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(texto)

    verbo = "cambiarian" if args.check else "actualizados"
    print(f"sin cambios : {len(iguales)}")
    print(f"{verbo:12s}: {len(cambiados)}")
    for n in cambiados:
        print(f"    {n}{'  (nuevo)' if n in nuevos else ''}")
    if cambiados and not args.check:
        print("\nRevisa el diff y haz commit:")
        print("    git add config/grafana/dashboards && git commit -m 'grafana: actualiza dashboards'")
    return 1 if (args.check and cambiados) else 0


if __name__ == "__main__":
    raise SystemExit(main())
