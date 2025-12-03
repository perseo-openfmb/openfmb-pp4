from fastapi import FastAPI, HTTPException
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import dotenv
import os

dotenv.load_dotenv()  # Cargar variables de entorno desde un archivo .env si es necesario

app = FastAPI()

# IMPORTANTE: Dentro de Docker, usamos el nombre del servicio definido en docker-compose
# En tu caso, el servicio se llama "timescale" (según lo que me mostraste antes)
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_PORT = os.getenv("DB_PORT")

def get_db_connection():
    """
    Función para establecer conexión con la base de datos.
    Retorna el objeto de conexión.
    """
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            port=DB_PORT
        )
        return conn
    except Exception as e:
        print(f"Error conectando a la base de datos: {e}")
        return None

# --- RUTAS DE LA API (ENDPOINTS) ---

@app.get("/")
def read_root():
    """Ruta de prueba para verificar que la API funciona."""
    return {"mensaje": "¡La API de TimescaleDB está funcionando!"}

@app.get("/test-db")
def test_db():
    """
    Ruta para probar la conexión a TimescaleDB.
    Devuelve la versión de la base de datos.
    """
    conn = get_db_connection()
    if conn is None:
        raise HTTPException(status_code=500, detail="No se pudo conectar a la base de datos")

    try:
        # Usamos 'with' para asegurar que el cursor se cierre correctamente
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Ejecutamos una consulta simple
            cur.execute("SELECT version();")
            result = cur.fetchone()
            
        conn.close() # Cerramos la conexión al terminar
        return {"version_db": result}
        
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error en la consulta: {str(e)}")

# Ejemplo de consulta de datos (Ajustar según tus tablas reales)
# @app.get("/ejemplo-consulta")
# def get_data():
#     conn = get_db_connection()
#     if not conn:
#         raise HTTPException(status_code=500, detail="Error de conexión")
    
#     try:
#         with conn.cursor(cursor_factory=RealDictCursor) as cur:
#             # IMPORTANTE: Cambia 'nombre_tabla' por una tabla real que tengas
#             # TimescaleDB usa SQL estándar
#             query = "SELECT * FROM nombre_tabla LIMIT 10;" 
#             cur.execute(query)
#             rows = cur.fetchall()
            
#         conn.close()
#         return {"data": rows}
#     except Exception as e:
#         conn.close()
#         return {"error": str(e), "nota": "Asegúrate de cambiar 'nombre_tabla' en el código"}