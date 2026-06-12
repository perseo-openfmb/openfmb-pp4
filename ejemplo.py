from openfmb_client.client import OpenFMBClient

# (1) definir el cliente OpenFMB
client = OpenFMBClient(base_url="http://localhost:8000/")

# (2) obtener "objeto" con la última medida del dispositivo de interés
medidor = client.get_last_state(device_uuid="00000001-0001-0020-0000-000000000001")

# (3) sacar medidas
medida1 = medidor["a_phsb_mag"]
medida2 = medidor["hz_mag"]
print("Medida 1:", medida1)
print("Medida 2:", medida2)
