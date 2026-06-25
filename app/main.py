'''
Autor:             Kevin Martinez
Revisado por:      Jaime Vergara
Refactorizado por: Claude Opus 4.8
Fecha:             2026-06-25

API asíncrona de SOLO LECTURA para extraer mediciones OpenFMB almacenadas en
TimescaleDB (tabla `data`, de columnas anchas: una columna numérica por cada
magnitud MMXU).

Prioridades del refactor: seguridad, simplicidad y mínima carga.
  - Configuración tipada con pydantic-settings (falla rápido si falta una
    credencial); sin python-dotenv.
  - Pool de conexiones asyncpg gestionado en el lifespan y guardado en
    `app.state` (sin variables globales).
  - Las columnas `numeric` se decodifican como float (JSON limpio, menos
    overhead que Decimal).
  - No se filtran detalles internos de error al cliente; se registran con el
    módulo logging.
  - Los valores `null` se conservan: en el histórico las franjas sin dato
    (errores/desconexiones) quedan visibles.

Convención de estilo: todas las cadenas usan comillas simples.
'''

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, List, Optional
from uuid import UUID

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger('openfmb_api')


# -----------------------------------------------------------------------------
# Configuración (tipada; falla al arrancar si falta una credencial obligatoria)
# -----------------------------------------------------------------------------
class Settings(BaseSettings):
    '''Parámetros leídos de variables de entorno (o de un .env en desarrollo).

    Los nombres se mapean sin distinguir mayúsculas: `db_user` <- `DB_USER`, etc.
    '''

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=False,
    )

    db_user: str
    db_pass: str
    db_name: str
    db_host: str
    db_port: int = 5432
    db_pool_min: int = 1
    db_pool_max: int = 10


settings = Settings()


# -----------------------------------------------------------------------------
# Ciclo de vida: pool de conexiones a la base de datos
# -----------------------------------------------------------------------------
async def _init_connection(conn: asyncpg.Connection) -> None:
    '''Inicializa cada conexión del pool.

    Decodifica las columnas `numeric` como `float` para devolver números JSON
    nativos (más livianos que `Decimal`). La precisión de float64 es más que
    suficiente para magnitudes eléctricas.
    '''
    await conn.set_type_codec(
        'numeric',
        encoder=str,
        decoder=float,
        schema='pg_catalog',
        format='text',
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    '''Crea el pool de conexiones al arrancar y lo cierra al apagar.'''
    logger.info('Inicializando pool de conexiones a la base de datos...')
    app.state.db_pool = await asyncpg.create_pool(
        user=settings.db_user,
        password=settings.db_pass,
        database=settings.db_name,
        host=settings.db_host,
        port=settings.db_port,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
        init=_init_connection,
    )
    try:
        yield
    finally:
        logger.info('Cerrando pool de conexiones...')
        await app.state.db_pool.close()


async def get_db(request: Request) -> AsyncIterator[asyncpg.Connection]:
    '''Entrega una conexión del pool durante la petición y la libera al terminar.'''
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire() as connection:
        yield connection


# -----------------------------------------------------------------------------
# Modelos Pydantic (contratos de la API)
# -----------------------------------------------------------------------------
class MeasurementData(BaseModel):
    '''Magnitudes eléctricas (MMXU) de una lectura.

    Todos los campos son opcionales y se devuelven como `null` cuando el medidor
    no reporta esa magnitud o el dispositivo está desconectado. En el histórico
    los `null` se conservan, de modo que las franjas de tiempo sin dato quedan
    visibles. Nombres = columnas de la tabla `data`.
    '''

    model_config = ConfigDict(extra='ignore')

    # Corriente — A
    a_net_mag: Optional[float] = None
    a_neut_mag: Optional[float] = None
    a_phsa_mag: Optional[float] = None
    a_phsb_mag: Optional[float] = None
    a_phsc_mag: Optional[float] = None

    # Frecuencia — Hz
    hz_mag: Optional[float] = None

    # Factor de potencia — PF
    pf_neut_mag: Optional[float] = None
    pf_net_mag: Optional[float] = None
    pf_phsa_mag: Optional[float] = None
    pf_phsb_mag: Optional[float] = None
    pf_phsc_mag: Optional[float] = None

    # Tensión fase-neutro — PhV (magnitud y ángulo)
    phv_neut_mag: Optional[float] = None
    phv_neut_ang: Optional[float] = None
    phv_net_mag: Optional[float] = None
    phv_net_ang: Optional[float] = None
    phv_phsa_mag: Optional[float] = None
    phv_phsa_ang: Optional[float] = None
    phv_phsb_mag: Optional[float] = None
    phv_phsb_ang: Optional[float] = None
    phv_phsc_mag: Optional[float] = None
    phv_phsc_ang: Optional[float] = None

    # Tensión fase-fase — PPV (magnitud y ángulo)
    ppv_phsab_mag: Optional[float] = None
    ppv_phsab_ang: Optional[float] = None
    ppv_phsbc_mag: Optional[float] = None
    ppv_phsbc_ang: Optional[float] = None
    ppv_phsca_mag: Optional[float] = None
    ppv_phsca_ang: Optional[float] = None

    # Potencia aparente — VA
    va_neut_mag: Optional[float] = None
    va_net_mag: Optional[float] = None
    va_phsa_mag: Optional[float] = None
    va_phsb_mag: Optional[float] = None
    va_phsc_mag: Optional[float] = None

    # Potencia reactiva — VAr
    var_neut_mag: Optional[float] = None
    var_net_mag: Optional[float] = None
    var_phsa_mag: Optional[float] = None
    var_phsb_mag: Optional[float] = None
    var_phsc_mag: Optional[float] = None

    # Potencia activa — W
    w_neut_mag: Optional[float] = None
    w_net_mag: Optional[float] = None
    w_phsa_mag: Optional[float] = None
    w_phsb_mag: Optional[float] = None
    w_phsc_mag: Optional[float] = None


class Measurement(BaseModel):
    '''Una fila de la tabla `data`: metadatos de la lectura más sus magnitudes.'''

    message_uuid: UUID
    device_uuid: UUID
    timestamp: datetime
    tagname: str
    data: MeasurementData


class HistoricalResponse(BaseModel):
    '''Respuesta de la consulta histórica de un dispositivo.'''

    device_uuid: UUID
    count: int
    measurements: List[Measurement]


class DeviceListResponse(BaseModel):
    '''Listado de dispositivos que tienen datos en la base.'''

    count: int
    device_uuids: List[UUID]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _row_to_measurement(row: asyncpg.Record) -> Measurement:
    '''Convierte una fila de `data` (`SELECT *`) en un modelo Measurement.

    Las columnas de metadatos se toman por nombre; el resto se entrega a
    `MeasurementData`, que ignora las claves que no sean magnitudes.
    '''
    return Measurement(
        message_uuid=row['message_uuid'],
        device_uuid=row['device_uuid'],
        timestamp=row['timestamp'],
        tagname=row['tagname'],
        data=MeasurementData.model_validate(dict(row)),
    )


# -----------------------------------------------------------------------------
# Aplicación y rutas
# -----------------------------------------------------------------------------
app = FastAPI(
    title='OpenFMB Async API',
    version='2.0.0',
    description='API de solo lectura para extraer mediciones OpenFMB desde TimescaleDB.',
    lifespan=lifespan,
)


@app.get('/', summary='Información del servicio')
async def root() -> dict[str, str]:
    '''Endpoint informativo de disponibilidad (sin acceso a la base de datos).'''
    return {'message': 'OpenFMB Async API is running'}


@app.get('/health', summary='Estado de salud')
async def health(conn: asyncpg.Connection = Depends(get_db)) -> dict[str, str]:
    '''Verifica la conectividad con la base de datos sin exponer detalles internos.'''
    try:
        await conn.fetchval('SELECT 1;')
    except Exception:
        logger.exception('Falló el chequeo de salud contra la base de datos')
        raise HTTPException(status_code=503, detail='database unavailable')
    return {'status': 'ok'}


@app.get('/devices', response_model=DeviceListResponse, summary='Listar dispositivos')
async def list_devices(conn: asyncpg.Connection = Depends(get_db)) -> DeviceListResponse:
    '''Devuelve los `device_uuid` distintos presentes en la tabla `data`.'''
    rows = await conn.fetch('SELECT DISTINCT device_uuid FROM data ORDER BY device_uuid;')
    device_uuids = [row['device_uuid'] for row in rows]
    return DeviceListResponse(count=len(device_uuids), device_uuids=device_uuids)


@app.get(
    '/devices/{device_uuid}/last-state',
    response_model=Measurement,
    summary='Última lectura de un dispositivo',
)
async def get_last_state(
    device_uuid: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> Measurement:
    '''Última medición registrada para el dispositivo (404 si no tiene datos).'''
    row = await conn.fetchrow(
        '''
        SELECT *
        FROM data
        WHERE device_uuid = $1
        ORDER BY timestamp DESC
        LIMIT 1;
        ''',
        device_uuid,
    )
    if row is None:
        raise HTTPException(status_code=404, detail='Device not found')
    return _row_to_measurement(row)


@app.get(
    '/devices/{device_uuid}/historical',
    response_model=HistoricalResponse,
    summary='Histórico de un dispositivo',
)
async def get_historical_data(
    device_uuid: UUID,
    limit: int = Query(100, ge=1, le=5000, description='Máximo de filas a devolver'),
    start: Optional[datetime] = Query(None, description='Inicio del rango (ISO 8601)'),
    end: Optional[datetime] = Query(None, description='Fin del rango (ISO 8601)'),
    conn: asyncpg.Connection = Depends(get_db),
) -> HistoricalResponse:
    '''Histórico de mediciones de un dispositivo en un rango de tiempo opcional.

    Los valores `null` se conservan tal como están en la base de datos, por lo
    que las franjas sin dato (errores o desconexiones) quedan visibles. El rango
    `start`/`end` es opcional; `limit` acota el número de filas (más recientes).
    '''
    clauses = ['SELECT *', 'FROM data', 'WHERE device_uuid = $1']
    args: List[Any] = [device_uuid]

    if start is not None:
        args.append(start)
        clauses.append(f'AND timestamp >= ${len(args)}')
    if end is not None:
        args.append(end)
        clauses.append(f'AND timestamp <= ${len(args)}')

    args.append(limit)
    clauses.append('ORDER BY timestamp DESC')
    clauses.append(f'LIMIT ${len(args)}')

    rows = await conn.fetch('\n'.join(clauses), *args)
    measurements = [_row_to_measurement(row) for row in rows]
    return HistoricalResponse(
        device_uuid=device_uuid,
        count=len(measurements),
        measurements=measurements,
    )
