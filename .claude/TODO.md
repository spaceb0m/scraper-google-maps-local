# TODO — Roadmap de mejoras

> Plan elaborado el 2026-03-25. Estado: **pendiente de implementación**.
> El MVP web está funcionando. Estas mejoras van a continuación.

---

## Fase 1 — Cobertura geográfica automática (sin concurrencia)

El usuario solo especifica `--city`; el scraper genera el grid automáticamente.

- [ ] Crear `src/geo/__init__.py`
- [ ] Crear `src/geo/nominatim.py`
  - `fetch_city_geodata(city, session) → CityGeodata(bbox, polygon_geojson)`
  - Llamada a `https://nominatim.openstreetmap.org/search?q=<city>&format=json&polygon_geojson=1&limit=1`
  - Usar `aiohttp.ClientSession` con User-Agent obligatorio (política Nominatim)
- [ ] Crear `src/geo/grid.py`
  - `build_sector_grid(bbox, cell_deg=0.02) → list[Sector]`
    - `cell_deg=0.02` ≈ 1.5–2.2 km a latitudes ibéricas; zoom 14 cubre ~3×3 km
  - `filter_by_polygon(sectors, polygon_geojson) → list[Sector]`
    - Usa `shapely.geometry.shape()` + `polygon.contains(Point(lon, lat))`
    - Descarta sectores cuyo centro caiga fuera del polígono real de la ciudad
- [ ] Modificar `src/cli.py`
  - Si no hay `--zones`: llamar geo stack → generar lista de sectores automáticamente
  - `--zones` manual sigue funcionando como override
  - Loop secuencial existente sin cambios
- [ ] Añadir a `requirements.txt` y `pyproject.toml`:
  - `aiohttp>=3.9.0`
  - `shapely>=2.0.0`

---

## Fase 2 — Pool de Playwright contexts y concurrencia

**Nota crítica:** Google Maps requiere renderizado JS; `aiohttp` no puede sustituir a Playwright para el scraping. `aiohttp` solo se usa para Nominatim.

Concurrencia realista con Playwright (cada context ≈ 200–300 MB RAM):
- `--concurrency 3` (default): máquinas de 8 GB
- `--concurrency 5`: servidores de 16 GB
- `--concurrency 8`: máximo absoluto en 32 GB dedicados

- [ ] Modificar `src/browser/session.py`
  - Extraer `_context_kwargs(timeout_ms) → dict` con locale/user_agent
  - Interfaz pública `start_session`/`stop_session` sin cambios
- [ ] Crear `src/browser/pool.py`
  - `ContextPool(browser, n, timeout_ms)` — async context manager
  - `asyncio.Semaphore(n)` para limitar contexts concurrentes
  - Un solo `Browser` + N contexts (patrón canónico de Playwright)
- [ ] Modificar `src/cli.py`
  - Añadir `--concurrency` (int, default 3)
  - Modo concurrente: `asyncio.gather` de N tareas de sector con `ContextPool`
  - `--concurrency 1` preserva modo legacy secuencial

---

## Fase 3 — CSV streaming y gestión de memoria

- [ ] Crear `src/pipeline/csv_writer.py`
  - `StreamingCsvWriter` — async context manager
  - Abre CSV al inicio, escribe sector a sector con `asyncio.Lock`
  - Dedup en vuelo importando `normalize_maps_url` y `make_fallback_key` de `dedupe.py`
  - `handle.flush()` tras cada batch
- [ ] Modificar `src/cli.py`
  - Reemplazar `dedupe_records → export_csv` final por `StreamingCsvWriter`
  - `gc.collect()` cada 20 sectores completados

---

## Fase 4 — Integración web y QA

- [ ] `server.py` — añadir campo `concurrency` (int, default 3) al formulario POST `/run`
- [ ] `static/index.html` — añadir input numérico "Concurrencia (1–8)"
- [ ] Eliminar/deprecar textarea de zonas manuales en la UI (el grid es automático)
- [ ] Tests nuevos:
  - `tests/test_grid.py` — puro, sin IO
  - `tests/test_nominatim.py` — mock de `aiohttp`
  - `tests/test_csv_writer.py` — fichero temporal con `tmp_path`

---

## Fase 5 — Subdivisión adaptativa de sectores (pendiente)

Cuando un sector se para por heurística (~120 resultados), subdivirlo automáticamente en 4 sub-sectores (cuadrantes) y relanzarlos. Recursivo hasta que todos confirmen fin de lista o se alcance un tamaño mínimo de celda (`min_cell_deg`, e.g. 0.002°).

**Lógica:**
- En `_process_sector`: si `result.reached_end == False` y `sector.cell_deg > min_cell_deg`, generar 4 sub-sectores (NW, NE, SW, SE) y encolarlos como nuevas tareas
- Añadir `cell_deg` al dataclass `Sector` para poder subdividir recursivamente
- Actualizar `build_sector_grid` para aceptar `cell_deg` por sector

**Impacto:** cobertura total garantizada en zonas de alta densidad sin sobre-dividir zonas vacías.

---

## Verificación end-to-end (al completar todas las fases)

```bash
pip install -r requirements.txt

# Modo principal: grid automático, concurrencia 3
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "restaurantes" \
  --output ./out/sc_restaurantes.csv \
  --concurrency 3

# Modo legacy intacto
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "restaurantes" \
  --output ./out/legacy.csv \
  --concurrency 1

pytest -q
```

Señales de éxito:
- Log: `"Nominatim: X sectores en bounding box, Y tras filtro geográfico"`
- Progreso por sector con número actual / total
- CSV se rellena durante la ejecución (no solo al final)
- RAM estable con `htop` durante ejecución larga
- Log final: `"✓ Cobertura completa"` si todas las zonas confirmaron fin de lista

---

## Fase 6 — Valoraciones de Google Business (pendiente)

Para cada negocio en el CSV, scrapear sus reseñas individuales desde la ficha de Google Maps.

- Requiere navegar con Playwright a la sección de reseñas de cada negocio
- Paginar reseñas (click "Más reseñas")
- Extraer: autor, rating, fecha, texto, respuesta del negocio
- Guardar en una tercera hoja del XLSX o fichero separado

---

## Fase 7 — Consulta al Catastro (pendiente)

Para cada negocio con dirección física en España, consultar la Sede Electrónica del Catastro para obtener los metros cuadrados del inmueble.

- API pública del Catastro: `https://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero/COVCCallejero.svc/`
- Geocodificar dirección → referencia catastral → datos del inmueble
- Columna adicional en Sheet 2: `metros_cuadrados`
