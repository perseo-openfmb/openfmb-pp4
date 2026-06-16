================================================================================
Uso_de_OpenFMB_API
================================================================================

DESCRIPCIÓN:
  Guía rápida para usar la librería Python 'openfmb-client' y acceder a la
  base de datos TimescaleDB del centro de control desde un script externo,
  a través de un túnel SSH. Es el punto de entrada para quien quiere leer
  datos de los dispositivos sin interactuar con el HMI.

PASOS CUBIERTOS (en orden):
  1.  Instalación — pip install del repositorio GitHub perseo-openfmb/ y sus dependencias (requirements.txt)
    - Crear entorno de python:  python3 -m venv mi_entorno
    - Activar entorno de python: source mi_entorno/bin/activate
    - (con el entorno activado)Instalar cliente OpenfMB: pip install git+https://github.com/perseo-openfmb/openfmb-client.git
    - Instalar requirements.txt: pip install -r requirements.txt
      
  2.  Túnel SSH — comando completo para hacer port-forwarding de los puertos
      3000 (Grafana), 32771 (HMI) y 8000 (API) desde el servidor de control.
    - ssh -J guest.user@smartcities.udea.edu.co:1784 operador@172.28.16.179 -p 22666 -L 3000:192.168.0.108:3000 -L 32771:192.168.0.108:32771 -L 8000:192 168.0.108:8000
  3.  Instanciar cliente — OpenFMBClient(base_url="http://localhost:8000/").
  4.  Leer último dato — client.get_last_state(device_uuid="...") devuelve
      un objeto con todas las variables del dispositivo.
  5.  Seleccionar variables — acceso por clave, p.ej. medidor["a_phsb_mag"]
      (corriente promedio) o medidor["ppv_phsbc_mag"] (potencia aparente total).
  6.  Tabla de correspondencia — listado de los 8 medidores del sistema con
      su nombre, UUID, dirección IP:puerto y número de esclavo Modbus.
  7.  Mapeo de variables — tabla completa de registros → nombre de variable
      para medidores Schneider y para medidores Siemens.
  8.  Documentación adicional — enlace al README del repositorio en GitHub.

IR A ESTE ARCHIVO SI:  quiere leer datos de los medidores desde un script
Python externo, necesita conocer los UUIDs de los dispositivos, o necesita
saber qué variable del objeto corresponde a qué medida eléctrica.

================================================================================
RESUMEN
================================================================================  
  ¿UUID / mRID de un equipo?       → Archivo 4
  ¿Acceso remoto / túnel SSH?      →  Archivo 4
  ¿Acceso a la base de datos?      →  Archivo 4
================================================================================
