================================================================================
  ÍNDICE DE DOCUMENTACIÓN — PLATAFORMA OpenFMB (Proyecto PERSEO P4 / UdeA)
================================================================================

Este archivo describe brevemente el contenido de cada documento de este
directorio, para facilitar la navegación antes de abrirlos.

================================================================================
ARCHIVO 1 — Documentacion_plataforma_openfmb
================================================================================

DESCRIPCIÓN:
  Guía completa y detallada de la plataforma OpenFMB. Cubre TODO el ciclo de
  vida de la plataforma, desde la instalación inicial hasta la visualización
  de datos. Es el documento de referencia principal del proyecto.

TEMAS CUBIERTOS (por secciones):
  1.  Proyecto de referencia de OpenFMB — instalación de Docker, ejecución del
      demo y primera visualización en la interfaz HMI.
  2.  Conexión del medidor Schneider A9MEM3155 — cableado físico, configuración
      RS485-Ethernet, creación de ficheros YAML con herramienta OACT, fichero
      docker-compose.yml y visualización en HMI.
  3.  Factores de escala — cómo escalar registros desde el adaptador y desde HMI.
  4.  Acceso remoto al HMI — túnel SSH, Ubuntu Server, acceso desde Windows.
  5.  Medidores en cascada — conexión física de múltiples medidores y uso de
      'Templating' para escalar la configuración.
  6.  Escritura en registros Modbus — uso del emulador ModbusPal, plugins
      modbus-outstation y modbus-master, escritura con Python.
  7.  Control ON/OFF con Raspberry Pi 4 — escritura de coils, configuración
      del dispositivo, ficheros de configuración para control digital.
  8.  Puente NATS ↔ MQTT — configuración del adaptador como traductor entre
      ambos protocolos, publicadores/suscriptores en Python.
  9.  Conexión con base de datos — configuración de TimescaleDB con Docker,
      estructura de tabla SQL, configuración del adaptador para persistencia.
  10. Visualización con Grafana — conexión a TimescaleDB, dashboards, consultas.
  11. Escritura desde la interfaz HMI — control de registros y coils Modbus
      directamente desde los diagramas del HMI.
  12. Sistema de identificadores mRID — codificación y asignación de MRIDs
      dentro de la plataforma OpenFMB.

IR A ESTE ARCHIVO SI:  necesita instalar la plataforma, conectar un medidor
nuevo desde cero, entender la arquitectura general, o consultar cualquier
paso que no esté cubierto en los otros documentos.

================================================================================
ARCHIVO 2 — integrating MG assests to OpenFMB
================================================================================

DESCRIPCIÓN:
  Guía enfocada en integrar equipos específicos de la microrred de la UdeA a
  una plataforma OpenFMB ya configurada. Asume familiaridad con el entorno y
  complementa directamente el Archivo 1. Cada sección es un tipo de equipo.

EQUIPOS CUBIERTOS:
  1.  Medidores Schneider A9MEM3155 — uso de 'Templating' para instanciar
      múltiples medidores con un solo YAML, vinculación en HMI con 'Measure Box'
      y mapeo de registros (corriente, voltaje, potencias, factor de potencia).
  2.  Productos Modbus (relés de potencia) — mapeo de 12 coils, perfiles
      SwitchStatusProfile y SwitchDiscreteControlProfile, control desde HMI
      con icono 'Button'.
  3.  Dispositivo Color Control — estrategia de 4 archivos YAML (uno por
      esclavo: 100, 225, 245, 246), codificación de mRIDs, uso de archivos de
      soporte (.xlsx) del repositorio para localizar registros de lectura y
      escritura, control de set-point desde HMI.
  4.  Inversor Fronius — archivo modbus-fronius.yaml, archivo de soporte para
      registros de lectura, control de registros de escritura desde HMI,
      operación conjunta de registros (40243 habilitado por 40247).

IR A ESTE ARCHIVO SI:  necesita agregar un medidor Schneider, un relé de
potencia, el Color Control o el inversor Fronius a la plataforma; o si busca
el procedimiento de vinculación en HMI para un equipo existente.

================================================================================
ARCHIVO 3 — Documentation_Grafana_Api_OpenFMB
================================================================================

DESCRIPCIÓN:
  Documento técnico sobre los desarrollos de software realizados sobre 
  la interfaz grafica de OpenFMB (HMI de OpenFMB modificado para el Proyecto
  PERSEO P4). Cubre la arquitectura del sistema, instrucciones de instalación
  para Ubuntu y Windows, y detalle de cada feature desarrollado.

TEMAS CUBIERTOS:
  · Arquitectura del sistema — capas de comunicación: Modbus → adaptador
    OpenFMB → TimescaleDB → backend Rust (NATS/WebSocket) → frontend Angular
    → Grafana (iframe).
  · Estructura del repositorio — directorios Server/, Client/, config/, scripts/,
    Dockerfile, docker-compose.yml, timescaledb.sql.
  · Backend (Rust/warp/tokio) — autenticación JWT, actores riker, suscriptor
    NATS, publicador de comandos de control.
  · Frontend (Angular 15/mxGraph/NgRx) — módulos designer, hmi, store, shared.
  · Infraestructura Docker — servicios NATS, adapter, TimescaleDB, HMI.
  · Instalación ejecutable y desarrollo en Ubuntu y Windows (pasos detallados,
    versiones de software en apéndice).
  · Auto Zoom — método applyAutoZoom() en designer y HMI, ajuste de toolbar.
  · Imágenes institucionales — preparación SVG con Inkscape, registro en
    toolbar.json, listado de 27 imágenes añadidas (UdeA, GIMEL, GITA, aliados).
  · Interconexión Switch ↔ Set-Point — convención de codificación de mRIDs para
    bloqueo/desbloqueo de set-points desde interruptores.
  · Integración Grafana (GrafanaDialogComponent) — mapeo OpenFMB → columna
    PostgreSQL, generación automática de SQL, URL del iframe /d-solo/,
    configuración del dashboard hmi-measure-variable.json.
  · Comandos Docker y Git frecuentes, convención de nombres de código.
  · Versiones de software (Ubuntu y Windows) — tabla completa para reproducción.

IR A ESTE ARCHIVO SI:  necesita modificar el código del HMI, entender cómo
funciona la integración con Grafana, agregar imágenes al toolbar, reproducir
el entorno de desarrollo, o consultar versiones de software del proyecto.

================================================================================
ARCHIVO 4 — Uso_de_OpenFMB_API
================================================================================

DESCRIPCIÓN:
  Guía rápida para usar la librería Python 'openfmb-client' y acceder a la
  base de datos TimescaleDB del centro de control desde un script externo,
  a través de un túnel SSH. Es el punto de entrada para quien quiere leer
  datos de los dispositivos sin interactuar con el HMI.

PASOS CUBIERTOS (en orden):
  1.  Instalación — pip install del repositorio GitHub perseo-openfmb/
      openfmb-client y sus dependencias (requirements.txt).
  2.  Túnel SSH — comando completo para hacer port-forwarding de los puertos
      3000 (Grafana), 32771 (HMI) y 8000 (API) desde el servidor de control.
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

  ¿Instalar la plataforma desde cero?          → Archivo 1 (Secc. 1 y 2)
  ¿Conectar un medidor o equipo nuevo?          → Archivo 2
  ¿UUID / mRID de un equipo?                    → Archivo 1 (Secc. 12) o Archivo 4
  ¿Leer datos desde Python sin el HMI?          → Archivo 4
  ¿Modificar el código del HMI?                 → Archivo 3
  ¿Integrar Grafana al HMI?                     → Archivo 3 (Secc. 19)
  ¿Agregar imágenes al designer del HMI?        → Archivo 3 (Secc. 18.2)
  ¿Escalar registros Modbus?                    → Archivo 1 (Secc. 3)
  ¿Configurar base de datos TimescaleDB?        → Archivo 1 (Secc. 9)
  ¿Acceso remoto / túnel SSH?                   → Archivo 1 (Secc. 4) o Archivo 4
  ¿Versiones de software del proyecto?          → Archivo 3 (Secc. 24)
================================================================================
