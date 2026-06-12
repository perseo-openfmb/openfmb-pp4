# Querys para diagramas de Grafana

## Medidor 1 -- Iluminación (Schneider)

### Potencia
>>> select "timestamp", phv_phsc_mag as "Active", ppv_phsab_mag as "Reactive", ppv_phsbc_mag as "Aparent"
from data
where device_uuid = '00000001-0001-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Corriente
>>> select "timestamp", a_net_mag as "Current L1", a_neut_mag as "Current L2", a_phsa_mag as "Current L3", "a_phsb_mag" as "Current Avg."
from data
where device_uuid = '00000001-0001-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Voltaje
>>> select "timestamp", pf_phsa_mag as "Voltage L1N", pf_phsb_mag as "Voltage L2N", pf_phsc_mag as "Voltage L3N", phv_net_mag as "Voltage L-N Avg."
from public.data
where device_uuid = '00000001-0001-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Energía (paso de potencia a energía)
>>> SELECT 
  SUM(phv_phsc_mag) / 3.6
FROM 
  data
WHERE 
  timestamp >= $__timeFrom() and timestamp <= $__timeTo() and device_uuid = '00000001-0001-0020-0000-000000000001';

### Frecuencia
>>> select "timestamp", va_net_mag
from data 
where device_uuid = '00000001-0001-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

## ---------------------------------------------
## Medidor 2 -- Operador de Red (Siemens)

### Potencia
>>> select "timestamp", phv_phsc_mag as "Active", ppv_phsab_mag as "Reactive", ppv_phsbc_mag as "Aparent"
from data
where device_uuid = '00000001-0002-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Corriente
>>> select "timestamp", a_net_mag as "Current L1", a_neut_mag as "Current L2", a_phsa_mag as "Current L3", "a_phsb_mag" as "Current Avg."
from data
where device_uuid = '00000001-0002-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Voltaje
>>> select "timestamp", pf_phsa_mag as "Voltage L1N", pf_phsb_mag as "Voltage L2N", pf_phsc_mag as "Voltage L3N", phv_net_mag as "Voltage L-N Avg."
from public.data
where device_uuid = '00000001-0002-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;

### Energía (paso de potencia a energía)
>>> SELECT 
  SUM(phv_phsc_mag) / 3.6
FROM 
  data
WHERE 
  timestamp >= $__timeFrom() and timestamp <= $__timeTo() and device_uuid = '00000001-0002-0020-0000-000000000001';

### Frecuencia
>>> select "timestamp", va_net_mag
from data 
where device_uuid = '00000001-0002-0020-0000-000000000001' AND $__timeFilter("timestamp")
ORDER BY "timestamp" ASC;
