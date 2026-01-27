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
import dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID # UUID generico
import asyncpg
import json

dotenv.load_dotenv()

# -----------------------------------------------------------------------------
# Database configuration
# -----------------------------------------------------------------------------

db_pool = None
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
        yield
    finally:
        if db_pool:
            await db_pool.close()

app = FastAPI(title="OpenFMB Async API", version="1.2.1", lifespan=lifespan)

async def get_db():
    if not db_pool:
        raise HTTPException(status_code=503, detail="DB not initialized")
    async with db_pool.acquire() as connection:
        yield connection

# -----------------------------------------------------------------------------
# Pydantic models (contratos de la API)
# -----------------------------------------------------------------------------

class Measurement(BaseModel):
    device_uuid: UUID # Acepta tu formato '00000001...'
    timestamp: datetime
    data: Dict[str, Any]

class HistoricalResponse(BaseModel):
    device_uuid: UUID
    count: int
    measurements: List[Measurement]

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

@app.get("/devices/{device_uuid}/last-state", response_model=Dict[str, Measurement])
async def get_last_state(
    device_uuid: UUID, 
    conn: asyncpg.Connection = Depends(get_db)
):
    row = await conn.fetchrow(
        """
        SELECT device_uuid, timestamp, to_jsonb(data) as data
        FROM data
        WHERE device_uuid = $1
        ORDER BY timestamp DESC
        LIMIT 1;
        """,
        str(device_uuid)
    )

    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    # Retornar el resultado como un diccionario
    return {"latest_measurement": {
        "device_uuid": row["device_uuid"],
        "timestamp": row["timestamp"],
        "data": json.loads(row["data"])
    }}

@app.get("/devices/{device_uuid}/historical", response_model=HistoricalResponse)
async def get_historical_data(
    device_uuid: UUID,
    limit: int = Query(100, ge=1, le=5000),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    conn: asyncpg.Connection = Depends(get_db)
):
    base_query = """
        SELECT device_uuid, timestamp, to_jsonb(data) as data
        FROM data
        WHERE device_uuid = $1
    """
    args = [str(device_uuid)]
    
    if start and end:
        base_query += " AND timestamp BETWEEN $2 AND $3"
        args.extend([start, end])
        base_query += " ORDER BY timestamp DESC LIMIT $4"
        args.append(limit) 
    else:
        base_query += " ORDER BY timestamp DESC LIMIT $2"
        args.append(limit)

    rows = await conn.fetch(base_query, *args)

    measurements = [
        {
            "device_uuid": row["device_uuid"],
            "timestamp": row["timestamp"],
            "data": json.loads(row["data"])
        }
        for row in rows
    ]

    return {
        "device_uuid": device_uuid,
        "count": len(measurements),
        "measurements": measurements,
    }
