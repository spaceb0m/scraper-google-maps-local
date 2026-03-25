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
