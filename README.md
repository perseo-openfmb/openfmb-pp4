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

El admin lo fija Grafana en cada arranque a partir de `GF_SECURITY_ADMIN_USER` /
`GF_SECURITY_ADMIN_PASSWORD`. El usuario de solo lectura lo crea el servicio
`grafana-init` por la API (Grafana no sabe provisionar usuarios por archivo).
El script es idempotente: si el usuario ya existe, re-sincroniza clave y rol.

```bash
docker compose logs grafana-init    # ver el resultado del provisioning
```

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

Y al reves: si editas un JSON a mano, el provisioner lo recarga a los ~30 s y
pisa lo que hubiera en la interfaz. **Exporta antes de tocar archivos a mano.**

Lo que no son dashboards (tema por defecto, usuarios, datasource) es declarativo
—`docker-compose.yml`, `.env` y `config/grafana/provisioning/`— justamente para
que sobreviva a un borrado del volumen. El tema se controla con `GRAFANA_THEME`
(`light` | `dark`).

## Adaptador Modbus

Todos los perfiles de **lectura** (`MeterReadingProfile`, `ResourceReadingProfile`,
`SwitchStatusProfile`) muestrean a **5000 ms**: son los que se publican por NATS y
acaban en TimescaleDB, y el sink agrupa escrituras cada 5 s
(`timescaledb.data-store-interval-seconds`), asi que muestrear mas rapido solo
agrega carga sin ganar resolucion.

Los perfiles de **control** (`...DiscreteControlProfile`) conservan su periodo
propio: ahi el `poll_period_ms` marca la latencia con la que se aplica un comando.

El periodo efectivo de cada perfil sale de combinar el `poll_period_ms` del
archivo en `modbus-master/` con un posible override
`profiles[N].poll_period_ms` en `config/adapter.yaml`, que tiene prioridad.
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
