# Python 3.12: 3.9 llegó a fin de vida en octubre de 2025 y ya no recibe parches de seguridad
FROM python:3.12-slim

# Sin buffer en stdout/stderr (logs en tiempo real) y sin .pyc (imagen más limpia)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Versiones fijadas para builds reproducibles. La capa de dependencias va antes del COPY
# del código para que un cambio en app/ no obligue a reinstalar las librerías.
# Notas:
#   - asyncpg trae binarios precompilados, por lo que no se necesita gcc ni libpq-dev.
#   - La configuración se inyecta por variables de entorno (pydantic-settings);
#     no se usa python-dotenv en el contenedor.
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    uvicorn==0.39.0 \
    asyncpg==0.29.0 \
    pydantic==2.7.4 \
    pydantic-settings==2.3.0

# Solo el código de la API; el resto del repositorio no es necesario dentro de la imagen
COPY app/ ./app/

# La API no necesita privilegios de root
RUN useradd --create-home --shell /usr/sbin/nologin apiuser
USER apiuser

EXPOSE 8000

# Healthcheck sin dependencias extra (usa la stdlib de Python ya presente en la imagen)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
