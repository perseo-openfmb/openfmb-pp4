from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusIOException
from pymodbus.pdu import ExceptionResponse
import struct
import time

CLIENT_TYPE = "tcp"
HOST = "192.168.0.9"
PORT = 26
SLAVES = {20: 1000}
READ_COUNT = 2
PER_SLAVE_DELAY_SEC = 0.5
LOOP_DELAY_SEC = 12
READ_RETRY_ON_TIMEOUT = 2
ERROR_CORRECTION_ENABLED = False


def decode_float(registers):
    return struct.unpack(">f", struct.pack(">HH", registers[0], registers[1]))[0]


def decode_uint16(registers):
    return registers[0]


def read_slave(client, slave_id, register_address, read_count):
    result = client.read_holding_registers(
        address=register_address, count=read_count, slave=slave_id
    )
    if not result.isError():
        return "ok", decode_float(result.registers)
    if isinstance(result, ExceptionResponse):
        return "exception", result
    if isinstance(result, ModbusIOException):
        return "timeout", result
    return "error", result


def read_slave_with_retry(client, slave_id, register_address, read_count, retries):
    status, payload = read_slave(client, slave_id, register_address, read_count)
    if status != "timeout" or retries <= 0:
        return status, payload

    # Reconnect once and retry the read to mitigate transient socket issues.
    client.close()
    if not client.connect():
        return status, payload

    return read_slave(client, slave_id, register_address, read_count)


def main():
    if CLIENT_TYPE != "tcp":
        raise ValueError(f"Unsupported client type: {CLIENT_TYPE}")

    count_total = 0
    count_errors = 0
    client = ModbusTcpClient(host=HOST, port=PORT, timeout=2.0, retries=2)
    try:
        while True:
            if not client.connect():
                print("Could not connect to Modbus client. Retrying...")
                time.sleep(LOOP_DELAY_SEC)
                continue

            for slave_id in SLAVES.keys():
                count_total += 1
                status, payload = (
                    read_slave_with_retry(
                        client,
                        slave_id,
                        SLAVES[slave_id],
                        READ_COUNT,
                        READ_RETRY_ON_TIMEOUT,
                    )
                    if ERROR_CORRECTION_ENABLED
                    else read_slave(client, slave_id, SLAVES[slave_id], READ_COUNT)
                )

                if status == "ok":
                    print(f"[{count_total}] Slave ID: {slave_id}, Value: {payload}")
                elif status == "exception":
                    print(
                        f"[{count_total}] Slave ID: {slave_id} responded with Modbus Exception ({payload})."
                    )
                    count_errors += 1
                elif status == "timeout":
                    print(
                        f"[{count_total}] No response from Slave ID: {slave_id} (Timeout)."
                    )
                    count_errors += 1
                else:
                    print(f"[{count_total}] Error: {payload}")
                    count_errors += 1

                time.sleep(PER_SLAVE_DELAY_SEC)

            success_rate = (
                0.0 if count_total == 0 else (1 - (count_errors / count_total))
            )
            print(
                f"Total Attempts: {count_total}, Errors: {count_errors}, Success Rate: {success_rate:.2%}"
            )
            print("--" * 50)
            time.sleep(LOOP_DELAY_SEC)
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
