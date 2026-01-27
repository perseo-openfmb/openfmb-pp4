# 1. Usamos una imagen base oficial de Python ligera
FROM python:3.9-slim

# 2. Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Instalamos las dependencias del sistema necesarias para psycopg2
RUN apt-get update && apt-get install -y libpq-dev gcc

# 4. Copiamos los archivos de tu proyecto al contenedor
COPY . /app

# 5. Instalamos las librerías de Python
RUN pip install --no-cache-dir fastapi uvicorn asyncpg python-dotenv pydantic-settings

# 6. Exponemos el puerto por donde escuchará la API
EXPOSE 8000

# 7. Comando para iniciar la API cuando arranque el contenedor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
