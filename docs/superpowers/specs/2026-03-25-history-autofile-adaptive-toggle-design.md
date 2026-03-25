# Design: Historial de ejecuciones, ficheros automáticos y toggle de subdivisión adaptativa

**Fecha:** 2026-03-25
**Estado:** Aprobado

---

## Resumen

Tres mejoras independientes sobre la interfaz web del scraper:

1. **Toggle de subdivisión adaptativa** — checkbox en el formulario para activar/desactivar la subdivisión recursiva de sectores.
2. **Nombres de fichero automáticos** — el servidor genera el nombre del CSV a partir de ciudad + categoría + timestamp; el usuario no necesita especificarlo.
3. **Historial de ejecuciones** — sección debajo del formulario que muestra todas las ejecuciones de la sesión actual; clic en una fila abre la carpeta (local) o descarga el CSV (remoto).

---

## Feature 1: Toggle de subdivisión adaptativa

### Cambios en `src/cli.py`

Añadir el argumento:

```
--adaptive-subdivision  bool  default=True
```

Implementado con `parse_bool`. Cuando es `False`, `_process_sector` no activa la subdivisión aunque `result.reached_end == False`: el flag `needs_subdivision` se fuerza a `False`.

### Cambios en `server.py`

`POST /run` recibe el campo `adaptive_subdivision: str = Form("true")` y lo pasa como `--adaptive-subdivision {value}` al subprocess.

### Cambios en `static/index.html`

Añadir checkbox en la sección de opciones avanzadas del formulario:

```
☑ Subdivisión adaptativa   (checked por defecto)
```

---

## Feature 2: Nombres de fichero automáticos

### Generación del nombre

El servidor genera el nombre en `POST /run` antes de lanzar el subprocess:

```
out/{city_slug}_{category_slug}_{YYYYMMDD_HHMMSS}.csv
```

**Reglas del slug:**
- Normalizar Unicode (NFD) y eliminar diacríticos
- Pasar a minúsculas
- Sustituir cualquier carácter que no sea `[a-z0-9]` por `_`
- Colapsar `__` múltiples en `_`
- Truncar a 40 caracteres máximo por componente

**Ejemplos:**
- `out/santiago_de_compostela_restaurantes_20260325_143022.csv`
- `out/madrid_tiendas_de_ropa_20260325_091500.csv`

### Cambios en `server.py`

- Nueva función `_make_output_path(city, category) -> str` con la lógica de slug anterior.
- `POST /run` llama a esta función y almacena el path generado en `jobs[job_id]["output"]`.
- El directorio `out/` se crea con `Path(output).parent.mkdir(parents=True, exist_ok=True)` si no existe.

### Cambios en `static/index.html`

- Eliminar el campo `<input name="output">` del formulario.
- El path del fichero no es configurable por el usuario.

---

## Feature 3: Historial de ejecuciones

### Metadatos por job

El dict `jobs[job_id]` se amplía con:

| Campo | Tipo | Descripción |
|---|---|---|
| `city` | str | Ciudad introducida |
| `category` | str | Categoría introducida |
| `started_at` | str | ISO timestamp del inicio |
| `valid_count` | int | Registros válidos (actualizado en tiempo real) |

`valid_count` se actualiza en el loop de lectura de stdout: cada línea que coincide con `STATS valid=N` extrae N y sobreescribe `jobs[job_id]["valid_count"]`.

### Nuevos endpoints

**`GET /history`**

Devuelve la lista de jobs en orden inverso (más reciente primero):

```json
[
  {
    "job_id": "uuid",
    "city": "Santiago de Compostela, España",
    "category": "restaurantes",
    "started_at": "2026-03-25T14:30:22",
    "status": "done",
    "valid_count": 121,
    "output": "out/santiago_de_compostela_restaurantes_20260325_143022.csv"
  }
]
```

**`POST /open-folder/{job_id}`**

Solo para uso local. Abre la carpeta contenedora del CSV con el gestor de archivos del SO:

- macOS: `open -R {filepath}` (revela el fichero en Finder)
- Linux: `xdg-open {folder}`
- Windows: `explorer {folder}`

Devuelve `{"status": "ok"}` o `{"error": "..."}`.

### Cambios en `static/index.html`

**Detección de entorno:**

```js
const isLocal = ['localhost', '127.0.0.1', ''].includes(window.location.hostname);
```

**Sección "Historial"** (aparece solo cuando hay al menos 1 job):

- Card separado debajo del principal, mismo estilo visual
- Tabla con columnas: Hora | Ciudad | Categoría | Estado | Válidos
- Cada fila es clickable:
  - Local → `POST /open-folder/{job_id}`
  - Remoto → `window.location = /download/{job_id}`
- La fila del job activo actualiza `valid_count` y `status` en tiempo real (cada vez que llega un evento SSE con STATS o done)
- Al iniciar una nueva ejecución, se añade una fila nueva al principio de la tabla

---

## Archivos modificados

| Archivo | Cambios |
|---|---|
| `src/cli.py` | Añadir `--adaptive-subdivision` (bool, default True) |
| `server.py` | `_make_output_path()`, campo `adaptive_subdivision` en `/run`, `valid_count` en job metadata, `GET /history`, `POST /open-folder/{job_id}` |
| `static/index.html` | Checkbox subdivisión, eliminar campo output, sección historial |

## Archivos sin cambios

`src/browser/pool.py`, `src/geo/`, `src/pipeline/`, `src/scraper/`, `src/domain.py`, `src/utils/`

---

## Notas de implementación

- El historial **persiste** entre reinicios del servidor en `out/history.json`.
- Al arrancar el servidor, se carga `out/history.json` si existe y se populan los jobs históricos en memoria (sin `proc`, sin `lines` — solo metadatos).
- Tras cada cambio de estado de un job (`running` → `done` / `error` / `stopped`) se reescribe `out/history.json` con la lista completa de entradas.
- Formato de `history.json`: array JSON de objetos con los campos `job_id`, `city`, `category`, `started_at`, `status`, `valid_count`, `output`. Sin `lines` ni `proc` (no serializables ni útiles entre sesiones).
- La carpeta de salida es siempre `out/` relativa al directorio del servidor. No es configurable por el usuario en esta versión.
- `POST /open-folder` es un endpoint inocuo en remoto (nadie lo llama desde JS cuando `isLocal` es false), pero podría protegerse con un check adicional en el servidor si se desea.
