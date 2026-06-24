# Script for Modbus TCP Slave Emulator
# Author: Kevin D. Martinez Zapata
# Date: 2024-08-05
# Version: 2.2

import asyncio
import numpy as np
from pymodbus.server.async_io import StartAsyncTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
import logging
import random
import struct

# Constants
N_REGS = 5000                   # Number of registers
IP_ADDRESS = "192.168.0.108"      # IP address of the server
PORT = 5020                       # Port number of the server
SLEEP_TIME = 1                  # Sleep time in seconds
N_SLAVES = 6                    # Number of slaves

# Config de logging
logging.basicConfig()       # Configure logging
log = logging.getLogger()   # Get logger
log.setLevel(logging.DEBUG) # Set log level to debug

# Initialize multiple slaves
store = {}
for i in range(1, N_SLAVES + 1):
    store[i] = ModbusSlaveContext(
        di=ModbusSequentialDataBlock(0, [0]*N_REGS),  # Discrete Inputs (not used here)
        co=ModbusSequentialDataBlock(0, [0]*N_REGS),  # Coils (not used here)
        hr=ModbusSequentialDataBlock(0, [0]*N_REGS),  # Holding Registers
        ir=ModbusSequentialDataBlock(0, [0]*N_REGS)   # Input Registers (not used here)
    )

# Create server context with slaves and datastore
context = ModbusServerContext(slaves=store, single=False)

# Optional: Initialize server identity
identity = ModbusDeviceIdentification()                         # Create identity object
identity.VendorName = 'Pymodbus'                                # Set vendor name
identity.ProductCode = 'PM'                                     # Set product code
identity.VendorUrl = 'http://github.com/riptideio/pymodbus/'    # Set vendor URL
identity.ProductName = 'Pymodbus Server'                        # Set product name
identity.ModelName = 'Pymodbus Server'                          # Set model name
identity.MajorMinorRevision = '1.0'                             # Set major.minor.revision

# Windows
def clear():
    import os
    os.system('cls')

# Linux
# def clear():
#     import os
#     os.system('clear')

# Function for converting a floating value to two 16-bit registers
def float_to_registers(value):
    packed = struct.pack('<f', value)       # Pack floating value in 4 bytes in big-endian
    return struct.unpack('<HH', packed)     # Unpack 4 bytes in two 16-bit registers

# Asynchronous function for updating Modbus registers
async def update_registers():
    while True: # Infinite loop
        for i in range(1, N_SLAVES + 1):
            # Generate random values within specified ranges
            current_avg_value = random.uniform(0, 1)                        # Average Current in Amperes
            current_l1n_value = random.uniform(0, 1)                        # Current L1N in Amperes
            current_l2n_value = random.uniform(10, 20)                        # Current L2N in Amperes
            current_l3n_value = random.uniform(0, .5)                        # Current L3N in Amperes
            
            voltage_avg_value = random.uniform(123, 126)                    # Average Voltage in Volts
            voltage_l1n_value = random.uniform(123, 126)                    # Voltage L1N in Volts
            voltage_l2n_value = random.uniform(123, 126)                    # Voltage L2N in Volts
            voltage_l3n_value = random.uniform(123, 126)                    # Voltage L3N in Volts
            
            frequency_value = random.uniform(59, 61)                        # Frequency in Hertz
            PF_value = 1.                                                   # Power Factor
            
            active_global_power = random.uniform(0, 1)                      # Active Global Power in Watts
            reactive_global_power = 0.                                      # Reactive Global Power in VAr
            aparent_global_power = np.sqrt(active_global_power ** 2 + reactive_global_power ** 2) # Aparent Global Power in VA

            # Convert floating values to 16-bit registers
            current_avg_registers = float_to_registers(current_avg_value)
            current_l1n_registers = float_to_registers(current_l1n_value)
            current_l2n_registers = float_to_registers(current_l2n_value)
            current_l3n_registers = float_to_registers(current_l3n_value)
            
            voltage_avg_registers = float_to_registers(voltage_avg_value)
            voltage_l1n_registers = float_to_registers(voltage_l1n_value)
            voltage_l2n_registers = float_to_registers(voltage_l2n_value)
            voltage_l3n_registers = float_to_registers(voltage_l3n_value)
            
            frequency_registers = float_to_registers(frequency_value)
            PF_registers = float_to_registers(PF_value)
            
            active_power_registers = float_to_registers(active_global_power)
            reactive_power_registers = float_to_registers(reactive_global_power)
            aparent_power_registers = float_to_registers(aparent_global_power)

            # Write values to the registers for each slave
            # context[i].setValues(3, 3008, list(current_avg_registers))
            # context[i].setValues(3, 2998, list(current_l1n_registers))
            context[i].setValues(3, 3000, list(current_l2n_registers))
            # context[i].setValues(3, 3002, list(current_l3n_registers))
            
            # context[i].setValues(3, 3034, list(voltage_avg_registers))
            # context[i].setValues(3, 3026, list(voltage_l1n_registers))
            context[i].setValues(3, 3028, list(voltage_l2n_registers))
            # context[i].setValues(3, 3030, list(voltage_l3n_registers))
            
            # context[i].setValues(3, 3108, list(frequency_registers))
            # context[i].setValues(3, 3082, list(PF_registers))
            
            # context[i].setValues(3, 3058, list(active_power_registers))
            # context[i].setValues(3, 3066, list(reactive_power_registers))
            # context[i].setValues(3, 3074, list(aparent_power_registers))
            
            # if i == 3:
            #     irradiance_value = random.uniform(200, 250)                     # Irradiance in W/m^2
            #     iradiance_registers = float_to_registers(irradiance_value)  # Convert floating value to 16-bit registers
            #     context[i].setValues(3, 3110, list(iradiance_registers))    # Write value to the registers
            
            # context[i].setValues(3, 839, list(aparent_power_registers))
            # context[i].setValues(3, 840, list(aparent_power_registers))
            # context[i].setValues(3, 841, list(aparent_power_registers))
            # context[i].setValues(3, 842, list(aparent_power_registers))
            # context[i].setValues(3, 843, list(aparent_power_registers))
        # Wait for 1 secon
        await asyncio.sleep(SLEEP_TIME)

# Function for running the Modbus TCP server
async def run_server():
    update_task = asyncio.create_task(update_registers())   # Create task for updating registers
    await StartAsyncTcpServer(context,                      # Server context
                              identity,                     # Server identity
                              address=(                     # Server address
                                  IP_ADDRESS,               # IP address
                                  PORT                      # Port number
                                )
                            )
    await update_task                                       # Wait for update task to finish

# Main function
if __name__ == '__main__':
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass
    finally:
        clear()
        log.debug('Server stopped')