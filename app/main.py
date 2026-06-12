"""
Autor: Kevin Martinez
Refactorización: Jaime / ChatGPT
Fecha: 2025-12-16
Descripción:
API refactorizada para generar documentación. Incluye endpoints para obtener datos históricos
Incluye:
- Corrección de la metadata de  OpenAPI
- Modelos de respuesta utilizando Pydantic
- Documentación de los endopints
"""

import os
import dotenv # manejo de las variables de entorno
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends 
from pydantic import BaseModel # manejo de los modelos de datos y validación de las respuestas
from typing import List, Optional, Dict, Any # manejo de los tipos de datos en las respuestas
from datetime import datetime # manejo de las fechas en los endpoints y modelos de datos
from uuid import UUID  # UUID generico
import asyncpg # cliente asíncrono para PostgreSQL
import json # manejo de los datos en formato JSON

dotenv.load_dotenv() # cargar las variables de entorno

# -----------------------------------------------------------------------------
# Database configuration
# -----------------------------------------------------------------------------

db_pool = None # pool de conexiones a la base de datos, se inicializa en el lifespan del FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    try:
        print("Iniciando pool...")
        db_pool = await asyncpg.create_pool(
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            min_size=1,
            max_size=20,
        )
        yield # el código después del yield se ejecutará al finalizar la aplicación, cerrando el pool de conexiones
    finally:
        if db_pool:
            await db_pool.close()

# instancia de fastapi
app = FastAPI(title="OpenFMB Async API", version="1.2.1", lifespan=lifespan)

async def get_db():
    """
    Función para obtener una configuración de conexión
    a la base de datos desde el pool.
    """
    if not db_pool:
        raise HTTPException(status_code=503, detail="DB not initialized")
    async with db_pool.acquire() as connection:
        yield connection

# -----------------------------------------------------------------------------
# Pydantic models (contratos de la API)
# -----------------------------------------------------------------------------


class Measurement(BaseModel):
    device_uuid: UUID  # Acepta tu formato '00000001...'
    timestamp: datetime
    data: Dict[str, Any]

class LatestMeasurementResponse(BaseModel):
    latest_measurement: Measurement

class HistoricalResponse(BaseModel):
    device_uuid: UUID
    count: int
    measurements: List[Measurement]

class DeviceListResponse(BaseModel):
    count: int
    device_uuids: List[UUID]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def normalize_json_value(value: Any) -> Dict[str, Any]:
    """
    Normaliza un valor JSON a un diccionario.

    Args:
        - value: El valor a normalizar, que puede ser un dict, una cadena JSON o None.

    Returns:
        - Un diccionario con los datos normalizados. Si el valor es None, se devuelve un diccionario vacío.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


# -----------------------------------------------------------------------------
# API Routes
# -----------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "OpenFMB Async API is running"}

@app.get("/test-db")
async def test_db(conn: asyncpg.Connection = Depends(get_db)):
    try:
        version = await conn.fetchval("SELECT version();")
        return {"database_version": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/devices/{device_uuid}/last-state", response_model=Dict[str, Any])
async def get_last_state(device_uuid: UUID, conn: asyncpg.Connection = Depends(get_db)):
    row = await conn.fetchrow(
        """
        SELECT device_uuid, timestamp, data
        FROM data
        WHERE device_uuid = $1
        ORDER BY timestamp DESC
        LIMIT 1;
        """,
        str(device_uuid),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    full_row = normalize_json_value(row["data"])
    full_row.setdefault("device_uuid", row["device_uuid"])
    full_row.setdefault("timestamp", row["timestamp"])
    return full_row

@app.get("/devices/{device_uuid}/historical", response_model=HistoricalResponse)
async def get_historical_data(
    device_uuid: UUID,
    limit: int = Query(100, ge=1, le=5000),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    conn: asyncpg.Connection = Depends(get_db),
):
    base_query = [
        "SELECT device_uuid, timestamp, data",
        "FROM data",
        "WHERE device_uuid = $1",
    ]
    args: List[Any] = [str(device_uuid)]
    next_arg = 2

    if start is not None:
        base_query.append(f"AND timestamp >= ${next_arg}")
        args.append(start)
        next_arg += 1
    if end is not None:
        base_query.append(f"AND timestamp <= ${next_arg}")
        args.append(end)
        next_arg += 1

    base_query.append("ORDER BY timestamp DESC")
    base_query.append(f"LIMIT ${next_arg}")
    args.append(limit)

    rows = await conn.fetch("\n".join(base_query), *args)

    measurements = [
        {
            "device_uuid": row["device_uuid"],
            "timestamp": row["timestamp"],
            "data": normalize_json_value(row["data"]),
        }
        for row in rows
    ]

    return {
        "device_uuid": device_uuid,
        "count": len(measurements),
        "measurements": measurements,
    }

@app.get("/devices", response_model=DeviceListResponse)
async def list_devices(conn: asyncpg.Connection = Depends(get_db)):
    rows = await conn.fetch(
        """
        SELECT DISTINCT device_uuid
        FROM data
        ORDER BY device_uuid;
        """
    )
    device_uuids = [row["device_uuid"] for row in rows]
    return {"count": len(device_uuids), "device_uuids": device_uuids}
