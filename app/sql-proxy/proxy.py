#!/usr/bin/env python3
"""
SQL NaN Proxy para OpenFMB Adapter
Properly frames PostgreSQL wire protocol v3 messages.
"""

import asyncio
import struct
import re
import sys
import logging
import signal

LISTEN_PORT = 5433
PG_HOST = "timescaledb"
PG_PORT = 5432

logging.basicConfig(
    level=logging.INFO,
    format="[sql-proxy] %(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("sql-proxy")

# glibc imprime NaN como "nan"/"-nan" y los infinitos como "inf"/"-inf"
# (otros runtimes usan "infinity"). El signo debe absorberse en el reemplazo,
# o quedaria "-NULL" (error de sintaxis en PostgreSQL).
#
# Scanner de un solo paso: las alternativas de "protected" capturan regiones
# que deben copiarse intactas (strings E'...', literales '...', identificadores
# "..." y dollar-quoting); solo los tokens nan/inf que quedan fuera de esas
# regiones se reemplazan por NULL. En el dollar-quoting, el tag admite vacio
# ("|") en vez de "?" para que el backreference funcione con $$...$$.
_SQL_SCAN_RE = re.compile(
    r"""
      (?P<protected>
          E'(?:[^'\\]|\\.|'')*'                        # string E'...' (escapes \)
        | '(?:[^']|'')*'                               # literal ('' = comilla)
        | "(?:[^"]|"")*"                               # identificador "..."
        | \$(?P<tag>[A-Za-z_]\w*|)\$.*?\$(?P=tag)\$    # dollar-quoting
      )
    | (?P<bad>[-+]?\b(?:nan|inf(?:inity)?)\b)
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def rewrite_sql(sql: str) -> tuple:
    low = sql.lower()
    if "nan" not in low and "inf" not in low:
        return sql, False
    changed = False

    def _replace(m):
        nonlocal changed
        if m.group("bad"):
            changed = True
            return "NULL"
        return m.group(0)

    return _SQL_SCAN_RE.sub(_replace, sql), changed


# Limite superior del campo length; PostgreSQL impone el mismo (1 GiB).
# Un length fuera de [4, MAX] solo puede venir de trafico corrupto o malicioso
# y desincronizaria el framing (o intentaria reservar GBs de memoria).
MAX_PG_MSG_LEN = 1 << 30


class ProtocolError(Exception):
    """Frame invalido en el wire protocol; la conexion no puede continuar."""


async def read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


async def read_pg_message(reader: asyncio.StreamReader, startup_done: bool) -> tuple:
    """
    Read exactly one PostgreSQL wire protocol message.
    Returns (message_bytes, is_startup).
    Returns (b'', False) on EOF.
    
    startup_done=False: first message is StartupMessage (no type byte)
    startup_done=True: normal message with type byte

    Lanza ProtocolError si el campo length es invalido. Un EOF a mitad de
    mensaje descarta el fragmento y se reporta como EOF (b"").
    """
    head = b""
    if startup_done:
        head = await reader.read(1)
        if not head:
            return b"", False

    length_bytes = await read_exact(reader, 4)
    if len(length_bytes) < 4:
        if head or length_bytes:
            log.warning(
                "EOF a mitad de frame: %d bytes de cabecera descartados",
                len(head) + len(length_bytes),
            )
        return b"", True

    length = struct.unpack("!I", length_bytes)[0]
    if not 4 <= length <= MAX_PG_MSG_LEN:
        raise ProtocolError("campo length invalido: %d" % length)

    payload_len = length - 4
    payload = b""
    if payload_len > 0:
        payload = await read_exact(reader, payload_len)
        if len(payload) < payload_len:
            log.warning(
                "EOF a mitad de frame: payload incompleto (%d de %d bytes), descartado",
                len(payload), payload_len,
            )
            return b"", True

    return head + length_bytes + payload, True


def classify_client_msg(data: bytes) -> str:
    if not data:
        return "EOF"
    b = data[0]
    names = {
        ord("Q"): "Query", ord("P"): "Parse", ord("B"): "Bind",
        ord("E"): "Execute", ord("S"): "Sync", ord("D"): "Describe",
        ord("C"): "Close", ord("H"): "Flush", ord("X"): "Terminate",
        ord("d"): "CopyData", ord("c"): "CopyDone", ord("f"): "CopyFail",
    }
    if b in names:
        return names[b]
    if len(data) >= 8:
        ver = struct.unpack("!I", data[4:8])[0]
        if ver in {0x30000, 0x30001, 0x30002, 0x30003}:
            return "StartupMsg"
    return f"Client(0x{b:02x})"


def classify_server_msg(data: bytes) -> str:
    if not data:
        return "EOF"
    b = data[0]
    names = {
        ord("R"): "Auth", ord("K"): "BackendKey",
        ord("T"): "RowDesc", ord("D"): "DataRow",
        ord("C"): "CmdComplete", ord("Z"): "ReadyQuery",
        ord("I"): "EmptyQuery", ord("N"): "Notice",
        ord("E"): "Error", ord("s"): "PortalSuspended",
        ord("t"): "ParamDesc", ord("1"): "ParseComplete",
        ord("2"): "BindComplete", ord("3"): "CloseComplete",
        ord("W"): "Notify",
    }
    return names.get(b, f"Server(0x{b:02x})")


def extract_query_sql(data: bytes) -> str:
    sql_bytes = data[5:-1]
    return sql_bytes.decode("utf-8", errors="replace")


def extract_parse_sql(data: bytes) -> str:
    payload = data[5:]
    stmt_end = payload.index(b"\x00")
    sql_start = stmt_end + 1
    sql_end = payload.index(b"\x00", sql_start)
    sql_bytes = payload[sql_start:sql_end]
    return sql_bytes.decode("utf-8", errors="replace")


def rebuild_query_message(new_sql: str) -> bytes:
    sql_bytes = new_sql.encode("utf-8") + b"\x00"
    length = 4 + len(sql_bytes)
    return b"Q" + struct.pack("!I", length) + sql_bytes


def rebuild_parse_message(original: bytes, new_sql: str) -> bytes:
    payload = original[5:]
    stmt_end = payload.index(b"\x00")
    sql_start = stmt_end + 1
    sql_end = payload.index(b"\x00", sql_start)
    stmt_name = payload[:stmt_end + 1]
    sql_bytes = new_sql.encode("utf-8") + b"\x00"
    rest = payload[sql_end + 1:]
    new_payload = stmt_name + sql_bytes + rest
    length = 4 + len(new_payload)
    return b"P" + struct.pack("!I", length) + new_payload


def process_client_message(msg: bytes) -> bytes:
    if not msg:
        return msg

    first_byte = msg[0]

    if first_byte == ord("Q"):
        try:
            sql = extract_query_sql(msg)
            new_sql, changed = rewrite_sql(sql)
            if changed:
                log.info("NAN REWRITTEN [Query] | %s", sql.strip()[:200])
                return rebuild_query_message(new_sql)
        except Exception as exc:
            log.error("Error processing Query: %s", exc)

    elif first_byte == ord("P"):
        try:
            sql = extract_parse_sql(msg)
            new_sql, changed = rewrite_sql(sql)
            if changed:
                log.info("NAN REWRITTEN [Parse] | %s", sql.strip()[:200])
                return rebuild_parse_message(msg, new_sql)
        except Exception as exc:
            log.error("Error processing Parse: %s", exc)

    return msg


class _PrefixedReader:
    def __init__(self, prefix: bytes, original: asyncio.StreamReader):
        self._prefix = prefix
        self._original = original

    async def read(self, n: int = -1) -> bytes:
        if self._prefix:
            if n == -1:
                result = self._prefix
                self._prefix = b""
                return result
            elif n <= len(self._prefix):
                result = self._prefix[:n]
                self._prefix = self._prefix[n:]
                return result
            else:
                result = self._prefix
                self._prefix = b""
                remaining = n - len(result)
                more = await self._original.read(remaining)
                return result + more
        return await self._original.read(n)


async def relay_to_pg(
    client_reader, pg_writer, peer,
):
    """Read messages from adapter, process nan, forward to PG."""
    count = 0
    rewritten = 0
    startup_done = False

    try:
        while True:
            msg, startup_done_this = await read_pg_message(client_reader, startup_done)
            if startup_done_this:
                startup_done = True
            if not msg:
                log.info("adapter→PG: EOF after %d messages", count)
                break

            msg_name = classify_client_msg(msg)
            out = process_client_message(msg)
            if out is not msg:
                rewritten += 1
                log.info("NAN #%d rewritten", rewritten)

            count += 1
            if count <= 3 or count % 100 == 0:
                log.info(
                    "adapter→PG #%d [%s] %d bytes%s",
                    count, msg_name, len(msg),
                    " REWRITTEN" if out is not msg else "",
                )

            pg_writer.write(out)
            await pg_writer.drain()

    except asyncio.CancelledError:
        log.info("adapter→PG: cancelled after %d msgs", count)
    except ProtocolError as exc:
        log.error("adapter→PG: frame invalido tras %d msgs, cerrando conexion: %s", count, exc)
    except (ConnectionResetError, BrokenPipeError) as exc:
        log.info("adapter→PG: connection lost after %d msgs: %s", count, exc)
    except Exception as exc:
        log.error("adapter→PG error after %d msgs: %s", count, exc, exc_info=True)
    finally:
        pg_writer.close()
        log.info("adapter→PG cerrada | msgs=%d rewritten=%d", count, rewritten)


async def relay_from_pg(
    pg_reader, client_writer, peer,
):
    """Read raw bytes from PG, forward to adapter (passthrough)."""
    count = 0

    try:
        while True:
            data = await pg_reader.read(65536)
            if not data:
                log.info("PG→adapter: EOF after %d messages", count)
                break

            count += 1
            if count <= 3 or count % 100 == 0:
                msg_name = classify_server_msg(data)
                log.info("PG→adapter #%d [%s] %d bytes", count, msg_name, len(data))

            client_writer.write(data)
            await client_writer.drain()

    except asyncio.CancelledError:
        log.info("PG→adapter: cancelled after %d msgs", count)
    except (ConnectionResetError, BrokenPipeError) as exc:
        log.info("PG→adapter: connection lost after %d msgs: %s", count, exc)
    except Exception as exc:
        log.error("PG→adapter error after %d msgs: %s", count, exc, exc_info=True)
    finally:
        client_writer.close()
        log.info("PG→adapter cerrada | msgs=%d", count)


async def handle_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
):
    peer = client_writer.get_extra_info("peername")
    log.info("=== Nueva conexion desde %s ===", peer)

    try:
        # Todo primer mensaje valido mide >= 8 bytes (SSLRequest=8,
        # CancelRequest=16, StartupMessage>=9), asi que exigir 8 es seguro.
        first_data = await asyncio.wait_for(client_reader.readexactly(8), timeout=5.0)
        code = struct.unpack("!I", first_data[4:8])[0]
        if code == 80877103:
            client_writer.write(b"N")
            await client_writer.drain()
            log.info("SSLRequest rechazado desde %s", peer)
        else:
            client_reader = _PrefixedReader(first_data, client_reader)
    except asyncio.IncompleteReadError:
        log.warning("Conexion cerrada antes del primer mensaje completo desde %s", peer)
        client_writer.close()
        return
    except asyncio.TimeoutError:
        log.warning("Timeout esperando primer mensaje desde %s", peer)
        client_writer.close()
        return
    except Exception as exc:
        log.error("Error leyendo primer mensaje desde %s: %s", peer, exc)
        client_writer.close()
        return

    pg_reader = None
    pg_writer = None
    for attempt in range(10):
        try:
            pg_reader, pg_writer = await asyncio.open_connection(PG_HOST, PG_PORT)
            break
        except Exception as exc:
            if attempt < 9:
                log.info("PG no listo (intento %d/10), reintentando en 2s...", attempt + 1)
                await asyncio.sleep(2)
            else:
                log.error("No se pudo conectar a PG despues de 10 intentos: %s", exc)
                client_writer.close()
                return

    task_to_pg = asyncio.create_task(
        relay_to_pg(client_reader, pg_writer, peer)
    )
    task_from_pg = asyncio.create_task(
        relay_from_pg(pg_reader, client_writer, peer)
    )

    done, pending = await asyncio.wait(
        [task_to_pg, task_from_pg],
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    log.info("=== Conexion desde %s cerrada ===", peer)


async def main():
    server = await asyncio.start_server(
        handle_client,
        "0.0.0.0",
        LISTEN_PORT,
        reuse_address=True,
    )

    log.info("=" * 60)
    log.info("SQL NaN Proxy arrancado")
    log.info("  Escuchando en:  0.0.0.0:%d", LISTEN_PORT)
    log.info("  PostgreSQL en:  %s:%d", PG_HOST, PG_PORT)
    log.info("  Funcion:        reemplazar nan/inf -> NULL en INSERTs")
    log.info("  Framing:        message-by-message (proper wire protocol)")
    log.info("=" * 60)

    # start_server() ya deja el servidor aceptando conexiones; se espera la
    # senal con un Event en vez de serve_forever(), cuya cancelacion via
    # server.close() propagaria CancelledError hasta asyncio.run.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    log.info("Senal de apagado recibida, cerrando proxy...")
    server.close()
    await server.wait_closed()
    log.info("Proxy cerrado correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
