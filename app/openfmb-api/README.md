# OpenFMB API

API asíncrona (FastAPI + asyncpg) para consultar mediciones almacenadas en TimescaleDB.

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Health check |
| GET | `/test-db` | Verifica conexión a PostgreSQL |
| GET | `/devices` | Lista todos los `device_uuid` registrados |
| GET | `/devices/{uuid}/last-state` | Última medición de un dispositivo |
| GET | `/devices/{uuid}/historical` | Histórico con filtros `start`, `end`, `limit` (max 5000) |

## Variables de entorno

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `DB_USER` | Usuario PostgreSQL | `postgres` |
| `DB_PASS` | Contraseña PostgreSQL | `(del .env)` |
| `DB_NAME` | Base de datos | `openfmb` |
| `DB_HOST` | Host de la BD | `sql-proxy` (o `timescale` directo) |
| `DB_PORT` | Puerto de la BD | `5433` (proxy) o `5432` (directo) |

## Infraestructura

```
API (:8000) ──→ sql-proxy (:5433) ──→ timescaledb (:5432)
```

La API se conecta al proxy para ser consistente con el adapter. Si se necesita
conexión directa, cambiar `DB_HOST=timescale` y `DB_PORT=5432`.

## Ejecución

```bash
# Producción (Docker)
docker compose up mi-api-python --build

# Desarrollo local
pip install fastapi uvicorn asyncpg pydantic python-dotenv
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Ejemplos de uso

```bash
# Listar dispositivos
curl http://localhost:8000/devices

# Última medición
curl http://localhost:8000/devices/00000001-0001-0020-0000-000000000001/last-state

# Histórico (últimas 100 mediciones)
curl "http://localhost:8000/devices/00000001-0001-0020-0000-000000000001/historical?limit=100"

# Histórico con rango de fechas
curl "http://localhost:8000/devices/00000001-0001-0020-0000-000000000001/historical?start=2026-07-01T00:00:00&end=2026-07-24T23:59:59&limit=500"
```
