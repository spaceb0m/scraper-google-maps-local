# Google Maps Scraper

Scraper de negocios de Google Maps con interfaz web integrada. Extrae nombre, teléfono, dirección, web, valoración y categoría de los resultados de búsqueda y los exporta a CSV.

## Características

- **Scraping vía Playwright** — navega Google Maps como un usuario real (sin API key)
- **Interfaz web** — formulario con parámetros configurables y log en tiempo real via SSE
- **Multi-zona** — soporta cuadrículas geográficas para cubrir ciudades completas
- **Deduplicación automática** — elimina duplicados por URL de Maps o por hash de nombre+dirección+teléfono
- **Detección de fin de lista** — distingue entre fin real confirmado por Google y parada heurística

## Requisitos

- Python 3.9+
- pip

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

## Uso — CLI

```bash
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "tiendas de ropa" \
  --output ./out/resultado.csv
```

### Parámetros

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `--city` | string | requerido | Ciudad y país (ej. `"Madrid, España"`) |
| `--category` | string | requerido | Categoría de negocio (ej. `"restaurantes"`) |
| `--output` | string | requerido | Ruta del CSV de salida |
| `--headless` | bool | `true` | Ejecutar navegador sin ventana visible |
| `--max-results` | int | `0` | Máximo de resultados por zona (0 = todos) |
| `--slow-ms` | int | `250` | Delay entre acciones de scroll (ms) |
| `--timeout-ms` | int | `15000` | Timeout de carga de página (ms) |
| `--zones` | JSON | — | Lista de zonas geográficas (ver sección multi-zona) |

### Multi-zona (cobertura completa de una ciudad)

Google Maps limita los resultados al viewport inicial (~120 negocios centrados en la ciudad). Para cubrir la ciudad completa, usa `--zones` con una cuadrícula de coordenadas:

```bash
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "restaurantes" \
  --output ./out/sc_restaurantes.csv \
  --zones '[
    {"lat": 42.879, "lon": -8.544, "zoom": 14},
    {"lat": 42.870, "lon": -8.540, "zoom": 14},
    {"lat": 42.860, "lon": -8.535, "zoom": 14}
  ]'
```

- Zoom 14 cubre aproximadamente un radio de 1.5–2 km por celda
- Los duplicados entre zonas se eliminan automáticamente

## Uso — Interfaz web

```bash
uvicorn server:app --reload
```

Abre `http://localhost:8000`. La interfaz permite:

- Configurar todos los parámetros mediante formulario
- Ver el log de ejecución en tiempo real (SSE)
- Monitorizar métricas en vivo: descubiertos / procesados / válidos / errores
- Descargar el CSV resultante al finalizar

## Formato de salida (CSV)

| Campo | Descripción |
|---|---|
| `nombre` | Nombre del negocio |
| `telefono` | Teléfono de contacto |
| `direccion` | Dirección completa |
| `web` | URL del sitio web |
| `rating` | Valoración (0.0–5.0) |
| `categoria` | Categoría en Google Maps |
| `source_query` | Búsqueda realizada |
| `retrieved_at_utc` | Timestamp de extracción (ISO 8601 UTC) |
| `maps_url` | URL directa en Google Maps |

## Arquitectura

```
src/
├── cli.py                  # Punto de entrada y orquestación principal
├── domain.py               # Modelo de datos (BusinessRecord)
├── browser/
│   └── session.py          # Gestión de sesión Playwright (Chromium)
├── scraper/
│   ├── maps_search.py      # Búsqueda, scroll y detección de fin de lista
│   └── maps_detail.py      # Extracción de datos de página de detalle
├── pipeline/
│   ├── normalize.py        # Limpieza y normalización de texto
│   ├── dedupe.py           # Deduplicación por URL y por hash
│   └── export_csv.py       # Exportación a CSV
└── utils/
    ├── logging.py          # Configuración de logging
    └── retry.py            # Reintento async con backoff exponencial

server.py                   # Servidor FastAPI (interfaz web)
static/index.html           # UI: formulario + log SSE en tiempo real
```

## Cómo funciona el scraping

1. **Búsqueda**: navega a `google.com/maps` (o a coordenadas con `--zones`), gestiona diálogos de consentimiento y ejecuta la búsqueda
2. **Descubrimiento**: hace scroll en el panel de resultados recogiendo URLs (`a.hfpxzc`), detectando fin de lista real o parando por heurística (12 iteraciones sin crecimiento)
3. **Extracción**: visita cada detalle y extrae campos con múltiples selectores + fallbacks regex
4. **Pipeline**: normaliza texto → deduplica → exporta CSV

## Limitaciones conocidas

- Google Maps limita cada viewport a ~120 resultados → usa `--zones` para cobertura total
- Scraping secuencial conservador. Ver roadmap para concurrencia planificada
- Dependiente del DOM de Google Maps, que puede cambiar sin aviso

## Desarrollo y tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Roadmap

Ver [`.claude/TODO.md`](.claude/TODO.md):
- Grid geográfico automático via Nominatim (sin `--zones` manual)
- Concurrencia con múltiples Playwright contexts (`--concurrency`)
- Escritura incremental al CSV (RAM constante independientemente del volumen)
