from pymodbus.client import ModbusTcpClient
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse
import struct
import time

clientType = "tcp"
client = None

if clientType == "tcp":
    client = ModbusTcpClient(host="192.168.0.10", port=26)
elif clientType == "serial":
    client = ModbusSerialClient(
        "COM3", baudrate=19200, bytesize=8, parity="N", stopbits=1, debug=False
    )
else:
    print("Client type not supported")
    exit()
count_total = 0
count_erros = 0
# Modbus slave number
# slaves = [11, 13, 14]
# slaves = [22, 23, 24]
# slaves = [12]
# slaves = [246]
slaves = [12]
# 21,22,23
while True:
    for slaveNum in slaves:
        # print("Trying Slave ID: ", slaveNum)
        count_total += 1
        try:
            # Connect to the client
            if not client.connect():
                raise ConnectionError(f"Could not connect to Modbus client")

            volRegisters = client.read_holding_registers(82, 2, slave=slaveNum)
            # print(volRegisters.registers[0])
            #esta linea ubica el primer parametro como puntero en el stack, el numero de registros es el numero de posiciiones que lee desde el indice
            # para leer los registros 40096 y 40097, el puntero se ubica en 40094 y se lee dos registros mas (40095 y 40096) que son R-1
            # reg 40094

            # R = 40096 -40097 Apparent Power
            # R= 40092 - 40093 AC power
            #-----------------------------


            VoltageListF = struct.unpack(
                ">f",
                struct.pack(">HH", volRegisters.registers[0], volRegisters.registers[1]),
            )[0]

            # Read registers and convert to float
            # volRegisters = client.read_holding_registers(2999 + 28, 4, slave=slaveNum)
            # VoltageListF = struct.unpack(
            #h   ">f",
            #     struct.pack(">HH", currRegisters.registers[0], currRegisters.registers[1]),
            # )[0]

            # activPowRegisters = client.read_holding_registers(2999 + 60, 4, slave=slaveNum)
            # ActivePowerF = struct.unpack(
            #     ">f",
            #     struct.pack(
            #         ">HH", activPowRegisters.registers[0], activPowRegisters.registers[1]
            #     ),
            # )[0]

            # reactivPowRegisters = client.read_holding_registers(2999+68, 4, slave=slaveNum)
            # ReactivePowerF = struct.unpack(">f", struct.pack(">HH", reactivPowRegisters.registers[0], reactivPowRegisters.registers[1]))[0]

            # AparntPowRegisters = client.read_holding_registers(2999+76, 4, slave=slaveNum)
            # AaparentPowerF = struct.unpack(">f", struct.pack(">HH", AparntPowRegisters.registers[0], AparntPowRegisters.registers[1]))[0]

            # PFRegisters = client.read_holding_registers(2999+84, 4, slave=slaveNum)
            # PFF = struct.unpack(">f", struct.pack(">HH", PFRegisters.registers[0], PFRegisters.registers[1]))[0]

            # frecRegisters = client.read_holding_registers(2999+110, 4, slave=slaveNum)
            # FrecF = struct.unpack(">f", struct.pack(">HH", frecRegisters.registers[0], frecRegisters.registers[1]))[0]

            # Close the client connection
            client.close()

            # Print the results
            print(f"[{count_total}] Voltage - Slave [{slaveNum}]: ", VoltageListF)
            # print("Current: ", CurrentListF)
            # print("Power: ", ActivePowerF)
            # print("Reactive Power: ", ReactivePowerF)
            # print("Apparent Power: ", AaparentPowerF)
            # print("Power Factor: ", PFF)
            # print("Frequency: ", FrecF, "\n")

            time.sleep(0.1)

        except ModbusIOException:
            count_erros += 1
            print(f"[{count_total}] No response from Slave ID: {slaveNum} (Timeout).")
        except ExceptionResponse as e:
            count_erros += 1
            print(f"[{count_total}] Slave ID: {slaveNum} responded with Modbus Exception ({e}).")
        except Exception as e:
            count_erros += 1
            print(f"An error occurred: {e}")

    # count_total += 1
    time.sleep(1)

    p = count_erros / count_total
    print(f"Prom. Acc.:, {(1 - p):.2%}")
