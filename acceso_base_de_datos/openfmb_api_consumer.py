from openfmb_client.client import OpenFMBClient
import pandas as pd
from datetime import datetime, timedelta
import re

def cargar_configuracion():
    
    CONFIG_ARCHIVOS = {
        'schneider': 'mapeo_variables_openfmb_api_sch.csv',
        'siemens': 'mapeo_variables_openfmb_api_sie.csv',
        'fronius': 'mapeo_variables_openfmb_api_Fron.csv',
        'color control': 'mapeo_variables_openfmb_api_CC.csv',
        'pyranometro': 'mapeo_variables_openfmb_api_pyra.csv'
    }

    # 1. Pre-cargar todos los CSVs en memoria para consultarlos fácilmente
    dataframes_mapos = {}
    for clave, archivo in CONFIG_ARCHIVOS.items():
        try:
            dataframes_mapos[clave] = pd.read_csv(archivo, sep=';').dropna(subset=['Variable'])
        except Exception as e:
            print(f"Advertencia: No se pudo cargar {archivo}: {e}")

    equipos = {}
    mapas_variables = {} # Ahora la clave será el UUID, no la marca

    try:
        df_equipos = pd.read_csv('identificadores_microrred.csv', sep=';').dropna(subset=['Identificador'])

        for _, row in df_equipos.iterrows():
            uuid = row['Identificador'].strip()
            nombre_dispositivo = row['Dispositivo'].strip()
            nombre_lower = nombre_dispositivo.lower()

            # Identificar qué archivo CSV le corresponde
            tipo_match = 'generico'
            for clave in CONFIG_ARCHIVOS.keys():
                if clave in nombre_lower:
                    tipo_match = clave
                    break
            
            equipos[uuid] = {
                'nombre': nombre_dispositivo,
                'tipo': tipo_match,
                'ip': row.get('Direccion IP:puerto', '')
            }

            # 2. Filtrar y asignar variables ESPECÍFICAS para este UUID
            mapas_variables[uuid] = {}
            
            if tipo_match in dataframes_mapos:
                df_mapa = dataframes_mapos[tipo_match]
                
                # Buscar si el nombre del equipo tiene un sub-identificador en paréntesis
                # Ej: "Color Control (Inv. Quattro - Baterías)" -> "Inv. Quattro - Baterías"
                match_parentesis = re.search(r'\((.*?)\)', nombre_dispositivo)
                
                for _, fila_var in df_mapa.iterrows():
                    nombre_var = str(fila_var['Variable']).strip()
                    item_code = str(fila_var['item']).strip()
                    
                    if match_parentesis:
                        # Si hay paréntesis, EXIGIMOS que ese texto esté en la variable
                        sub_id = match_parentesis.group(1).strip().lower()
                        if sub_id in nombre_var.lower():
                            mapas_variables[uuid][nombre_var] = item_code
                    else:
                        # Si es un dispositivo normal sin paréntesis (ej. Pyranometro), 
                        # cargamos todas las variables de su archivo.
                        mapas_variables[uuid][nombre_var] = item_code

    except Exception as e:
        print(f"Error cargando configuración: {e}")

    return equipos, mapas_variables


def listar_dispositivos():
    """Retorna la lista de dispositivos formateada."""
    lista = []
    for uuid, datos in EQUIPOS_DICT.items():
        lista.append({'nombre': datos['nombre'], 'id': uuid})
    return lista

def obtener_ultimo_valor(uuid):
    """Obtiene el último valor y lo mapea según la marca del equipo."""
    if uuid not in EQUIPOS_DICT:
        print(f"Error: UUID {uuid} no reconocido en configuración.")
        return {}

    # 1. Obtener datos crudos de la API
    try:
    
        last_state = CLIENT.get_last_state(uuid)
    except Exception as e:
        print(f"Error API: {e}")
        return {}

    # 2. Identificar qué mapa usar
    tipo_equipo = EQUIPOS_DICT[uuid]['tipo'] # 'schneider' o 'siemens'
    mapa_variables = MAPAS_DICT.get(uuid, {})


    # 3. Construir respuesta limpia
    resultado = {'timestamp': last_state.get('timestamp', {})}

    for nombre_var, item_code in mapa_variables.items():      
        if not pd.isna(item_code):
            valor = last_state.get(item_code.lower())
            if valor is not None:
                resultado[nombre_var.lower()] = valor
    
    return resultado

def obtener_historial(uuid, start_date=None, end_date=None, days=0, weeks=0, hours=0, minutes=0, limit=100):
    """
    Obtiene historial.
    Soporta fechas exactas (start_date, end_date) O tiempo relativo.
    """
    if uuid not in EQUIPOS_DICT:
        print(f"Error: UUID {uuid} no reconocido.")
        return []

    # --- Lógica de Fechas ---
    if start_date and end_date:
        f_inicio, f_fin = start_date, end_date
    else:
        f_fin = datetime.now()
        delta = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)
        if delta.total_seconds() == 0: delta = timedelta(hours=1) # Default 1 hora
        f_inicio = f_fin - delta

    try:
        history = CLIENT.get_historical_data(
            device_uuid=uuid, 
            start=f_inicio, 
            end=f_fin, 
            limit=limit
        )
    except Exception as e:
        print(f"Error API: {e}")
        return []

    valores_procesados = []
    
    tipo_equipo = EQUIPOS_DICT[uuid]['tipo']
    mapa_variables = MAPAS_DICT.get(uuid, {})

    for registro in history:
        fila = {'timestamp': registro.get('timestamp', {})}
        datos_api = registro.get('data', {})
        
        for nombre_var, item_code in mapa_variables.items():

            if not pd.isna(item_code):
                val = datos_api.get(item_code.lower())
                if val is not None:
                    fila[nombre_var] = val
        
        valores_procesados.append(fila)

    return valores_procesados

###################################################################################
#instanciar consumidor de OpenFMB API 
CLIENT = OpenFMBClient(base_url="http://172.28.16.179:8000/")

#cargar archivos de apoyo (dispositivos y mapeo)
EQUIPOS_DICT, MAPAS_DICT = cargar_configuracion()

#Validacion de API activa
if not CLIENT.check_health():
        print("OpenFMB API detenida.")
        exit()
###################################################################################

###################################################################################
######################listado de dispositivos disponibles
lista_dip = listar_dispositivos()

print("total de dispositivos: ", len(lista_dip))
for i in lista_dip:
    print(f"Nombre: {i['nombre']}  |   ID: {i['id']}")
    print()

##################### Obtener ultima fila de BD de un dispositivo con uuid
uuid = '00000003-0001-0005-0000-000000000001'
# uuid = '00000001-0002-0020-0000-000000000001'

ultimo_dato = obtener_ultimo_valor(uuid)

# print(ultimo_dato)

for i in ultimo_dato:
    print(f"variable {i} | valor: {ultimo_dato[i]}")


#################### obtener historico en un tiempo relativo
# historial = obtener_historial(
#         uuid=uuid,
#         limit=100, 
#         hours=1, 
#         minutes=0
#     )

# print(f"Registros obtenidos: {len(historial)}")


# obtener historico en un rango de fechas

# inicio = datetime(2026, 6, 10, 8, 0)   # 15 de febrero de 2026, 8:00 AM
# fin    = datetime(2026, 6, 11, 12, 30) # 15 de febrero de 2026, 12:30 PM

# historial = obtener_historial(uuid, limit=100, start_date=inicio, end_date=fin)

# print(f"Registros obtenidos: {len(historial)}")

# for i in historial[0]:
#     print(f"variable {i} | valor: {historial[0][i]}")
###################################################################################











