# %%
# Script for Modbus TCP Slave Emulator
# Author: Kevin D. Martinez Zapata
# Date: 2024-08-05
# Version: 2.2

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse
import time
# %%
# Variables
clientType = "tcp"
client = None

def chack_connection(port: str, idx_list: list) -> dict:
    client = ModbusTcpClient(host="192.168.0.8", port=port)
    result = {}

    if not client.connect():
        raise ConnectionError(f"Could not connect to Modbus client on port {port}")
    
    print(f"Connected to Modbus client on port {port}")

    registers = [40096, 21]

    for slaveNum in idx_list:
        response = client.read_holding_registers(21, 2, slave=slaveNum)

        if not response.isError():
            # Ideal response handling
            result[slaveNum] = True
            print(f"[ID {slaveNum}] ONLINE: Respuesta válida.")
        elif isinstance(response, ExceptionResponse):
            # Critical error handling
            result[slaveNum] = True
            print(f"[ID {slaveNum}] ONLINE: Respondió con Excepción Modbus ({response}).")
        elif isinstance(response, ModbusIOException):
            # No response handling
            result[slaveNum] = False
            print(f"[ID {slaveNum}] OFFLINE: Sin respuesta (Timeout).")
        else:
            # Unknown error handling
            result[slaveNum] = False
            print(f"[ID {slaveNum}] ERROR: {response}")

    client.close()
    return result
# %%
while True:
    if clientType == "tcp":
        ids_to_check = [11]  # IDs from 1 to 10
        port = 26

        try:
            status = chack_connection(port, ids_to_check)
            print("Final Status:", status)
        except ConnectionError as e:
            print(e)

        print("-----" * 10)

        time.sleep(1)
# %%
