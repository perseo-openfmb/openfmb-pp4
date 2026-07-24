# Search Engine

Motor de búsqueda full-text para documentación y configuración de la plataforma OpenFMB.

## Qué busca

| Tipo | Archivos | Motor |
|------|----------|-------|
| PDF | `*.pdf` | pdfplumber (extracción por página + detección de secciones) |
| CSV | `*.csv` | Lectura directa con sniffing de delimitador |

Los archivos a indexar se colocan en `docs/` (montado como volumen en Docker).

## Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Interfaz de búsqueda (dark theme) |
| GET | `/api/search?q=...&doc=...` | Búsqueda full-text (OR multi-término) |
| GET | `/api/docs` | Lista de documentos indexados |
| GET | `/pdf/{path}` | Sirve un PDF para visualización en navegador |
| GET | `/view/{path}?line=N&q=...` | Visor de archivos de texto con resaltado |

## Funcionalidades

- Búsqueda case-insensitive con normalización de tildes (español)
- Soporte de frases exactas con comillas simples: `'modbus timeout'`
- Filtros por tipo de documento (PDF / CSV)
- Resaltado de coincidencias en resultados y en vista de archivo
- Detección automática de secciones en PDFs
- Labels descriptivos para CSVs (mapeo de variables, identificadores mRID)

## Infraestructura

```
Browser (:5500) ──→ search-engine (Flask)
                         │
                         └──→ docs/ (PDFs + CSVs montados como volumen)
```

No se conecta a TimescaleDB ni a ningún otro servicio. Es una app estática que indexa archivos al iniciar.

## Ejecución

```bash
# Producción (Docker)
docker compose up search-engine --build

# Desarrollo local
pip install -r requirements.txt
python app.py
```

## Agregar documentación

Colocar los archivos en `docs/`:

```bash
cp mi_documento.pdf app/search-engine/docs/
cp mapeo_variables.csv app/search-engine/docs/
```

El índice se reconstruye al reiniciar el contenedor.
