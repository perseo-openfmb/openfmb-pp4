from pymodbus.client import ModbusTcpClient
import asyncio
import struct

async def main():
    client = ModbusTcpClient(host='192.168.0.9', port=26)
    
    while not client.connect():
        print('Could not connect to the Modbus server. Retrying in 5 seconds...')
        await asyncio.sleep(5)

    print('Connected to Modbus server.')

    global reg

    try:
        try:

            _ = client.write_register(40242, 100, slave=21)
            await asyncio.sleep(2)
            _ = client.write_register(40246, 1, slave=21)
            await asyncio.sleep(2)
            volRegisters = client.read_holding_registers(40246, 1, slave=21)
            print("EN: ",volRegisters.registers[0])
            volRegisters = client.read_holding_registers(40242, 1, slave=21)
            # VoltageListF = struct.unpack(
            #     ">f",
            #     struct.pack(">HH", volRegisters.registers[0], volRegisters.registers[1]),
            # )[0]
            print(volRegisters.registers[0])

            await asyncio.sleep(1)

            if not client.is_socket_open():
                raise Exception('Connection lost.')

        except Exception as e:
            print(f'{e}: Attempting to reconnect...')
            client.close()
            
            while not client.connect():
                print('Could not connect to the Modbus server. Retrying in 5 seconds...')
                await asyncio.sleep(5)

            print('Reconnected to Modbus server.')

    except KeyboardInterrupt:
        print('Leaving...')
        client.close()

if __name__ == '__main__':
    asyncio.run(main())
