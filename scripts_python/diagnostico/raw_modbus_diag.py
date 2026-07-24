#!/usr/bin/env python3
"""
Raw Modbus TCP diagnostic — sends raw frames and captures exact responses.
"""
import socket
import struct
import time

def send_raw(client, tx_id, unit, func_code, data=b""):
    """Build and send a raw Modbus TCP frame, return response."""
    pdu = bytes([func_code]) + data
    mbap = struct.pack(">HH", tx_id, 0) + struct.pack(">H", 1 + len(pdu)) + bytes([unit]) + pdu
    client.sendall(mbap)
    time.sleep(0.3)
    resp = client.recv(1024)
    return resp

def decode_mbap(data):
    """Decode MBAP header."""
    if len(data) < 7:
        return {"raw": data.hex(), "error": "too_short"}
    tx_id, proto_id, length, unit_id = struct.unpack(">HHHB", data[:7])
    return {"tx_id": tx_id, "proto_id": proto_id, "length": length, "unit_id": unit_id, "pdu": data[7:].hex()}

DEVICES = [
    {"name": "schneider-iluminacion",  "ip": "192.168.0.8",  "port": 26, "unit": 11},
    {"name": "siemens-red",            "ip": "192.168.0.8",  "port": 26, "unit": 14},
    {"name": "siemens-quattro",        "ip": "192.168.0.8",  "port": 26, "unit": 13},
    {"name": "piranometro",            "ip": "192.168.0.10", "port": 26, "unit": 12},
    {"name": "fronius",                "ip": "192.168.0.9",  "port": 26, "unit": 21},
    {"name": "modbox-centro",          "ip": "192.168.0.50", "port": 1503, "unit": 1},
    {"name": "color-control-100",      "ip": "192.168.0.105","port": 502, "unit": 100},
]

FUNC_CODES = [
    (0x01, "Read Coils"),
    (0x02, "Read Discrete Inputs"),
    (0x03, "Read Holding Registers"),
    (0x04, "Read Input Registers"),
]

for dev in DEVICES:
    print(f"\n{'='*60}")
    print(f"  {dev['name']} ({dev['ip']}:{dev['port']} unit={dev['unit']})")
    print(f"{'='*60}")
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((dev["ip"], dev["port"]))
        print("  TCP CONNECT: OK")
    except Exception as e:
        print(f"  TCP CONNECT: FAIL ({e})")
        s.close()
        continue
    
    tx = 1
    for fc, fc_name in FUNC_CODES:
        try:
            resp = send_raw(s, tx, dev["unit"], fc, struct.pack(">HH", 0, 10))
            decoded = decode_mbap(resp)
            if "error" in decoded:
                print(f"  FC{fc:02d} ({fc_name}): response={resp.hex()}")
            else:
                print(f"  FC{fc:02d} ({fc_name}): tx={decoded['tx_id']} len={decoded['length']} unit={decoded['unit_id']} pdu={decoded['pdu']}")
        except socket.timeout:
            print(f"  FC{fc:02d} ({fc_name}): TIMEOUT")
        except Exception as e:
            print(f"  FC{fc:02d} ({fc_name}): ERROR ({e})")
        tx += 1
        time.sleep(0.1)
    
    s.close()
