# =============================================================================
# Dockerfile: Contenedor standalone para el SQL NaN Proxy
# =============================================================================
# Contenedor liviano que ejecuta proxy.py de forma independiente.
# Se conecta al contenedor 'timescaledb' (PostgreSQL) en la red de Docker.
#
# Uso:
#   docker compose build sql-proxy
#   docker compose up -d sql-proxy
#
# Para desactivar:
#   docker compose stop sql-proxy
#   (cambiar adapter.yaml: puerto 5433 → 5432, reiniciar adapter)
# =============================================================================
FROM python:3.11-alpine

# Crear directorio de trabajo
WORKDIR /app

# Copiar el script del proxy
COPY proxy.py /app/proxy.py

# Puerto de escucha del proxy
EXPOSE 5433

# Ejecutar el proxy con output sin buffer para logs en tiempo real
CMD ["python3", "-u", "/app/proxy.py"]
