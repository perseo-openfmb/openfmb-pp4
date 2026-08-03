#!/usr/bin/env python3
"""Verifica los tiempos de muestreo del adaptador Modbus.

Reglas que se comprueban (ver el bloque CONVENCION en config/adapter.yaml):

  Perfiles de LECTURA  -> poll_period_ms == 5000
    MeterReadingProfile, ResourceReadingProfile, SwitchStatusProfile. Son los
    que se publican por NATS y terminan en TimescaleDB.

  SwitchDiscreteControlProfile -> poll_period_ms == 1000
    Son los interruptores: el periodo es la latencia con la que se acciona.
    A 5 s, cerrar un interruptor tardaria hasta 5 segundos.

  ResourceDiscreteControlProfile -> poll_period_ms == 5000
    Son setpoints de DER (limites de potencia del inversor, registros del
    Color Control), no accionamientos. Ponerlos a 1 s cuadruplicaba la carga
    Modbus y dejaba sin hilo a las sesiones de medicion.

  response_timeout_ms  -> se reporta como AVISO si supera el poll mas corto de
    su archivo, no como error: en modbus-fronius.yaml el equipo es lento y
    necesita 5 s aunque el archivo tenga un perfil de switch a 1 s. Es un
    atributo de sesion (uno por archivo), no por perfil.

Los tiempos viven en los archivos de modbus-master/. `config/adapter.yaml` ya
no los sobrescribe, pero si alguien vuelve a agregar un override
`profiles[N].poll_period_ms` o `response_timeout_ms` este script lo resuelve y
lo tiene en cuenta, porque el override gana.

Uso:
    python3 scripts/check_poll_periods.py           # verifica (salida 1 si falla)
    python3 scripts/check_poll_periods.py --list    # detalle por sesion
"""

from __future__ import annotations

import os
import sys
from collections import Counter

try:
    import yaml
except ImportError:
    sys.exit("Falta PyYAML. Instalalo con: pip install pyyaml")

LECTURA_MS = 5000
SWITCH_MS = 1000      # interruptores: latencia de accionamiento
RECURSO_MS = 5000     # setpoints de DER: no son accionamientos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADAPTER = os.path.join(RAIZ, "config", "adapter.yaml")

# Marcas en el nombre del perfil que identifican una lectura.
PERFILES_LECTURA = ("Reading", "Status")
PERFIL_SWITCH = "SwitchDiscreteControlProfile"


def es_lectura(nombre: str) -> bool:
    return any(marca in nombre for marca in PERFILES_LECTURA)


def esperado_para(nombre: str) -> int:
    """Periodo que le toca a un perfil segun su tipo."""
    if es_lectura(nombre):
        return LECTURA_MS
    return SWITCH_MS if nombre == PERFIL_SWITCH else RECURSO_MS


def main() -> int:
    listar = "--list" in sys.argv

    with open(ADAPTER, encoding="utf-8") as fh:
        adapter = yaml.safe_load(fh)

    sesiones = adapter["plugins"]["modbus-master"]["sessions"]
    problemas: list[str] = []
    avisos: list[str] = []
    n_lectura = n_switch = n_recurso = 0

    for sesion in sesiones:
        nombre_sesion = sesion.get("session-name", "?")
        archivo = os.path.basename(sesion["path"])
        ruta = os.path.join(RAIZ, "modbus-master", archivo)
        with open(ruta, encoding="utf-8") as fh:
            base = yaml.safe_load(fh)

        overrides = {o["key"]: o["value"] for o in sesion.get("overrides", [])}
        periodos: Counter[tuple[str, int]] = Counter()
        polls_del_archivo: list[int] = []

        for idx, perfil in enumerate(base.get("profiles") or []):
            nombre = perfil.get("name", "?")
            lectura = es_lectura(nombre)
            esperado = esperado_para(nombre)

            clave = f"profiles[{idx}].poll_period_ms"
            poll = int(overrides.get(clave, perfil.get("poll_period_ms", -1)))
            polls_del_archivo.append(poll)

            if lectura:
                n_lectura += 1
            elif nombre == PERFIL_SWITCH:
                n_switch += 1
            else:
                n_recurso += 1
            etiqueta = "LECTURA" if lectura else (
                "SWITCH" if nombre == PERFIL_SWITCH else "RECURSO")
            periodos[(etiqueta, poll)] += 1

            if poll != esperado:
                origen = "override en adapter.yaml" if clave in overrides else archivo
                problemas.append(
                    f"  {nombre_sesion} / profiles[{idx}] ({nombre}): "
                    f"{poll} ms, se esperaba {esperado} ms  [{origen}]"
                )

        timeout = int(
            overrides.get("response_timeout_ms", base.get("response_timeout_ms", -1))
        )
        if polls_del_archivo and timeout > min(polls_del_archivo):
            # Aviso, no error: en modbus-fronius.yaml el equipo es lento y
            # necesita 5 s de timeout aunque tenga un perfil de switch a 1 s.
            avisos.append(
                f"  {nombre_sesion}: response_timeout_ms={timeout} ms supera el poll "
                f"mas corto del archivo ({min(polls_del_archivo)} ms)"
            )

        if listar:
            detalle = "  ".join(
                f"{tipo}:{c}x{v}ms" for (tipo, v), c in sorted(periodos.items())
            )
            print(f"{nombre_sesion:24s} {archivo:32s} timeout={timeout:>5d}ms  {detalle}")

    if avisos:
        print("\nAvisos (timeout mayor que el ciclo mas corto del archivo):")
        print("\n".join(avisos))

    if problemas:
        print("\nFALLO:", file=sys.stderr)
        print("\n".join(problemas), file=sys.stderr)
        return 1

    print(
        f"\nOK: {n_lectura} lecturas a {LECTURA_MS} ms, "
        f"{n_switch} interruptores a {SWITCH_MS} ms, "
        f"{n_recurso} setpoints a {RECURSO_MS} ms."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
