# SQL NaN Proxy para OpenFMB Adapter

## Problema que resuelve

El adapter (`oesinc/openfmb.adapters:a30d1d0`) es un binario pre-compilado de C++
que construye INSERT SQL con el token `nan` (sin comillas) para campos con valor
NaN:

```sql
INSERT INTO data (..., tagname, ...)
VALUES (..., 'MeterReadingProfile', nan) ON CONFLICT ...
```

PostgreSQL interpreta `nan` como un **identificador de columna** y rechaza la query:

```
ERROR: column "nan" does not exist
```

Esto generaba **~77,000+ errores por hora** en los logs del adapter. El adapter
es un binario cerrado que no se puede modificar, y el esquema de la tabla `data`
no puede cambiar.

### Por qué no se puede resolver sin el proxy

Se descartaron todas las alternativas a nivel PostgreSQL:

| Alternativa | Por qué no funciona |
|---|---|
| Parámetro de PG (`nan_as_null`) | No existe. No hay configuración para tratar `nan` como NULL |
| Trigger BEFORE INSERT | Los triggers se ejecutan DESPUÉS del parse SQL. Si el parse falla, el trigger nunca se ejecuta |
| Columna dummy `nan` en la tabla | El adapter envía columnas específicas, no incluye "nan" en la lista. Además corrompe el esquema del hypertable |
| Función `nan()` | El adapter escribe `nan` SIN paréntesis. El parser lo ve como identificador, no como llamada a función |
| Extensión de PostgreSQL (C) | Extremadamente frágil, rompe con cada upgrade de PG, y es mucho más complejo que el proxy |
| Otra imagen de TimescaleDB | Ninguna versión de PostgreSQL treat `nan` como valor válido. Es comportamiento del parser SQL del estándar |
| Modificar el adapter | Binario cerrado, sin fuente, sin opción de rebuild. Solo el vendor (oesinc) podría cambiarlo |

El proxy TCP es la solución correcta: ligero (~250 líneas Python), microsegundos
de latencia, y opera en el nivel exacto donde el problema ocurre (wire protocol).

---

## Arquitectura actual

```
                          ┌─────────────────────────┐
                          │  docker network          │
                          │                          │
  Dispositivos Modbus ──→ │ adapter (:5433) ────────→│── sql-proxy ──→ timescaledb (:5432)
                          │                          │                   │
                          └─────────────────────────┘                   │
                                                                       ▼
                                                                   tabla "data"
                                                                       │
                          ┌────────────────────────────────────────────┤
                          │                                            │
                     Grafana (:3000)                          pgAdmin (:80)
                     API Python (:8000)                       db-backup
                     (conexión directa a :5432)
```

### Por qué no se usó protobuf

El proxy **no necesita** Protocol Buffers. El flujo de datos es:

```
Dispositivos Modbus → adapter (deserializa protobuf, genera SQL) → PostgreSQL
```

Cuando el SQL llega al proxy por el wire protocol, el protobuf ya fue desserializado.
El proxy solo ve texto SQL crudo por la conexión TCP.

---

## Cómo funciona el proxy (`proxy.py`)

### PostgreSQL Wire Protocol v3

El PostgreSQL wire protocol v3 tiene dos fases:

**Fase de Startup:**
```
Cliente → Servidor: StartupMessage (NO tiene byte de tipo)
  Formato: [length:4][protocol_version:4][key\0value\0...]\0
Servidor → Cliente: AuthenticationOk, ParameterStatus, ReadyForQuery
```

**Fase de Queries:**
```
Cliente → Servidor: 'Q' + [length:4] + [sql\0]           (Simple Query)
Cliente → Servidor: 'P' + [length:4] + [stmt\0][sql\0]   (Parse/Extended)
Servidor → Cliente: respuestas (RowDescription, DataRow, CommandComplete, etc.)
```

Importante:
- El **StartupMessage** no tiene byte de tipo — comienza directamente con la longitud
- El byte de tipo **`Q`** (0x51) indica Simple Query Protocol
- El byte de tipo **`P`** indica Extended Query Protocol (Parse)
- El campo **`length`** incluye sus propios 4 bytes pero **NO** el type byte

### Framing message-by-message

El proxy lee **exactamente un mensaje** PostgreSQL por iteración usando `read_pg_message()`,
que parsea el type byte y el length field para leer la cantidad exacta de bytes:

```python
async def read_pg_message(reader, startup_done):
    if not startup_done:
        # StartupMessage: sin type byte, solo [length:4][payload]
        length_bytes = await read_exact(reader, 4)
        length = struct.unpack("!I", length_bytes)[0]
        payload = await read_exact(reader, length - 4)
        return length_bytes + payload, True
    else:
        # Mensaje normal: [type:1][length:4][payload]
        type_byte = await reader.read(1)
        length_bytes = await read_exact(reader, 4)
        length = struct.unpack("!I", length_bytes)[0]
        payload = await read_exact(reader, length - 4)
        return type_byte + length_bytes + payload, True
```

Esto es crítico porque el proxy necesitaba reescribir mensajes individuales
(reconstruir el `Query` con el SQL modificado). Si se leyera un chunk crudo de TCP
(con `reader.read(65536)`), múltiples mensajes podrían llegar juntos y el proxy
los procesaría incorrectamente.

### Detección de SSLRequest

Antes del StartupMessage, el adapter (libpq) puede enviar un **SSLRequest**:
```
[0x00, 0x00, 0x00, 0x00, 0x00, 0x03, 0x00, 0x00]  (8 bytes, código 80877103)
```

El proxy lee los primeros 8 bytes del adapter:
- Si el código (bytes 4-7) es `80877103` → es SSLRequest → responde con `N` (no SSL)
- El adapter luego envía el StartupMessage por el mismo reader

### Intercepción de queries

El proxy crea dos relay tasks por cada conexión:

```python
asyncio.create_task(relay_to_pg(client_reader, pg_writer, peer))
asyncio.create_task(relay_from_pg(pg_reader, client_writer, peer))
```

Solo `relay_to_pg` inspecciona y procesa mensajes. `relay_from_pg` es passthrough puro.

Dentro de `relay_to_pg`, para cada mensaje:

```
1. read_pg_message() → lee un mensaje completo del adapter
2. classify_client_msg() → identifica tipo (Query, Parse, Bind, etc.)
3. process_client_message() → si es Q o P, busca "nan" y reemplaza por "NULL"
4. Envía el mensaje (original o modificado) a PostgreSQL
```

### Reescritura de SQL (`rewrite_sql`)

La función `rewrite_sql()` reemplaza tokens bare `nan` por `NULL`:

1. Verifica si `nan` aparece en algún lugar del SQL (check rápido, case-insensitive)
2. Divide el SQL por comillas simples (`'`)
3. Las partes en posiciones pares (0, 2, 4...) están **fuera de comillas** → se aplica regex
4. Las partes en posiciones impares (1, 3, 5...) están **dentro de comillas** → no se tocan

**Regex:** `(?<!')\bnan\b(?!')` con `re.IGNORECASE`

Detecta `nan`, `NaN`, `NAN` como tokens standalone (word boundary \b), no dentro de
palabras como "banana", y no entre comillas simples.

### Reconstrucción de mensajes (y el bug off-by-1)

Para `Query` (`Q`): se reemplaza el SQL manteniendo el formato:
```
'Q' + [length:4] + [new_sql\0]
```

**El campo `length` debe ser `4 + len(sql\0)` — NO incluye el type byte.**

```python
# CORRECTO:
def rebuild_query_message(new_sql: str) -> bytes:
    sql_bytes = new_sql.encode("utf-8") + b"\x00"
    length = 4 + len(sql_bytes)  # ← solo sus propios 4 bytes
    return b"Q" + struct.pack("!I", length) + sql_bytes
```

Para `Parse` (`P`): se preserva el statement name y los param OIDs originales:
```
'P' + [length:4] + [stmt_name\0] + [new_sql\0] + [num_params:2] + [param_oids]
```

---

## Bugs encontrados y corregidos

### 1. Off-by-1 en `rebuild_query_message` (BUG CRÍTICO)

**Problema:** El campo `length` se calculaba como `1 + 4 + len(sql_bytes)` incluyendo
el type byte `Q`. PostgreSQL espera que `length` solo incluya sus propios 4 bytes.

**Consecuencia:** PostgreSQL lee `length - 4` bytes del payload, que es **1 byte más**
de lo disponible. PG se cuelga esperando ese byte extra que nunca llega.

**Efecto observable:** El adapter enviaba 8 queries, 7 sin NaN (forward as-is, length
correcto) y 1 con NaN (reescrita, length corrupto). Las 7 primeras respondían con
`CmdComplete`, la 8a colgaba. El adapter nunca recibía la respuesta y dejaba de
enviar queries. Resultado: ~7-8 inserciones al reiniciar, luego silencio total.

```
23:33:02 adapter→PG #3 [Query] 602 bytes     → PG responde CmdComplete ✓
23:33:02 adapter→PG #4 [Query] 591 bytes     → PG responde CmdComplete ✓
23:33:02 adapter→PG #5 [Query] 362 bytes     → PG responde CmdComplete ✓
...
23:33:02 adapter→PG #9 [Query] 389 bytes     → PG responde CmdComplete ✓
23:33:03 adapter→PG #10 [Query] 243 REWRITTEN → PG SE CUELGA (length corrupto)
23:33:03          adapter espera respuesta... infinitamente
23:33:11          EOF → conexión rota
```

**Solución:** Cambiar `length = 1 + 4 + len(...)` a `length = 4 + len(...)` en
ambas funciones `rebuild_query_message` y `rebuild_parse_message`.

### 2. Proxy leía chunks crudos sin framing correcto

**Problema:** La versión inicial del proxy usaba `reader.read(MAX_MSG_SIZE)` que
retorna un chunk de bytes del TCP sin respetar fronteras de mensajes. Si múltiples
mensajes llegaban juntos y el primero contenía NaN, `rebuild_query_message` creaba
un mensaje con solo el primer SQL — los mensajes siguientes se perdían silenciosamente.

**Solución:** Reescritura completa con `read_pg_message()` que lee exactamente un
mensaje PostgreSQL por iteración, usando el length field del protocolo.

### 3. StartupMessage sin type byte

**Problema:** El StartupMessage de PostgreSQL no tiene byte de tipo (a diferencia de
todos los demás mensajes). La función `read_pg_message()` original esperaba un type
byte en la posición 0, causando que el parser leyera los 4 bytes del length como
un type byte inválido.

**Solución:** `read_pg_message()` acepta un flag `startup_done` que indica si el
primer mensaje (sin type byte) ya fue procesado.

### 4. `set(b"...")` crea set de ints

**Problema:** `_CLIENT_MSG_TYPES = set(b"...")` crea un `set` de enteros en Python 3.
La comparación `data[0] == b"Q"` falla porque `81 != b"Q"`.

**Solución:** `{ord(c) for c in "QBESDCXTRFKnpyd"}` crea un set de enters correctamente.

### 5. SSLRequest antes del StartupMessage

**Problema:** El adapter (libpq) envía un SSLRequest de 8 bytes antes del StartupMessage.

**Solución:** Leer los primeros 8 bytes. Si el código es `80877103` → responder con `N`.
Si no es SSLRequest, preservar los bytes con `_PrefixedReader`.

---

## Configuración de infraestructura (docker-compose)

### PostgreSQL: shared_buffers y max_locks

```yaml
timescale:
  image: timescale/timescaledb:latest-pg12-oss
  command: ["postgres", "-c", "max_locks_per_transaction=256", "-c", "shared_buffers=1GB"]
```

| Parámetro | Valor original | Valor actual | Por qué |
|---|---|---|---|
| `shared_buffers` | 3957MB | **1GB** | Con 4062 chunks de TimescaleDB, PostgreSQL mataba procesos por OOM (exit 137). El adaptive memory allocation de PG con tantos chunks necesitaba espacio para operaciones, no solo para caches |
| `max_locks_per_transaction` | 64 (default) | **256** | TimescaleDB con 4062 chunks necesita muchos locks por transacción (un lock por chunk afectado). Default de PG era insuficiente |

### Adapter: max-queued-messages

```yaml
timescaledb:
  max-queued-messages: 100000
```

Buffer grande para soportar caídas temporales de PostgreSQL. Cuando PG se caía
(antes del fix de OOM), el adapter perdía mensajes encolados. Con 100K de buffer,
el adapter puede acumular datos durante una caída y reenviarlos al reconectar.

### Servicio sql-proxy (contenedor separado)

```yaml
sql-proxy:
  build:
    context: ./scripts/sql-proxy
    dockerfile: Dockerfile
  container_name: sql-proxy
  restart: unless-stopped
  ports:
    - "5433:5433"
  depends_on:
    timescale:
      condition: service_healthy
```

El proxy corre como **contenedor independiente** de TimescaleDB. Esto permite:
- Reiniciar el proxy sin reiniciar la BD
- Logging independiente
- Separación de responsabilidades

### adapter.yaml

```yaml
timescaledb:
  enabled: true
  database-url: postgresql://postgres:password@sql-proxy:5433/openfmb
  store-measurement: true
  table-name: data
  store-raw-message: false
  raw-table-name: raw_data
  raw-data-format: 0
  max-queued-messages: 100000
  connect-retry-seconds: 2
  data-store-interval-seconds: 5
```

---

## Flujo completo de una inserción

```
1. Adapter lee registros Modbus (cada ~5s por dispositivo)
   [modbus-master] Starting transaction: poll sequence
   [modbus-master] Finished transaction: poll sequence

2. Adapter construye INSERT SQL:
   INSERT INTO data (..., tagname, ...)
   VALUES (..., 'MeterReadingProfile', nan) ON CONFLICT ...

3. Adapter envía por wire protocol v3:
   [0x51][00 00 00 EA][INSERT INTO data ...\x00]
    ^Q    ^length=234   ^sql + null terminator

4. Proxy recibe el mensaje con read_pg_message():
   → Lee exactamente 1 + 4 + 230 = 235 bytes
   → Clasifica: "Query"

5. Proxy busca "nan" con rewrite_sql():
   → "nan" → "NULL" (solo fuera de comillas simples)

6. Proxy reconstruye con rebuild_query_message():
   [0x51][00 00 00 EF][INSERT INTO data ...NULL...\x00]
    ^Q    ^length=235   ^sql con NULL + null terminator
                         (4 + 231 = 235, CORRECTO)

7. PostgreSQL recibe, parsea, ejecuta:
   → CommandComplete("INSERT 0 1")
   → ReadyForQuery('I')

8. Proxy reenvía respuesta al adapter
   → Adapter loguea: "Successfully inserted 1 row(s) into data."
```

---

## Archivos involucrados

| Archivo | Rol |
|---|---|
| `scripts/sql-proxy/proxy.py` | Proxy TCP principal (~250 líneas Python, framing message-by-message) |
| `scripts/sql-proxy/Dockerfile` | Imagen `python:3.11-alpine` standalone |
| `scripts/sql-proxy/README.md` | Este documento |
| `docker-compose.yml` | Servicios timescale (image), sql-proxy (build), adapter, nats, etc. |
| `config/adapter.yaml` | Línea 546: `database-url` → puerto 5433, línea 552: `max-queued-messages: 100000` |
| `sql/timescaledb.sql` | Esquema de la tabla `data` (47 columnas, hypertable) |

---

## Verificación y debugging

### Ver logs del proxy en tiempo real

```bash
docker logs -f sql-proxy 2>&1
```

### Ver NAN rewrites recientes

```bash
docker logs sql-proxy --since 5m 2>&1 | grep "NAN"
```

Ejemplo:
```
[sql-proxy] 2026-07-14 23:40:23 NAN #1 rewritten
[sql-proxy] 2026-07-14 23:40:28 NAN #2 rewritten
[sql-proxy] 2026-07-14 23:40:33 NAN #3 rewritten
```

### Verificar cero errores de NaN

```bash
docker logs adapter --since 5m 2>&1 | grep -c 'column "nan"'
# Debe ser: 0
```

### Verificar inserciones continuas

```bash
docker logs adapter --since 5m 2>&1 | grep -c "Successfully inserted"
```

### Verificar datos en la tabla

```bash
docker exec timescaledb psql -U postgres -d openfmb \
  -c "SELECT count(*) as total, max(timestamp) as ultimo,
       now() - max(timestamp) as gap FROM data;"
```

### Verificar conexión adapter → proxy → PG

```bash
docker exec sql-proxy netstat -tnp 2>/dev/null
```

Debería mostrar:
```
tcp  ESTABLISHED  proxy:5433  ← adapter:XXXXX
tcp  ESTABLISHED  proxy:XXXXX ← timescaledb:5432
```

### Resumen rápido

```bash
echo "=== Errores nan (debe ser 0) ===" && \
docker logs adapter --since 5m 2>&1 | grep -c 'column "nan"' && \
echo "=== Inserciones exitosas ===" && \
docker logs adapter --since 5m 2>&1 | grep -c "Successfully inserted" && \
echo "=== Proxy NAN rewrites ===" && \
docker logs sql-proxy --since 5m 2>&1 | grep -c "NAN" && \
echo "=== Ultima insercion ===" && \
docker exec timescaledb psql -U postgres -d openfmb -t \
  -c "SELECT now() - max(timestamp) FROM data;"
```

---

## Servicios que NO pasan por el proxy

| Servicio | Puerto | Conexión |
|---|---|---|
| Grafana | 3000 | → timescaledb:**5432** (directo) |
| pgAdmin | 80 | → timescaledb:**5432** (directo) |
| API Python | 8000 | → timescaledb:**5432** (directo) |
| db-backup | — | → timescaledb:**5432** (directo) |
| **Adapter** | — | → **sql-proxy:5433** (proxy) |

Solo el adapter pasa por el proxy porque es la única fuente del bug `nan`.

---

## Contexto del adapter

El adapter binario (`oesinc/openfmb.adapters:a30d1d0`) es un programa de C++
que:

1. Recibe datos de dispositivos Modbus a través de sesiones definidas en
   `modbus-master/*.yaml` (9 archivos YAML)
2. Serializa los datos usando Protocol Buffers internamente
3. Publica los datos en NATS
4. Consume sus propios mensajes de NATS y genera INSERT SQL a PostgreSQL

El adapter es **completamente cerrado** — no hay acceso al código fuente ni
posibilidad de modificarlo.

### Análisis de dispositivos Modbus

| Dispositivo | UnitId | % de timeouts | Diagnóstico |
|---|---|---|---|
| `meter-schneider` | 0x18, 0x16 | **87%** | Timeout físico del bus Modbus |
| `piranometro` | 0x0C | 8% | Timeout físico del bus Modbus |
| `meter-siemens` | 0x0D, 0x0E | 4% | Respuestas inesperadas |
| `fronius` | — | 1% | Normal |

Los timeouts de Modbus son un problema físico (cable, terminación, dirección
incorrecta del dispositivo), no del software. Cuando un dispositivo no responde,
el adapter genera un INSERT con `nan` para los campos de ese dispositivo.
