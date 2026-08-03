#!/usr/bin/env python3
"""
Modbus Device Independent Test
Tests all configured Modbus devices outside the OpenFMB platform.
Run from host network (vlan20) to verify physical device connectivity.
"""
import sys
import time
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse

# ─── Device Configuration ───────────────────────────────────────────────────
DEVICES = [
    # Schneider meters
    {"name": "schneider-iluminacion",   "ip": "192.168.0.10",  "port": 26, "unit": 21, "test_regs": [40243]},
    #{"name": "schneider-iluminacion",   "ip": "192.168.0.8",  "port": 26, "unit": 11, "test_regs": [3000, 3009, 3010, 3035, 3036]},
    # {"name": "schneider-microinv",      "ip": "192.168.0.10", "port": 26, "unit": 22, "test_regs": [3000, 3009, 3010, 3035, 3036]},
    # {"name": "schneider-fronius",       "ip": "192.168.0.10", "port": 26, "unit": 24, "test_regs": [3000, 3009, 3010, 3035, 3036]},
    # # Siemens meters
    # {"name": "siemens-red",             "ip": "192.168.0.8",  "port": 26, "unit": 14, "test_regs": [3000, 3009, 3010, 3035, 3036]},
    # {"name": "siemens-quattro",         "ip": "192.168.0.8",  "port": 26, "unit": 13, "test_regs": [3000, 3009, 3010, 3035, 3036]},
    # # Piranometro
    # {"name": "piranometro",             "ip": "192.168.0.10", "port": 26, "unit": 12, "test_regs": [3000, 3009, 3010]},
    # # Fronius inverter
    # {"name": "fronius",                 "ip": "192.168.0.9",  "port": 26, "unit": 21, "test_regs": [40001, 40002, 40003]},
    # # Modboxes
    # {"name": "modbox-centro",           "ip": "192.168.0.50", "port": 1503, "unit": 1, "test_regs": [0, 1, 2]},
    # {"name": "modbox-terraza",          "ip": "192.168.0.107","port": 1505, "unit": 1, "test_regs": [0, 1, 2]},
    # # Color Controls (Victron)
    # {"name": "color-control-100",       "ip": "192.168.0.105","port": 502, "unit": 100, "test_regs": [0, 1, 2]},
    # {"name": "color-control-246",       "ip": "192.168.0.105","port": 502, "unit": 246, "test_regs": [0, 1, 2]},
]

TIMEOUT_SEC = 3.0


def test_device(dev):
    """Test a single device: TCP connect + read registers (FC3 + FC4)."""
    ip = dev["ip"]
    port = dev["port"]
    unit = dev["unit"]
    name = dev["name"]
    
    result = {
        "name": name,
        "ip": ip,
        "port": port,
        "unit": unit,
        "tcp_ok": False,
        "reads": [],
        "errors": [],
        "status": "FAIL"
    }
    
    client = ModbusTcpClient(host=ip, port=port, timeout=TIMEOUT_SEC, retries=0)
    try:
        connected = client.connect()
        result["tcp_ok"] = connected
        if not connected:
            result["errors"].append("TCP connection refused")
            result["status"] = "TCP_FAIL"
            return result
    except Exception as e:
        result["errors"].append(f"TCP error: {e}")
        result["status"] = "TCP_FAIL"
        return result
    
    # Try multiple function codes and register ranges
    test_scans = [
        {"fc": "holding", "regs": [0, 1, 2, 100, 200, 300]},
        {"fc": "input",   "regs": [0, 1, 2, 100, 200, 300]},
        {"fc": "holding", "regs": [3000, 3009, 3010, 3035, 3036]},
        {"fc": "input",   "regs": [3000, 3009, 3010, 3035, 3036]},
    ]
    
    success_count = 0
    total_tries = 0
    
    for scan in test_scans:
        for reg in scan["regs"]:
            total_tries += 1
            try:
                if scan["fc"] == "holding":
                    resp = client.read_holding_registers(address=reg, count=2, slave=unit)
                else:
                    resp = client.read_input_registers(address=reg, count=2, slave=unit)
                    
                if isinstance(resp, ExceptionResponse):
                    result["reads"].append({
                        "reg": reg, "fc": scan["fc"],
                        "status": "exception", "code": resp.exception_code
                    })
                elif resp.isError():
                    err_str = str(resp)
                    if "No Response" not in err_str:
                        result["reads"].append({
                            "reg": reg, "fc": scan["fc"],
                            "status": "error", "detail": err_str
                        })
                else:
                    if len(resp.registers) >= 2:
                        val = struct.unpack(">f", struct.pack(">HH", resp.registers[0], resp.registers[1]))[0]
                    else:
                        val = resp.registers[0]
                    result["reads"].append({
                        "reg": reg, "fc": scan["fc"],
                        "status": "ok", "value": val
                    })
                    success_count += 1
                    # Found working combo - scan nearby registers
                    for nearby in range(reg + 1, reg + 20):
                        try:
                            if scan["fc"] == "holding":
                                nr = client.read_holding_registers(address=nearby, count=2, slave=unit)
                            else:
                                nr = client.read_input_registers(address=nearby, count=2, slave=unit)
                            if not nr.isError() and not isinstance(nr, ExceptionResponse):
                                if len(nr.registers) >= 2:
                                    nv = struct.unpack(">f", struct.pack(">HH", nr.registers[0], nr.registers[1]))[0]
                                else:
                                    nv = nr.registers[0]
                                result["reads"].append({
                                    "reg": nearby, "fc": scan["fc"],
                                    "status": "ok", "value": nv
                                })
                                success_count += 1
                        except:
                            pass
                        time.sleep(0.03)
                    break  # Found working, skip remaining scans
            except Exception as e:
                pass
            time.sleep(0.05)
        if success_count > 0:
            break
    
    client.close()
    
    if success_count >= 3:
        result["status"] = "OK"
    elif success_count > 0:
        result["status"] = "PARTIAL"
    elif not result["errors"]:
        result["status"] = "NO_REGS"
    else:
        result["status"] = "FAIL"
    
    return result


def print_results(results):
    """Print formatted results."""
    ok = [r for r in results if r["status"] == "OK"]
    partial = [r for r in results if r["status"] == "PARTIAL"]
    fail = [r for r in results if r["status"] not in ("OK", "PARTIAL")]
    
    print(f"\n{'='*70}")
    print(f"  MODBUS DEVICE TEST REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")
    print(f"\n  SUMMARY: {len(ok)} OK | {len(partial)} PARTIAL | {len(fail)} FAIL / {len(results)} total\n")
    
    for r in results:
        icon = "✓" if r["status"] == "OK" else ("~" if r["status"] == "PARTIAL" else "✗")
        print(f"  [{icon}] {r['name']:<25} {r['ip']}:{r['port']} u{r['unit']:<4} → {r['status']}")
        for rd in r["reads"]:
            if rd["status"] == "ok":
                print(f"      reg {rd['reg']}: {rd['value']:.2f}")
            else:
                print(f"      reg {rd['reg']}: {rd['status']} {rd.get('code','')}{rd.get('detail','')}")
        if r["errors"]:
            for e in r["errors"]:
                print(f"      ERROR: {e}")
        print()


if __name__ == "__main__":
    print(f"\nModbus Independent Device Test — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Testing {len(DEVICES)} devices...\n")
    
    results = []
    for dev in DEVICES:
        sys.stdout.write(f"  Testing {dev['name']} ({dev['ip']}:{dev['port']} u{dev['unit']})... ")
        sys.stdout.flush()
        r = test_device(dev)
        results.append(r)
        print(r["status"])
    
    print_results(results)
    
    # Exit code: 0=all OK, 1=any failures
    statuses = [r["status"] for r in results]
    sys.exit(0 if all(s == "OK" for s in statuses) else 1)
