#!/usr/bin/env python3
"""
Read actual register values from devices that respond to FC03/FC04.
Uses the exact register addresses from the adapter YAML configs.
"""
import socket
import struct
import time

def modbus_read(client, unit, func, address, count, tx_id=1):
    """Send raw Modbus read request, return register values."""
    pdu = bytes([func]) + struct.pack(">HH", address, count)
    mbap = struct.pack(">HH", tx_id, 0) + struct.pack(">H", 1 + len(pdu)) + bytes([unit]) + pdu
    client.sendall(mbap)
    time.sleep(0.2)
    resp = client.recv(1024)
    
    if len(resp) < 9:
        return None, f"short response ({resp.hex()})"
    
    func_resp = resp[7]
    if func_resp & 0x80:  # Exception
        exc_code = resp[8]
        return None, f"exception {exc_code}"
    
    byte_count = resp[8]
    reg_data = resp[9:9+byte_count]
    regs = [struct.unpack(">H", reg_data[i:i+2])[0] for i in range(0, len(reg_data), 2)]
    return regs, None

def float32_from_regs(hi, lo):
    return struct.unpack(">f", struct.pack(">HH", hi, lo))[0]

# Schneider registers (FC03)
print("="*70)
print("  SCHNEIDER METERS — FC03 Holding Registers")
print("="*70)

schneider_devices = [
    {"name": "schneider-iluminacion", "ip": "192.168.0.8",  "port": 26, "unit": 11},
    {"name": "schneider-microinv",    "ip": "192.168.0.10", "port": 26, "unit": 22},
    {"name": "schneider-fronius",     "ip": "192.168.0.10", "port": 26, "unit": 24},
]

# Key registers from adapter YAML:
# current A: lower=3010, upper=3009 (float32, scale 0.1)
# voltage L-N: lower=3036, upper=3035 (float32)
# voltage L-L: lower=3068, upper=3067 (float32)
# power VA: lower=3110, upper=3109 (float32)

for dev in schneider_devices:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((dev["ip"], dev["port"]))
    except Exception as e:
        print(f"\n  {dev['name']}: TCP FAIL ({e})")
        continue
    
    print(f"\n  {dev['name']} (u{dev['unit']}):")
    
    # Read a range that covers the key registers
    regs, err = modbus_read(s, dev["unit"], 0x03, 3000, 120)
    if err:
        print(f"    Error reading regs 3000-1319: {err}")
    else:
        print(f"    Read {len(regs)} registers starting at 3000")
        # Key indices: 3009-3010, 3035-3036, 3067-3068, 3109-3110
        offsets = {
            "Current B (3009-3010)": (9, 0.1),
            "Voltage L-N net (3035-3036)": (35, 1.0),
            "Voltage L-L phsAB (3067-3068)": (67, 1.0),
            "Power VA net (3109-3110)": (109, 1.0),
        }
        for label, (off, scale) in offsets.items():
            if off + 1 < len(regs):
                val = float32_from_regs(regs[off], regs[off+1]) * scale
                print(f"    {label}: {val:.2f}")
            else:
                print(f"    {label}: out of range")
    
    s.close()

# Siemens registers (FC01/FC02 — coils only)
print("\n" + "="*70)
print("  SIEMENS METERS — FC01 Coils + FC03 attempt")
print("="*70)

siemens_devices = [
    {"name": "siemens-red",     "ip": "192.168.0.8", "port": 26, "unit": 14},
    {"name": "siemens-quattro", "ip": "192.168.0.8", "port": 26, "unit": 13},
]

for dev in siemens_devices:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((dev["ip"], dev["port"]))
    except Exception as e:
        print(f"\n  {dev['name']}: TCP FAIL ({e})")
        continue
    
    print(f"\n  {dev['name']} (u{dev['unit']}):")
    
    # FC03
    regs, err = modbus_read(s, dev["unit"], 0x03, 0, 10, tx_id=10)
    print(f"    FC03 reg 0-9: {'ok' if regs else err}")
    
    # FC04
    regs, err = modbus_read(s, dev["unit"], 0x04, 0, 10, tx_id=11)
    print(f"    FC04 reg 0-9: {'ok' if regs else err}")
    
    s.close()

# Piranometro registers
print("\n" + "="*70)
print("  PIRANOMETRO — FC03 + FC04")
print("="*70)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3.0)
s.connect(("192.168.0.10", 26))
print("\n  piranometro (u12):")

regs, err = modbus_read(s, 12, 0x03, 0, 20, tx_id=20)
if regs:
    print(f"    FC03 regs 0-19: {[f'{r:04x}' for r in regs]}")
    if len(regs) >= 4:
        print(f"    reg0-1 as float32: {float32_from_regs(regs[0], regs[1]):.4f}")
        print(f"    reg2-3 as float32: {float32_from_regs(regs[2], regs[3]):.4f}")

regs, err = modbus_read(s, 12, 0x04, 0, 20, tx_id=21)
if regs:
    print(f"    FC04 regs 0-19: {[f'{r:04x}' for r in regs]}")
    if len(regs) >= 4:
        print(f"    reg0-1 as float32: {float32_from_regs(regs[0], regs[1]):.4f}")
        print(f"    reg2-3 as float32: {float32_from_regs(regs[2], regs[3]):.4f}")

s.close()

# Modbox
print("\n" + "="*70)
print("  MODBOX — FC01 Coils + FC03 Registers")
print("="*70)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3.0)
s.connect(("192.168.0.50", 1503))
print("\n  modbox-centro (u1):")

regs, err = modbus_read(s, 1, 0x01, 0, 16, tx_id=30)
if regs:
    print(f"    FC01 coils 0-15: {[f'{r:04x}' for r in regs]}")
else:
    print(f"    FC01: {err}")

regs, err = modbus_read(s, 1, 0x03, 0, 20, tx_id=31)
if regs:
    print(f"    FC03 regs 0-19: {[f'{r:04x}' for r in regs]}")
else:
    print(f"    FC03: {err}")

s.close()

# Fronius — Sunspec register map
print("\n" + "="*70)
print("  FRONIUS — Sunspec Register Map (Model 101)")
print("="*70)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3.0)
s.connect(("192.168.0.9", 26))
print("\n  fronius (u21):")

# Sunspec common block starts at 40000
# Model 101 (single phase inverter): W, VA, VAr, A, Ah, Wh, VArh
sunspec_regs = {
    40095: "W (AC Power)",
    40096: "VA (Apparent Power)",
    40097: "VAr (Reactive Power)",
    40099: "A (AC Current)",
    40101: "Wh (AC Energy)",
    40103: "VArh (Reactive Energy)",
}

regs, err = modbus_read(s, 21, 0x03, 40095, 15, tx_id=700)
if regs:
    print(f"\n  Registers 40095-40109 ({len(regs)} regs):")
    for i, r in enumerate(regs):
        addr = 40095 + i
        label = sunspec_regs.get(addr, "")
        if i < len(regs) - 1 and i % 2 == 0:
            val = float32_from_regs(regs[i], regs[i+1])
            print(f"    [{addr}] 0x{r:04x} {regs[i+1]:04x}  float32={val:12.2f}  {label}")
        elif i % 2 == 1:
            continue
        else:
            print(f"    [{addr}] 0x{r:04x}  int16={r}  {label}")
else:
    print(f"  Error: {err}")

# Quick reads for key values
regs, err = modbus_read(s, 21, 0x03, 40095, 2, tx_id=710)
if regs:
    w = float32_from_regs(regs[0], regs[1])
    print(f"\n  AC Power (W) = {w:.1f}")

regs, err = modbus_read(s, 21, 0x03, 40097, 2, tx_id=711)
if regs:
    var = float32_from_regs(regs[0], regs[1])
    print(f"  Reactive Power (VAr) = {var:.1f}")

regs, err = modbus_read(s, 21, 0x03, 40099, 2, tx_id=712)
if regs:
    a = float32_from_regs(regs[0], regs[1])
    print(f"  AC Current (A) = {a:.2f}")

s.close()
