# Contexto del proyecto para Claude

Este fichero proporciona contexto completo del proyecto para nuevas sesiones de trabajo.

## Versión actual: 0.4

## Qué es este proyecto

Scraper de Google Maps en Python + Playwright que extrae datos de negocios (nombre, teléfono, dirección, web, rating, categoría) y los exporta a CSV. Tiene una interfaz web (FastAPI + SSE) para ejecutarlo desde el navegador y ver el log en tiempo real.

## Estado actual (2026-03-25)

### Lo que funciona

- **CLI completo**: `python -m src.cli --city ... --category ... --output ...`
- **Multi-zona manual**: `--zones '[{"lat":..., "lon":..., "zoom":14}]'` para cubrir más de un viewport
- **Interfaz web en `http://localhost:8000`**: formulario con todos los parámetros, log SSE en tiempo real, métricas vivas (descubiertos/procesados/válidos/errores), descarga CSV
- **Detección de fin de lista**: distingue `reached_end=True` (Google confirmó) de parada heurística (12 iteraciones sin crecimiento)
- **Log granular**: progreso cada 10 resultados, avisos por registros omitidos, resumen de deduplicación

### Servidor web

```bash
uvicorn server:app --reload   # http://localhost:8000
```

`server.py` lanza el CLI como subproceso con `python -u -m src.cli ...` (flag `-u` = unbuffered para SSE en tiempo real). Los logs se streaman via SSE en `GET /stream/{job_id}`.

### Bug fix relevante

`_get_scroll_container` en `maps_search.py` usa `wait_for_selector(..., timeout=10000)` en lugar de comprobar si el elemento ya existe. Sin esta espera, Google Maps no ha terminado de cargar la lista y el scraper descubre 0 resultados.

### Analizador

```bash
# Se lanza automáticamente desde la UI — /analyze/<job_id>
# También ejecutable directamente:
python -m src.analyzer.cli --csv-path out/fichero.csv
```

`src/analyzer/cli.py` lee un CSV del scraper, filtra marcas (case-insensitive, subcadena), detecta tecnologías ecommerce mediante fingerprinting HTML con `aiohttp`, y genera un `.xlsx` con dos pestañas:
- **Sheet 1** (`Datos originales`): copia fiel del CSV
- **Sheet 2** (`Análisis`): registros no filtrados + columnas `es_tienda` (Sí/No/-) y `tecnologia`

Clasificación de estados de job: `done` (completado), `stopped` (detenido), `partial` (error pero con registros válidos), `error` (sin registros válidos).

## Estructura de ficheros

```
src/
├── cli.py              # Orquestación principal: parse args → zonas → search → extract → dedupe → CSV
├── domain.py           # BusinessRecord dataclass (9 campos)
├── browser/session.py  # start_session() / stop_session() — Playwright Chromium
├── scraper/
│   ├── maps_search.py  # open_maps_and_search(), collect_result_refs() → SearchResults(refs, reached_end)
│   └── maps_detail.py  # extract_business_record() — extrae los 9 campos de la página de detalle
├── pipeline/
│   ├── normalize.py    # clean_text, clean_phone, clean_web, clean_rating
│   ├── dedupe.py       # normalize_maps_url(), make_fallback_key(), dedupe_records()
│   └── export_csv.py   # export_csv(path, records) — escribe CSV completo al final
└── utils/
    ├── logging.py      # setup_logging() — formato: "timestamp | LEVEL | module | mensaje"
    └── retry.py        # retry_async(fn, attempts, base_delay) — backoff exponencial

server.py               # FastAPI: GET / → index.html | POST /run → lanza CLI | GET /stream/{id} → SSE
static/index.html       # UI: formulario, log, stats bar, badge de estado, botón descarga CSV
static/analyze.html     # UI del analizador: editor de marcas, log SSE, descarga XLSX
src/analyzer/
├── cli.py              # Punto de entrada del analizador (subproceso)
├── brand_filter.py     # load_brands(), is_excluded() — filtrado de marcas
└── fingerprint.py      # fetch_page(), detect_platform() — detección ecommerce
config/
└── excluded_brands.json  # Lista de marcas a excluir (editable desde UI)
.claude/
├── launch.json         # Config del servidor para preview_start
└── TODO.md             # Roadmap de mejoras pendientes (geo automático + concurrencia + CSV streaming)
```

## Modelo de datos

```python
@dataclass
class BusinessRecord:
    nombre: str
    telefono: str
    direccion: str
    web: str
    rating: str
    categoria: str
    source_query: str
    retrieved_at_utc: str
    maps_url: str
```

## Flujo principal (cli.py `_run`)

```
parse --zones (JSON) o usar dict vacío como zona por defecto
│
└─ para cada zona:
     open_maps_and_search(page, query, lat, lon, zoom)   # navega al viewport
     collect_result_refs(page, slow_ms, max_results)      # scroll → SearchResults
     _process_refs(refs, page, query, ...)                # visita cada detalle
       └─ cada 10 records: LOGGER.info("Progreso: X/Y ...")
│
dedupe_records(all_records)     # dedup global multi-zona
export_csv(output, deduped)     # escribe CSV completo
LOGGER.info resumen final       # discover/processed/valid/duplicates/errors/elapsed
```

## Deduplicación

`dedupe.py` usa dos estrategias en cascada:
1. **URL normalizada**: `maps_url.strip().split("?")[0]` — clave principal
2. **Hash fallback**: `sha1(nombre.lower() + "|" + direccion.lower() + "|" + telefono.lower())` — para registros sin URL

Ambas funciones (`normalize_maps_url`, `make_fallback_key`) son públicas e importables.

## Dependencias actuales

```
playwright>=1.50.0       # scraping (no sustituible por aiohttp — Google Maps requiere JS)
fastapi>=0.115.0         # servidor web
uvicorn[standard]>=0.32.0
python-multipart>=0.0.12 # Form() en FastAPI
openpyxl>=3.1.0          # Generación de XLSX multi-hoja
aiohttp>=3.9.0           # Fetch de páginas web para fingerprinting
```

**Python 3.9**: usar `Optional[str]` de `typing`, NO `str | None` (FastAPI/Pydantic evalúa anotaciones en runtime).

## Compatibilidad Python 3.9

El servidor corre con Python 3.9 del sistema. Evitar:
- Sintaxis `X | Y` en anotaciones de parámetros de FastAPI
- `dict[str, X]` como anotación de retorno en rutas FastAPI
- `list[X]` sin `from __future__ import annotations` en contextos evaluados por Pydantic

## Próximas mejoras (ver .claude/TODO.md)

### Fase 1 — Grid geográfico automático
- `src/geo/nominatim.py`: `fetch_city_geodata(city) → CityGeodata(bbox, polygon_geojson)` vía Nominatim
- `src/geo/grid.py`: `build_sector_grid(bbox, cell_deg=0.02)` + `filter_by_polygon(sectors, geojson)` con Shapely
- Nuevas deps: `aiohttp>=3.9.0`, `shapely>=2.0.0`
- Objetivo: `--city "Madrid"` genera el grid sin `--zones` manual

### Fase 2 — Concurrencia con Playwright contexts
- `src/browser/pool.py`: `ContextPool(browser, n, timeout_ms)` con `asyncio.Semaphore(n)`
- `--concurrency` (default 3): N contexts simultáneos, cada uno ~200-300 MB RAM
- **NO usar aiohttp para scraping de Maps** — requiere renderizado JS

### Fase 3 — CSV streaming
- `src/pipeline/csv_writer.py`: `StreamingCsvWriter` con `asyncio.Lock`, dedup en vuelo, flush por sector
- Elimina acumulación en memoria; RAM estable en ejecuciones largas

## Comandos útiles

```bash
# Ejecutar scraper
python -m src.cli --city "Madrid, España" --category "restaurantes" --output ./out/test.csv

# Servidor web (con live reload)
uvicorn server:app --reload

# Tests
pytest -q

# Instalar chromium (primera vez)
playwright install chromium
```
