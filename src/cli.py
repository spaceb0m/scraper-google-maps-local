from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from typing import Any

from playwright.async_api import async_playwright

from src.browser.pool import ContextPool, PooledContext
from src.geo.grid import Sector, build_sector_grid, filter_by_polygon
from src.geo.nominatim import fetch_city_geodata
from src.pipeline.csv_writer import StreamingCsvWriter
from src.scraper.maps_detail import extract_business_record
from src.scraper.maps_search import SearchResultRef, collect_result_refs, open_maps_and_search
from src.utils.logging import setup_logging
from src.utils.retry import retry_async

LOGGER = logging.getLogger(__name__)


def parse_bool(value: str) -> bool:
    lower = value.lower().strip()
    if lower in {"1", "true", "yes", "y"}:
        return True
    if lower in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"Booleano inválido: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Maps Scraper")
    parser.add_argument("--city", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--headless", type=parse_bool, default=True)
    parser.add_argument("--max-results", type=int, default=0)
    parser.add_argument("--slow-ms", type=int, default=250)
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--concurrency", type=int, default=3,
                        help="Número de contextos Playwright simultáneos (default: 3)")
    parser.add_argument(
        "--zones", type=str, default=None,
        help="[Avanzado] JSON manual de zonas. Si no se indica, se genera automáticamente via Nominatim.",
    )
    parser.add_argument(
        "--adaptive-subdivision", type=parse_bool, default=True,
        dest="adaptive_subdivision",
        help="Activar subdivisión adaptativa de sectores (default: true)",
    )
    return parser


async def _process_refs(
    refs: list,
    page: Any,
    query: str,
    slow_ms: int,
    sector_label: str,
    csv_writer: StreamingCsvWriter,
    metrics: dict,
) -> None:
    """Procesa una lista de refs escribiendo cada registro al CSV inmediatamente.
    Actualiza metrics en tiempo real y emite STATS cada 10 registros.
    """
    local_processed = 0
    local_errors = 0

    for ref in refs:
        url = ref.maps_url

        async def go_to_detail() -> None:
            await page.goto(url, wait_until="domcontentloaded")

        try:
            await retry_async(go_to_detail, attempts=2)
            await asyncio.sleep((slow_ms + random.randint(20, 150)) / 1000)
            record = await retry_async(
                lambda: extract_business_record(page, query),
                attempts=2,
            )
            if not record.nombre:
                local_errors += 1
                metrics["errors"] += 1
                LOGGER.warning("[%s] Sin nombre (omitido): %s", sector_label, url)
                continue

            await csv_writer.write_record(record)
            local_processed += 1
            metrics["processed"] += 1

            if local_processed % 10 == 0:
                LOGGER.info(
                    "[%s] Progreso: %d/%d procesados | %d válidos | %d errores",
                    sector_label, local_processed, len(refs), csv_writer.total_written, local_errors,
                )
                LOGGER.info(
                    "STATS discovered=%d processed=%d valid=%d errors=%d",
                    metrics["discovered"], metrics["processed"],
                    csv_writer.total_written, metrics["errors"],
                )
        except Exception as exc:  # noqa: BLE001
            local_errors += 1
            metrics["errors"] += 1
            LOGGER.warning("[%s] Error procesando %s: %s", sector_label, url, exc)


MIN_CELL_DEG = 0.002  # ~220 m — límite mínimo de subdivisión adaptativa


def _subdivide(sector: Sector) -> list:
    """Divide un sector en 4 sub-sectores (NW, NE, SW, SE) con la mitad del tamaño."""
    half = sector.cell_deg / 2
    quarter = half / 2
    new_zoom = min(sector.zoom + 1, 16)
    return [
        Sector(lat=sector.lat + quarter, lon=sector.lon - quarter, zoom=new_zoom, cell_deg=half),
        Sector(lat=sector.lat + quarter, lon=sector.lon + quarter, zoom=new_zoom, cell_deg=half),
        Sector(lat=sector.lat - quarter, lon=sector.lon - quarter, zoom=new_zoom, cell_deg=half),
        Sector(lat=sector.lat - quarter, lon=sector.lon + quarter, zoom=new_zoom, cell_deg=half),
    ]


async def _process_sector(
    label: str,
    sector: Sector,
    pool: ContextPool,
    query: str,
    csv_writer: StreamingCsvWriter,
    args: argparse.Namespace,
    metrics: dict,
) -> None:
    """Procesa un sector geográfico: search → collect → extract → write CSV.

    La subdivisión adaptativa ocurre FUERA del bloque try/finally para que el
    contexto Playwright se libere al pool ANTES de lanzar los sub-sectores.
    Sin esto, con concurrency=N todos los slots quedan ocupados esperando
    sub-tareas que nunca pueden adquirir un slot → deadlock.
    """
    pooled: PooledContext = await pool.acquire()
    needs_subdivision = False
    try:
        LOGGER.info(
            "── Sector %s @ %.5f, %.5f zoom=%d (cell=%.4f°) ──",
            label, sector.lat, sector.lon, sector.zoom, sector.cell_deg,
        )

        await retry_async(
            lambda: open_maps_and_search(
                pooled.page, query, lat=sector.lat, lon=sector.lon, zoom=sector.zoom
            ),
            attempts=3,
        )

        result = await collect_result_refs(
            page=pooled.page,
            slow_ms=args.slow_ms,
            max_results=args.max_results,
        )

        discovered = len(result.refs)
        metrics["discovered"] += discovered
        LOGGER.info("[%s] Descubiertos: %d (acumulado: %d)", label, discovered, metrics["discovered"])
        # Stats tempranas — la UI las muestra nada más terminar el discovery
        LOGGER.info(
            "STATS discovered=%d processed=%d valid=%d errors=%d",
            metrics["discovered"], metrics["processed"], csv_writer.total_written, metrics["errors"],
        )

        await _process_refs(
            refs=result.refs,
            page=pooled.page,
            query=query,
            slow_ms=args.slow_ms,
            sector_label=label,
            csv_writer=csv_writer,
            metrics=metrics,
        )

        LOGGER.info("[%s] Sector completado: %d válidos en CSV", label, csv_writer.total_written)
        # Stats finales del sector
        LOGGER.info(
            "STATS discovered=%d processed=%d valid=%d errors=%d",
            metrics["discovered"], metrics["processed"], csv_writer.total_written, metrics["errors"],
        )

        needs_subdivision = args.adaptive_subdivision and not result.reached_end

    except Exception as exc:  # noqa: BLE001
        LOGGER.error("[%s] Sector falló: %s", label, exc)
        metrics["errors"] += 1
    finally:
        # Liberar el slot SIEMPRE antes de lanzar sub-tareas (evita deadlock)
        await pool.release(pooled)

    # ── Subdivisión adaptativa (fuera del try, contexto ya liberado) ───────
    if needs_subdivision:
        if sector.cell_deg > MIN_CELL_DEG:
            sub_sectors = _subdivide(sector)
            LOGGER.info(
                "[%s] ↳ Subdividiendo en %d (cell %.4f° → %.4f°)",
                label, len(sub_sectors), sector.cell_deg, sector.cell_deg / 2,
            )
            sub_tasks = [
                _process_sector(f"{label}.{i + 1}", sub, pool, query, csv_writer, args, metrics)
                for i, sub in enumerate(sub_sectors)
            ]
            await asyncio.gather(*sub_tasks)
        else:
            LOGGER.warning(
                "[%s] ⚠ Celda mínima (%.4f°) — puede haber resultados sin capturar",
                label, sector.cell_deg,
            )
            metrics["heuristic_stops"] += 1


async def _run(args: argparse.Namespace) -> None:
    query = f"{args.category} en {args.city}"
    start_ts = time.perf_counter()

    # ── 1. Construir lista de sectores ──────────────────────────────────────
    if args.zones:
        LOGGER.info("Modo manual: leyendo zonas desde --zones")
        try:
            zones_data = json.loads(args.zones)
        except json.JSONDecodeError as exc:
            raise ValueError(f"--zones no es un JSON válido: {exc}") from exc
        sectors = [
            Sector(lat=z["lat"], lon=z["lon"], zoom=z.get("zoom", 14))
            for z in zones_data
        ]
        LOGGER.info("Zonas manuales: %d sectores", len(sectors))
    else:
        LOGGER.info("Consultando Nominatim para: %s", args.city)
        geodata = await fetch_city_geodata(args.city)
        raw_sectors = build_sector_grid(geodata.bbox, cell_deg=0.01, zoom=14)
        sectors = filter_by_polygon(raw_sectors, geodata.polygon_geojson)
        LOGGER.info(
            "Grid generado: %d sectores (de %d en bbox) para %s",
            len(sectors), len(raw_sectors), geodata.display_name,
        )

    if not sectors:
        LOGGER.error("No hay sectores que procesar. Revisa el nombre de la ciudad.")
        return

    # ── 2. Inicializar CSV streaming ────────────────────────────────────────
    csv_writer = StreamingCsvWriter(args.output)
    LOGGER.info("CSV: %s", args.output)

    # ── 3. Lanzar browser + pool ────────────────────────────────────────────
    metrics = {"discovered": 0, "processed": 0, "errors": 0, "heuristic_stops": 0}

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=args.headless)
    pool = ContextPool(browser=browser, n=args.concurrency, timeout_ms=args.timeout_ms)

    LOGGER.info(
        "Iniciando: %d sectores | concurrencia=%d | query='%s'",
        len(sectors), args.concurrency, query,
    )

    try:
        tasks = [
            _process_sector(f"{i + 1}/{len(sectors)}", s, pool, query, csv_writer, args, metrics)
            for i, s in enumerate(sectors)
        ]
        await asyncio.gather(*tasks)
    finally:
        await browser.close()
        await pw.stop()

    # ── 4. Resumen ──────────────────────────────────────────────────────────
    elapsed = time.perf_counter() - start_ts
    LOGGER.info("── Resumen final ──")
    LOGGER.info(
        "discover=%d processed=%d valid=%d duplicates=%d errors=%d elapsed_s=%.2f",
        metrics["discovered"],
        metrics["processed"],
        csv_writer.total_written,
        metrics["processed"] - csv_writer.total_written,
        metrics["errors"],
        elapsed,
    )
    if metrics["heuristic_stops"] > 0:
        LOGGER.warning(
            "⚠ %d sector(es) se detuvieron por heurística — puede haber resultados fuera del viewport",
            metrics["heuristic_stops"],
        )
    else:
        LOGGER.info("✓ Todos los sectores confirmaron fin de resultados")


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
