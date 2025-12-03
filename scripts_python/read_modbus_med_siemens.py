from pymodbus.client import ModbusTcpClient
from pymodbus.client import ModbusSerialClient
import struct

clientType = "tcp"
client = None

if clientType == "tcp":
    client = ModbusTcpClient("192.168.0.8", port=26)
elif clientType == "serial":
    client = ModbusSerialClient("COM3", baudrate=19200, bytesize=8, parity="N", stopbits=1, debug=True)
else:
    print("Client type not supported")
    exit()

# Modbus slave number
slaves = [13,14]
for slaveNum in slaves:

    try:
        # Connect to the client
        client.connect()

        # Read registers and convert to float
        #volRegisters = client.read_holding_registers(2999+28, 4, slave=slaveNum)
        #VoltageListF = struct.unpack(">f", struct.pack(">HH", volRegisters.registers[0], volRegisters.registers[1]))[0]

        #currRegisters = client.read_holding_registers(2999+0, 4, slave=slaveNum)
        #CurrentListF = struct.unpack(">f", struct.pack(">HH", currRegisters.registers[0], currRegisters.registers[1]))[0]

        activPowRegisters = client.read_holding_registers(19, 4, slave=slaveNum)
        ActivePowerF = struct.unpack(">f", struct.pack(">HH", activPowRegisters.registers[0], activPowRegisters.registers[1]))[0]
        #Potencia por fase

        #reactivPowRegisters = client.read_holding_registers(2999+68, 4, slave=slaveNum)
        #ReactivePowerF = struct.unpack(">f", struct.pack(">HH", reactivPowRegisters.registers[0], reactivPowRegisters.registers[1]))[0]

        #AparntPowRegisters = client.read_holding_registers(2999+76, 4, slave=slaveNum)
        #AaparentPowerF = struct.unpack(">f", struct.pack(">HH", AparntPowRegisters.registers[0], AparntPowRegisters.registers[1]))[0]

        #PFRegisters = client.read_holding_registers(2999+84, 4, slave=slaveNum)
        #PFF = struct.unpack(">f", struct.pack(">HH", PFRegisters.registers[0], PFRegisters.registers[1]))[0]

        #frecRegisters = client.read_holding_registers(2999+110, 4, slave=slaveNum)
        #FrecF = struct.unpack(">f", struct.pack(">HH", frecRegisters.registers[0], frecRegisters.registers[1]))[0]

        # Close the client connection
        client.close()

        # Print the results
        #print("\nVoltage: ", VoltageListF)
        #print("Current: ", CurrentListF)
        print("Power: ", ActivePowerF)
        #print("Reactive Power: ", ReactivePowerF)
        #print("Apparent Power: ", AaparentPowerF)
        #print("Power Factor: ", PFF)
        #print("Frequency: ", FrecF, "\n")

    except Exception as e:
        print("HUBO UN ERROR: ", e)
        client.close()
    
