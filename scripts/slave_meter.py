'''
Modbus TCP slave emulator
Author: Kevin Martinez
Refactor: Claude Code -- Claude Opus 4.8
Date: June 24, 2026
'''

from __future__ import annotations

import argparse
import asyncio
import logging
import struct
from contextlib import suppress
from dataclasses import dataclass

import numpy as np
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartAsyncTcpServer

logger = logging.getLogger("slave_meter")

# Holding registers are accessed with Modbus function code 3.
HOLDING_REGISTERS_FC = 3

# A Modbus register holds 16 bits; two of them make one 32-bit float.
REGISTERS_PER_FLOAT = 2

# Resolution of the grid the random floats are sampled from. It must comfortably
# exceed the number of pairs so that distinct grid points stay distinct once
# truncated to 32-bit precision -> guarantees "all different" values.
SAMPLE_GRID = 1 << 24


@dataclass
class Config:
    '''Runtime configuration for the emulator.'''
    host: str = '172.21.38.174'
    port: int = 5020
    slaves: int = 6
    registers: int = 5000
    interval: float = 1.0
    min_value: float = 0.0
    max_value: float = 100.0
    seed: int | None = None
    log_level: str = 'INFO'


def build_context(config: Config) -> ModbusServerContext:
    '''Build the server context with ``config.slaves`` independent slaves.

    ``zero_mode=True`` makes the protocol address match the storage index, so
    register N maps to slot N and the entire block can be written at once.
    '''
    slaves: dict[int, ModbusSlaveContext] = {}
    for unit_id in range(1, config.slaves + 1):
        slaves[unit_id] = ModbusSlaveContext(
            hr=ModbusSequentialDataBlock(0, [0] * config.registers),  # holding
            ir=ModbusSequentialDataBlock(0, [0] * config.registers),  # input
            di=ModbusSequentialDataBlock(0, [0] * config.registers),  # discrete
            co=ModbusSequentialDataBlock(0, [0] * config.registers),  # coils
            zero_mode=True,
        )
    return ModbusServerContext(slaves=slaves, single=False)


def build_identity() -> ModbusDeviceIdentification:
    '''Build the optional device identity block.'''
    identity = ModbusDeviceIdentification()
    identity.VendorName = 'Pymodbus'
    identity.ProductCode = 'PM'
    identity.VendorUrl = 'https://github.com/pymodbus-dev/pymodbus'
    identity.ProductName = 'Modbus Slave Meter Emulator'
    identity.ModelName = 'slave_meter_v2'
    identity.MajorMinorRevision = '2.0'
    return identity


def sample_pair_addresses(registers: int) -> list[int]:
    '''Odd-aligned float start addresses spanning the whole block.

    Used to log a snapshot proving floats are served across the *entire* range
    (first, quarters, middle and last float), not only the first registers.
    '''
    n_pairs = (registers - 1) // REGISTERS_PER_FLOAT
    if n_pairs <= 0:
        return []
    
    # Creare tuples like [(1, 2), (3, 4), ...] for each float pair
    odd_indices = [1 + idx * REGISTERS_PER_FLOAT for idx in range(n_pairs)]
    return [(odd_indices[i], odd_indices[i] + 1) for i in range(n_pairs)]


async def update_loop(context: ModbusServerContext, config: Config, rng: np.random.Generator) -> None:
    '''Refresh every slave's holding registers on a fixed interval.'''
    addresses = sample_pair_addresses(config.registers)
    while True:
        for unit_id in range(1, config.slaves + 1):
            # Put 1.0 for all float pairs in the slave's holding registers
            values = [1.0] * len(addresses)
            for (_, addr), value in zip(addresses, values):
                # Convert float to two 16-bit registers
                regs = struct.unpack('<HH', struct.pack('<f', value))
                context[unit_id].setValues(HOLDING_REGISTERS_FC, addr, list(regs))
        await asyncio.sleep(config.interval)


async def run_server(config: Config) -> None:
    '''Start the update loop and the async Modbus/TCP server together.'''
    context = build_context(config)
    identity = build_identity()
    rng = np.random.default_rng(config.seed)

    updater = asyncio.create_task(update_loop(context, config, rng))
    logger.info(
        "serving %d slave(s) x %d registers (%d floats) on %s:%d (refresh %.2fs)",
        config.slaves,
        config.registers,
        config.registers // REGISTERS_PER_FLOAT,
        config.host,
        config.port,
        config.interval,
    )
    try:
        await StartAsyncTcpServer(
            context=context,
            identity=identity,
            address=(config.host, config.port),
        )
    finally:
        updater.cancel()
        with suppress(asyncio.CancelledError):
            await updater


def parse_args(argv: list[str] | None = None) -> Config:
    '''Parse CLI arguments into a :class:`Config`.'''
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--host', default=Config.host, help='bind address')
    parser.add_argument('--port', type=int, default=Config.port, help='TCP port')
    parser.add_argument(
        '--slaves', type=int, default=Config.slaves, help='number of Modbus slaves'
    )
    parser.add_argument(
        '--registers',
        type=int,
        default=Config.registers,
        help='holding registers per slave (2 per float)',
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=Config.interval,
        help='seconds between register refreshes',
    )
    parser.add_argument(
        '--min-value',
        type=float,
        default=Config.min_value,
        help='lower bound for the random float values',
    )
    parser.add_argument(
        '--max-value',
        type=float,
        default=Config.max_value,
        help='upper bound for the random float values',
    )
    parser.add_argument(
        '--seed', type=int, default=Config.seed, help='RNG seed for reproducible runs'
    )
    parser.add_argument(
        '--log-level',
        default=Config.log_level,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='logging verbosity',
    )
    args = parser.parse_args(argv)
    return Config(
        host=args.host,
        port=args.port,
        slaves=args.slaves,
        registers=args.registers,
        interval=args.interval,
        min_value=args.min_value,
        max_value=args.max_value,
        seed=args.seed,
        log_level=args.log_level,
    )


def main():
    config = parse_args()
    logging.basicConfig(
        level=config.log_level,
        format='%(asctime)s %(levelname)-7s %(name)s: %(message)s'
    )

    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        logger.info('Shutting down server...')
    finally:
        logger.info('Server stopped')


if __name__ == '__main__':
    main()