from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from dataclasses import asdict
from typing import Any

from src.browser.session import start_session, stop_session
from src.pipeline.dedupe import dedupe_records
from src.pipeline.export_csv import export_csv
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
    parser = argparse.ArgumentParser(description="Google Maps Scraper MVP")
    parser.add_argument("--city", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--headless", type=parse_bool, default=True)
    parser.add_argument("--max-results", type=int, default=0)
    parser.add_argument("--slow-ms", type=int, default=250)
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument(
        "--zones",
        type=str,
        default=None,
        help=(
            'JSON con lista de zonas geográficas para cobertura completa. '
            'Ejemplo: \'[{"lat": 42.879, "lon": -8.544, "zoom": 14}]\''
        ),
    )
    return parser


async def _process_refs(
    refs: list[SearchResultRef],
    page: Any,
    query: str,
    slow_ms: int,
    discovered_total: int,
    errors_offset: int,
) -> tuple[list, int]:
    """Procesa una lista de refs y devuelve (records, errors)."""
    records = []
    processed = 0
    errors = errors_offset

    for ref in refs:
        async def go_to_detail() -> None:
            await page.goto(ref.maps_url, wait_until="domcontentloaded")

        try:
            await retry_async(go_to_detail, attempts=2)
            await asyncio.sleep((slow_ms + random.randint(20, 150)) / 1000)
            record = await retry_async(
                lambda: extract_business_record(page, query),
                attempts=2,
            )
            if not record.nombre:
                errors += 1
                LOGGER.warning("Sin nombre (omitido): %s", ref.maps_url)
                continue
            records.append(record)
            processed += 1
            if processed % 10 == 0:
                LOGGER.info(
                    "Progreso: %s/%s procesados | %s válidos | %s errores",
                    processed,
                    discovered_total,
                    len(records),
                    errors,
                )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            LOGGER.warning("Error procesando %s: %s", ref.maps_url, exc)
            await page.screenshot(path=f"out/error_{errors}.png", full_page=False)
            content = await page.content()
            with open(f"out/error_{errors}.html", "w", encoding="utf-8") as handle:
                handle.write(content)

    return records, errors


async def _run(args: argparse.Namespace) -> None:
    query = f"{args.category} en {args.city}"
    start_ts = time.perf_counter()

    # Parsear zonas si se han proporcionado
    zones: list[dict] = []
    if args.zones:
        try:
            zones = json.loads(args.zones)
            LOGGER.info("Modo multi-zona: %s zonas configuradas", len(zones))
        except json.JSONDecodeError as exc:
            raise ValueError(f"--zones no es un JSON válido: {exc}") from exc

    session = await start_session(headless=args.headless, timeout_ms=args.timeout_ms)
    page = session.page

    all_records: list = []
    total_discovered = 0
    total_errors = 0
    all_reached_end = True  # Se pondrá False si alguna zona no confirma el fin

    # Si no hay zonas, ejecutar en modo simple (sin coordenadas específicas)
    run_zones = zones if zones else [{}]

    try:
        for zone_idx, zone in enumerate(run_zones):
            lat = zone.get("lat")
            lon = zone.get("lon")
            zoom = zone.get("zoom")

            if zones:
                LOGGER.info(
                    "── Zona %s/%s @ %.5f, %.5f zoom=%s ──",
                    zone_idx + 1,
                    len(run_zones),
                    lat,
                    lon,
                    zoom,
                )

            LOGGER.info("Búsqueda: %s", query)
            await retry_async(
                lambda: open_maps_and_search(page, query, lat=lat, lon=lon, zoom=zoom),
                attempts=3,
            )

            result = await collect_result_refs(
                page=page,
                slow_ms=args.slow_ms,
                max_results=args.max_results,
            )

            zone_discovered = len(result.refs)
            total_discovered += zone_discovered

            if not result.reached_end:
                all_reached_end = False

            LOGGER.info(
                "Resultados descubiertos en esta zona: %s (acumulado: %s)",
                zone_discovered,
                total_discovered,
            )

            zone_records, total_errors = await _process_refs(
                refs=result.refs,
                page=page,
                query=query,
                slow_ms=args.slow_ms,
                discovered_total=total_discovered,
                errors_offset=total_errors,
            )
            all_records.extend(zone_records)

        # Deduplicación global (especialmente útil en modo multi-zona)
        deduped = dedupe_records(all_records)
        duplicates = len(all_records) - len(deduped)

        export_csv(args.output, deduped)

        elapsed = time.perf_counter() - start_ts

        LOGGER.info("── Resumen final ──")
        LOGGER.info(
            "discover=%s processed=%s valid=%s duplicates=%s errors=%s elapsed_s=%.2f",
            total_discovered,
            len(all_records),
            len(deduped),
            duplicates,
            total_errors,
            elapsed,
        )
        LOGGER.info(
            "Deduplicación: %s duplicados eliminados → %s registros únicos",
            duplicates,
            len(deduped),
        )

        if zones:
            if all_reached_end:
                LOGGER.info(
                    "✓ Cobertura completa: todas las zonas confirmaron fin de resultados"
                )
            else:
                LOGGER.warning(
                    "⚠ Alguna zona se detuvo por heurística — considera añadir más zonas o reducir el zoom"
                )
        else:
            if all_reached_end:
                LOGGER.info(
                    "✓ Fin de resultados confirmado por Google Maps para el viewport actual"
                )
            else:
                LOGGER.warning(
                    "⚠ Parada por heurística — puede haber más resultados fuera del viewport. "
                    "Usa --zones para cubrir toda la ciudad"
                )

        if deduped:
            LOGGER.debug("Primer registro: %s", asdict(deduped[0]))

    finally:
        await stop_session(session)


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
