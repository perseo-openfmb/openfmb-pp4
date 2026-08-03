# openfmb-pp4

OpenFMB PERSEO P4 Project - dev branch

## Puesta en marcha

```bash
cp .env.example .env        # y rellenar las claves
docker compose up -d
```

| Servicio      | URL                    | Notas                                  |
|---------------|------------------------|----------------------------------------|
| Grafana       | http://localhost:3000  | requiere login (ver abajo)             |
| HMI           | http://localhost:32771 |                                        |
| API Python    | http://localhost:8000  |                                        |
| Search engine | http://localhost:5500  |                                        |
| pgAdmin       | http://localhost:80    |                                        |
| TimescaleDB   | localhost:5432         |                                        |

## Grafana

### Usuarios

El acceso anonimo esta deshabilitado: antes existia un bypass que entraba como
**Admin** sin clave, de modo que cualquiera con acceso al puerto 3000 podia
editar o borrar dashboards. Ahora hay dos cuentas, definidas en el `.env`:

| Cuenta                    | Rol    | Puede                                          |
|---------------------------|--------|------------------------------------------------|
| `GRAFANA_USER`            | Admin  | ver y editar dashboards, datasources, usuarios  |
| `GRAFANA_VIEWER_USER`     | Viewer | solo ver y explorar; no puede guardar nada      |

El usuario de solo lectura lo crea el servicio `grafana-init` por la API
(Grafana no sabe provisionar usuarios por archivo). El script es idempotente:
si el usuario ya existe, re-sincroniza clave y rol.

```bash
docker compose logs grafana-init    # ver el resultado del provisioning
```

#### ⚠️ La clave del admin NO se reaplica en cada arranque

Grafana usa `GF_SECURITY_ADMIN_PASSWORD` **solo cuando crea el usuario admin
por primera vez en un volumen vacio**. En arranques posteriores la ignora: la
clave real vive dentro de `grafana.db`, en el volumen `grafana_data`.

Consecuencia practica: si editas `GRAFANA_PASSWORD` en el `.env` de un stack
que ya venia corriendo, **el login seguira pidiendo la clave vieja** aunque
`docker exec grafana env` muestre la nueva. Para sincronizarlas:

```bash
./scripts/grafana_reset_admin_password.sh              # toma la clave del .env
./scripts/grafana_reset_admin_password.sh 'otraClave'  # o una explicita
```

### Sesion iniciada: cuanto dura

Al entrar, Grafana deja una cookie `grafana_session` **persistente** (no de
sesion de navegador), asi que cerrar el navegador no cierra la sesion. La
duracion se controla en `docker-compose.yml`:

| Variable                                        | Valor | Significado                          |
|-------------------------------------------------|-------|--------------------------------------|
| `GF_AUTH_LOGIN_MAXIMUM_INACTIVE_LIFETIME_DURATION` | `30d` | caduca tras 30 dias sin usarla       |
| `GF_AUTH_LOGIN_MAXIMUM_LIFETIME_DURATION`          | `90d` | tope absoluto desde el login         |
| `GF_AUTH_TOKEN_ROTATION_INTERVAL_MINUTES`          | `60`  | cada cuanto rota el token (invisible)|

La sesion tambien sobrevive a `docker restart grafana`, porque los tokens se
guardan en `grafana.db` dentro del volumen.

Dos cosas que **rompen** la persistencia si se cambian:

- **`GF_AUTH_ANONYMOUS_ENABLED=true`**: al volver al navegador sin cookie
  valida, Grafana no te pide login — te sirve como usuario *Anonymous*. Parece
  que "se cayo la sesion" cuando en realidad nunca te la pidio. Por eso se deja
  en `false`.
- **`GF_SECURITY_COOKIE_SECURE=true`** sirviendo por HTTP plano: el navegador
  descarta la cookie y hay que loguearse en cada visita. Solo ponerlo en `true`
  cuando el stack este detras de HTTPS.

### Persistencia de los dashboards  ⚠️

El provisioning por archivo de Grafana es de **una sola via**:

```
config/grafana/dashboards/*.json  ──automatico──>  Grafana
config/grafana/dashboards/*.json  <──NO EXISTE───  Grafana
```

Lo que se edita y se guarda en la interfaz vive **solo** en `grafana.db`, dentro
del volumen `grafana_data`. No viaja al repositorio por si solo, asi que un
`git push` se lleva los JSON viejos y los cambios de estilo se pierden al migrar
de maquina o al recrear el volumen.

**Flujo correcto para cambiar un dashboard:**

```bash
# 1. editarlo y guardarlo en la interfaz de Grafana
# 2. volcarlo al repositorio
python3 scripts/grafana_export_dashboards.py
# 3. revisar el diff y commitear
git add config/grafana/dashboards && git commit -m "grafana: actualiza dashboards"
```

Antes de un push conviene comprobar que no quedo nada sin exportar:

```bash
python3 scripts/grafana_export_dashboards.py --check   # salida != 0 si hay pendientes
```

**Cuidado con las filas colapsadas.** Al expandir una fila (`row`) en la
interfaz, Grafana saca los paneles anidados al nivel superior del JSON y pone
`collapsed: false`. El contenido no cambia —los paneles son los mismos— pero el
diff sale enorme (miles de lineas) y, si se commitea, el dashboard pasa a abrir
con todas las filas desplegadas para todo el mundo.

Si `--check` reporta un dashboard que no recuerdas haber editado, compara
primero el numero de paneles: si coincide, es solo estado de la interfaz y
**no conviene exportarlo**. Colapsa las filas en Grafana y vuelve a comprobar.

Y al reves: si editas un JSON a mano, el provisioner lo recarga a los ~30 s y
pisa lo que hubiera en la interfaz. **Exporta antes de tocar archivos a mano.**

Lo que no son dashboards (tema por defecto, usuarios, datasource) es declarativo
—`docker-compose.yml`, `.env` y `config/grafana/provisioning/`— justamente para
que sobreviva a un borrado del volumen. El tema se controla con `GRAFANA_THEME`
(`light` | `dark`).

## Adaptador Modbus

Los tiempos viven en los archivos de `modbus-master/`, que son la **unica fuente
de verdad**. `config/adapter.yaml` ya no los sobrescribe: solo define que sesion
usa que archivo, con que IP/unit-id y que mRIDs.

| Tipo de perfil | Perfiles | Cant. | `poll_period_ms` | Por que |
|---|---|---|---|---|
| **Lectura** | `MeterReadingProfile`, `ResourceReadingProfile`, `SwitchStatusProfile` | 37 | **5000** | Se publican por NATS y acaban en TimescaleDB. El sink agrupa escrituras cada 5 s (`data-store-interval-seconds`), asi que muestrear mas rapido solo agrega carga sin ganar resolucion. |
| **Interruptores** | `SwitchDiscreteControlProfile` | 26 | **1000** | Reles Modbox y el switch del CC 246. Es la latencia de accionamiento: a 5 s, cerrar un interruptor tardaria hasta 5 segundos. |
| **Setpoints** | `ResourceDiscreteControlProfile` | 53 | **5000** | Limites de potencia del inversor Fronius y registros del Color Control. No son accionamientos. |

> Se probo poner **todos** los perfiles de control a 1 s y no salio bien: la
> carga Modbus paso de ~20 a ~76 transacciones/s y las sesiones de medicion se
> quedaron sin hilo — `Medidor_Iluminacion` cayo a una lectura cada 11 s con
> 50 % de huecos. Dejando solo los interruptores a 1 s la carga queda en ~32/s
> y el accionamiento sigue siendo de 1 segundo.

### `response_timeout_ms`

Es un atributo **de sesion** (uno por archivo), no por perfil, asi que no puede
distinguir control de medicion.

| Archivos | Timeout | Motivo |
|---|---|---|
| `modbus-boxes.yaml`, `CC_slave_246.yaml` | **1000 ms** | Reles locales rapidos (0 % de fallos medidos) y son justo los que accionan en 1 s. |
| El resto | **5000 ms** | Aqui caen los medidores Schneider/Siemens, el piranometro y el inversor Fronius, que son lentos: con timeouts de 1000–2500 ms perdian lecturas (el Fronius dio 41 timeouts en 3 min con 1000 ms). |

`modbus-fronius.yaml` es la excepcion consciente: tiene un perfil de switch a
1 s pero timeout de 5 s, porque el equipo es lento. `check_poll_periods.py` lo
reporta como **aviso**, no como error.

### Carga y `thread-pool-size`

`thread-pool-size` esta en **12**: un hilo por sesion (hay 11) mas margen. Con
los 6 originales se notaba la contencion al subir la carga.

Un equipo que no responde ocupa su hilo el ciclo completo, asi que si vuelve a
aparecer contencion la salida es **bajar el timeout o subir el poll de los
setpoints**, no tocar el de medicion ni el de los interruptores.

> Nota de campo: los medidores Schneider/Siemens de `192.168.0.8` y
> `192.168.0.10` son erraticos (5–20 % de lecturas perdidas) en **todas** las
> configuraciones probadas, incluida la original. Comparten pasarela
> serie-sobre-TCP y ese es el cuello de botella real, no la configuracion del
> adaptador. Los Color Control, en cambio, van a 5.00 s con 0 % de perdidas.

Para verificarlo:

```bash
python3 scripts/check_poll_periods.py           # falla si algo se salio de 5000 ms
python3 scripts/check_poll_periods.py --list    # detalle por sesion
```

## Respaldos de la base

El servicio `db-backup` hace un `pg_dump -Fc` diario en `./backups/` y conserva
los 7 mas recientes (`BACKUP_INTERVAL_SECONDS`, `BACKUP_KEEP`). Para restaurar:

```bash
./scripts/db_restore.sh backups/openfmb_<fecha>.dump
```

## Mantenimiento de Docker

```bash
# Parar y borrar contenedores
docker stop $(docker ps -a -q); docker rm $(docker ps -a -q)

# Borrar imagenes
docker rmi -f $(docker images -a -q)

# Borrar volumenes no usados
docker volume prune

# Borrar todo (¡incluye los datos de Grafana y TimescaleDB!)
docker system prune --volumes

# ID de usuario
echo $(id -u)
```

### Carpeta `./grafana_data/` huerfana

Grafana usaba un bind-mount `./grafana_data:/var/lib/grafana` y ahora usa el
volumen con nombre `grafana_data`, asi que **la carpeta `./grafana_data/` del
repositorio ya no se usa**: quedo con el `grafana.db` viejo dentro. Se conserva
por si hace falta rescatar algo de la configuracion anterior; una vez
comprobado que no se necesita, se puede borrar.

Para inspeccionarla sin levantar nada:

```bash
sqlite3 grafana_data/grafana.db "select title, version, updated from dashboard;"
```
