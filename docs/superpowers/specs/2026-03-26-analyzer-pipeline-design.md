# Diseño: Pipeline de Análisis (Segunda Fase de Procesado)

**Fecha:** 2026-03-26
**Estado:** Aprobado
**Versión objetivo:** 0.4

---

## Contexto

El scraper de Google Maps ya produce CSVs con negocios scrapeados. Este diseño añade:

1. Mejoras al historial de ejecuciones en la UI
2. Un pipeline de análisis secundario accesible desde el historial que filtra marcas y detecta tiendas online mediante fingerprinting HTML, generando un `.xlsx` con dos pestañas

---

## Cambios en el Historial de Ejecuciones

### Iconos por entrada

Cada fila del historial tendrá dos iconos en su columna de acciones:

- **Icono carpeta**: abre el explorador de archivos del SO (local) o descarga el CSV (remoto). Disponible siempre.
- **Icono análisis** (lupa/rayo): navega a `/analyze/{job_id}`. Disponible cuando `valid_count > 0`, independientemente del estado.

### Clasificación de estados

| Estado | Condición |
|--------|-----------|
| `done` | El proceso completó normalmente |
| `stopped` | Detenido manualmente por el usuario |
| `partial` | Terminó por error/excepción pero `valid_count > 0` |
| `error` | Terminó por error y `valid_count = 0` |

---

## Arquitectura del Módulo Analizador

### Nuevos ficheros

```
src/analyzer/
├── cli.py          # Punto de entrada del análisis
├── brand_filter.py # Carga y aplica filtro de marcas
└── fingerprint.py  # Fetch + detección de plataforma ecommerce

config/
└── excluded_brands.json   # Lista persistente de marcas a excluir

static/
└── analyze.html    # Página de análisis (nueva ruta)
```

### Flujo de `src/analyzer/cli.py`

```
Lee CSV de entrada (path pasado como argumento)
Carga config/excluded_brands.json
Para cada registro:
  ├─ Si nombre contiene marca excluida (case-insensitive, subcadena) → omitir de Sheet 2
  ├─ Si web vacía o es instagram.com / facebook.com → is_store="-", platform="-"
  └─ Si web válida → fetch HTML → detect_platform()
       └─ LOGGER.info con resultado → SSE al frontend
Escribe XLSX:
  ├─ Sheet 1 = copia fiel de todos los registros del CSV original
  └─ Sheet 2 = registros no excluidos + columnas: es_tienda (Sí/No/-), tecnologia
Emite STATS y resumen final
```

### `src/analyzer/brand_filter.py`

- `load_brands(path: str) -> list[str]`: lee `config/excluded_brands.json`
- `is_excluded(name: str, brands: list[str]) -> bool`: comparación case-insensitive por subcadena

Ejemplo: marca `"Adolfo Dominguez"` excluye `"Adolfo Dominguez"` y `"Adolfo Dominguez (Santiago de Compostela)"`.

### `src/analyzer/fingerprint.py`

- `fetch_page(url: str) -> str | None`: descarga HTML con `aiohttp`, timeout 10s, devuelve `None` en error
- `detect_platform(html: str) -> tuple[bool, str | None]`: devuelve `(is_store, platform)`

Plataformas detectadas por fingerprinting:

| Plataforma | Firma |
|------------|-------|
| Shopify | `cdn.shopify.com` |
| WooCommerce | `woocommerce` en scripts/meta |
| PrestaShop | `prestashop` en scripts |
| Magento | `mage/` o `Magento` |
| Squarespace | `static.squarespace.com` |
| Wix | `static.wixstatic.com` |
| Webflow | `webflow.com` |

Si el HTML contiene términos como `add-to-cart`, `checkout`, `/cart`, `/carrito`, `añadir al carrito`, o atributos `data-product-id` sin plataforma reconocida → `(True, "Desconocida")`.
Sin ninguno de esos indicios → `(False, None)`.

---

## Configuración de Marcas

**`config/excluded_brands.json`** (incluido en el repo):

```json
{
  "brands": [
    "Sfera", "Springfield", "Stradivarius", "Pull&Bear", "ZARA",
    "MANGO", "Adolfo Dominguez", "BIMBA Y LOLA", "Roberto Verino",
    "Women's Secret", "Calzedonia", "Parfois"
  ]
}
```

---

## Nuevas Rutas del Servidor

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/analyze/{job_id}` | Sirve `static/analyze.html` |
| `POST` | `/run-analyze/{job_id}` | Lanza `src/analyzer/cli.py` como subproceso |
| `GET` | `/analyze-stream/{job_id}` | SSE del log de análisis |
| `GET` | `/brands` | Devuelve lista de marcas del JSON |
| `POST` | `/brands` | Sobreescribe la lista en el JSON |
| `GET` | `/download-xlsx/{job_id}` | Descarga el fichero `.xlsx` generado por el análisis |

---

## Página `static/analyze.html`

- Muestra el nombre del CSV de origen
- Campo editable con la lista de marcas (cargado via `GET /brands`), botón "Guardar cambios"
- Botón "Iniciar análisis"
- Log SSE en tiempo real (mismo estilo visual que `index.html`)
- Barra de stats: filtrados / analizados / tiendas detectadas
- Botón "Descargar XLSX" al terminar (nuevo endpoint `GET /download-xlsx/{job_id}`)

---

## Salida: Fichero XLSX

El análisis genera un fichero `.xlsx` en `out/` con el mismo nombre base que el CSV:

```
out/santiago_de_compostela_restaurantes_20260325_143022.csv   ← scraping (no se toca)
out/santiago_de_compostela_restaurantes_20260325_143022.xlsx  ← análisis
```

- **Sheet 1** (`Datos originales`): copia fiel del CSV (todos los registros)
- **Sheet 2** (`Análisis`): registros no excluidos por marcas + columnas adicionales:
  - `es_tienda`: `Sí` / `No` / `-` (sin web o web social)
  - `tecnologia`: nombre de la plataforma o `Desconocida` / `-`

Dependencia nueva: `openpyxl>=3.1.0`

---

## Roadmap (No implementar ahora)

Añadir a `.claude/TODO.md`:

- **Fase 6 — Valoraciones de Google Business**: scrapear las reseñas individuales de cada negocio desde su ficha de Google Maps
- **Fase 7 — Consulta al Catastro**: obtener los metros cuadrados de la dirección física de cada negocio desde la Sede Electrónica del Catastro

---

## Dependencias nuevas

```
openpyxl>=3.1.0    # Generación de XLSX con múltiples hojas
aiohttp>=3.9.0     # Fetch de páginas web para fingerprinting (ya previsto en TODO)
```
