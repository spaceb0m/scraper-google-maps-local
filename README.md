# Google Maps Scraper `v0.6`

Scraper de negocios de Google Maps con interfaz web integrada. Extrae nombre, teléfono, dirección, web, valoración y categoría de los resultados de búsqueda y los exporta a CSV.

## Características

- **Scraping vía Playwright** — navega Google Maps como un usuario real (sin API key)
- **Grid geográfico automático** — genera la cuadrícula de sectores vía Nominatim + Shapely; solo hay que indicar `--city`
- **Subdivisión adaptativa** — los sectores con alta densidad se subdividen recursivamente en 4 sub-sectores hasta cubrir todos los negocios
- **Concurrencia configurable** — N contextos Playwright simultáneos (`--concurrency`, default 3)
- **Escritura incremental al CSV** — cada registro se escribe inmediatamente; el CSV es válido incluso si se detiene la ejecución
- **Deduplicación automática** — elimina duplicados por URL de Maps o por hash de nombre+dirección+teléfono
- **Detección de fin de lista** — distingue entre fin real confirmado por Google y parada heurística
- **Interfaz web** — formulario con parámetros configurables, log en tiempo real via SSE, métricas vivas y botón de detener

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
  --category "restaurantes" \
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
| `--concurrency` | int | `3` | Número de contextos Playwright simultáneos |
| `--zones` | JSON | — | Override manual de zonas (avanzado, ver abajo) |

### Grid automático (comportamiento por defecto)

El scraper consulta Nominatim para obtener el bounding box y polígono real de la ciudad, genera una cuadrícula de sectores de 0.01° (~1.1 km) y filtra los que caen fuera del polígono urbano real. Cada sector que alcanza el límite de resultados de Maps (~120) se subdivide automáticamente en 4 sub-sectores recursivos hasta garantizar cobertura completa.

```bash
# Grid automático — comportamiento por defecto
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "restaurantes" \
  --output ./out/sc_restaurantes.csv \
  --concurrency 3
```

### Override manual de zonas (avanzado)

```bash
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "restaurantes" \
  --output ./out/sc_restaurantes.csv \
  --zones '[
    {"lat": 42.879, "lon": -8.544, "zoom": 14},
    {"lat": 42.870, "lon": -8.540, "zoom": 14}
  ]'
```

## Uso — Interfaz web

```bash
uvicorn server:app --reload
```

Abre `http://localhost:8000`. La interfaz permite:

- Configurar todos los parámetros mediante formulario
- Ver el log de ejecución en tiempo real (SSE)
- Monitorizar métricas en vivo: descubiertos / procesados / válidos / errores
- Detener la ejecución en cualquier momento (el CSV parcial queda disponible)
- Descargar el CSV resultante al finalizar o tras detener

## Analizador de resultados

Procesa el CSV generado por el scraper para detectar qué negocios tienen tienda online y qué tecnología ecommerce usan.

```bash
# Se lanza automáticamente desde la interfaz web (botón 🔍 en el historial)
# También ejecutable directamente:
python -m src.analyzer.cli --csv-path out/fichero.csv
```

### Qué hace

1. **Filtra marcas** — excluye cadenas configuradas en `config/excluded_brands.json` (coincidencia de subcadena, sin distinguir mayúsculas)
2. **Detecta tecnología** — descarga el HTML de cada web y busca firmas de plataformas conocidas
3. **Genera XLSX** — fichero con dos pestañas:
   - `Datos originales`: copia fiel del CSV
   - `Análisis`: registros no filtrados con columnas `es_tienda` (Sí/No/–) y `tecnologia`

### Plataformas detectadas

Shopify, WooCommerce, PrestaShop, Velfix, Magento, Squarespace, Wix, Webflow y "Desconocida" (indicadores genéricos de carrito/checkout).

### Métricas en tiempo real

La interfaz web muestra durante el análisis: Filtrados / Analizados / Tiendas / Sin web·Error.

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
├── cli.py                  # Orquestación principal: grid → pool → sectores → CSV
├── domain.py               # Modelo de datos (BusinessRecord)
├── browser/
│   ├── session.py          # Gestión de sesión Playwright (Chromium)
│   └── pool.py             # ContextPool — N contextos simultáneos con Semaphore
├── geo/
│   ├── nominatim.py        # fetch_city_geodata() — bbox + polígono vía Nominatim
│   └── grid.py             # build_sector_grid() + filter_by_polygon() con Shapely
├── scraper/
│   ├── maps_search.py      # Búsqueda, scroll y detección de fin de lista
│   └── maps_detail.py      # Extracción de datos de página de detalle
├── pipeline/
│   ├── normalize.py        # Limpieza y normalización de texto
│   ├── dedupe.py           # Deduplicación por URL y por hash
│   ├── csv_writer.py       # StreamingCsvWriter — escritura incremental con dedup en vuelo
│   └── export_csv.py       # Exportación a CSV (modo legacy)
└── utils/
    ├── logging.py          # Configuración de logging
    └── retry.py            # Reintento async con backoff exponencial

server.py                   # Servidor FastAPI (interfaz web + SSE + stop + analizador)
static/index.html           # UI: formulario + log SSE + métricas + stop + descarga + historial
static/analyze.html         # UI del analizador: editor de marcas, log SSE, descarga XLSX
src/analyzer/
├── cli.py                  # Punto de entrada del analizador (subproceso)
├── brand_filter.py         # Filtrado de marcas por subcadena
└── fingerprint.py          # Detección de plataforma ecommerce por fingerprinting HTML
config/
└── excluded_brands.json    # Lista de marcas a excluir (editable desde la UI)
```

## Cómo funciona el scraping

1. **Grid**: consulta Nominatim → bounding box + polígono real → cuadrícula de sectores → filtro Shapely
2. **Búsqueda**: navega a coordenadas del sector con zoom configurado, gestiona diálogos de consentimiento
3. **Descubrimiento**: scroll en el panel de resultados recogiendo URLs (`a.hfpxzc`), detectando fin de lista real o parando por heurística (12 iteraciones sin crecimiento)
4. **Subdivisión**: si el sector para por heurística y `cell_deg > 0.002°`, se subdivide en 4 sub-sectores (NW, NE, SW, SE) recursivamente
5. **Extracción**: visita cada detalle y extrae campos con múltiples selectores + fallbacks regex
6. **Pipeline**: normaliza → deduplica en vuelo → escribe al CSV inmediatamente

## Concurrencia y RAM

Cada contexto Playwright carga Google Maps con ~200–300 MB de RAM. Recomendaciones:

| `--concurrency` | RAM recomendada |
|---|---|
| 3 (default) | 8 GB |
| 5 | 16 GB |
| 8 (máximo) | 32 GB |

## Limitaciones conocidas

- Dependiente del DOM de Google Maps, que puede cambiar sin aviso
- Los sectores comparten bordes → algunos negocios se descubren en múltiples sectores y se descartan por deduplicación (comportamiento correcto y esperado)
- Nominatim tiene política de uso justo: 1 req/s, User-Agent obligatorio

## Desarrollo y tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
