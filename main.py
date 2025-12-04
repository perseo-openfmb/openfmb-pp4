"""
Author: Kevin Martinez
Date: 2025-12-03
Description: FastAPI application to interact with TimescaleDB.
This application includes endpoints to test the database connection
and retrieve the latest state of a device.
"""

from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import dotenv
import os
from datetime import datetime

dotenv.load_dotenv()  # Load environment variables from a .env file if needed

app = FastAPI()

# IMPORTANT: Inside Docker, we use the service name defined in docker-compose
# In your case, the service is called "timescale" (as you showed me before)
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_PORT = os.getenv("DB_PORT")

def get_db_connection():
    """
    Function to establish a connection to the database.
    Returns the connection object.
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT
        )
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None


# --- API ROUTES (ENDPOINTS) ---


@app.get("/")
def read_root():
    """Test route to verify that the API is working."""
    return {"message": "The TimescaleDB API is working!"}


@app.get("/test-db")
def test_db():
    """
    Route to test the connection to TimescaleDB.
    Returns the database version.
    """
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="Could not connect to the database")

    try:
        # Use 'with' to ensure the cursor is closed properly
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Execute a simple query
            cur.execute("SELECT version();")
            result = cur.fetchone()

        conn.close()  # Close the connection when finished
        return {"version_db": result}

    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error in query: {str(e)}")


@app.get("/devices/{device_uuid}/last-state")
def get_last_state(device_uuid: str):
    """
    Strategy 1: Returns the most recent measurement of a device.
    Useful to show the current real-time state.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Could not connect to the database")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT *
                FROM data
                WHERE device_uuid = %s
                ORDER BY "timestamp" DESC
                LIMIT 1;
            """
            cur.execute(query, (device_uuid,))
            result = cur.fetchone()

        conn.close()

        if not result:
            raise HTTPException(
                status_code=404, detail="Device not found or no measurements available"
            )

        return {"latest_measurement": result}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error in query: {str(e)}")


@app.get("/devices/{device_uuid}/historical")
def get_historical_data(device_uuid: str, limit: int = 100,
                        start: datetime = None, end: datetime = None):
    """
    Option 1:
    Finds the latest historical data for a device.

    Option 2:
    Finds historical data between two dates.
    Expected date format in URL: YYYY-MM-DDTHH:MM:SS (ISO 8601)

    Option 3:
    If no date range or date range is specified, returns all historical data for the device.

    Example usage:
        >>> /devices/{device_uuid}/historical?limit=50
    >>> /devices/{device_uuid}/historical?start=2023-01-01T00:00:00&end=2023-01-31T23:59:59
    >>> /devices/{device_uuid}/historical
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Could not connect to the database")

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if start and end:
                query = """
                    SELECT *
                    FROM data
                    WHERE device_uuid = %s
                    AND "timestamp" >= %s
                    AND "timestamp" <= %s
                    ORDER BY "timestamp" DESC
                """
                cur.execute(query, (device_uuid, start, end))
            elif limit:
                query = """
                    SELECT *
                    FROM data
                    WHERE device_uuid = %s
                    ORDER BY "timestamp" DESC
                    LIMIT %s
                """
                cur.execute(query, (device_uuid, limit))
            else:
                query = """
                    SELECT *
                    FROM data
                    WHERE device_uuid = %s
                    ORDER BY "timestamp" DESC
                    LIMIT ALL
                """
                cur.execute(query, (device_uuid,))

            results = cur.fetchall()

        conn.close()
        return {"historical": results}

    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error in query: {str(e)}")
