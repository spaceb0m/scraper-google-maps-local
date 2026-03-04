# Google Maps Scraper MVP (Directo)

Scraper MVP en Python + Playwright para obtener negocios desde Google Maps y exportar a CSV.

## Requisitos

- Python 3.11+
- pip

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium
```

## Ejecución MVP

```bash
python -m src.cli \
  --city "Santiago de Compostela, España" \
  --category "tiendas de ropa" \
  --output "./out/santiago_ropa.csv" \
  --headless true \
  --max-results 0 \
  --slow-ms 250 \
  --timeout-ms 15000
```

## Salida CSV

Columnas:

- nombre
- telefono
- direccion
- web
- rating
- categoria
- source_query
- retrieved_at_utc
- maps_url

## Tests

```bash
pytest -q
```

## Notas

- Estrategia anti-bloqueo inicial conservadora: sesión única y ritmo secuencial.
- El scraping directo depende de cambios en UI de Google Maps; se han añadido selectores alternativos y capturas de error.
