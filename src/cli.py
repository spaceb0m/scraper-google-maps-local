from __future__ import annotations

import argparse
import asyncio
import logging
import random
import time
from dataclasses import asdict

from src.browser.session import start_session, stop_session
from src.pipeline.dedupe import dedupe_records
from src.pipeline.export_csv import export_csv
from src.scraper.maps_detail import extract_business_record
from src.scraper.maps_search import collect_result_refs, open_maps_and_search
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
    return parser


async def _run(args: argparse.Namespace) -> None:
    query = f"{args.category} en {args.city}"
    start_ts = time.perf_counter()

    session = await start_session(headless=args.headless, timeout_ms=args.timeout_ms)
    page = session.page

    discovered = 0
    processed = 0
    errors = 0
    records = []

    try:
        LOGGER.info("Búsqueda: %s", query)
        await retry_async(lambda: open_maps_and_search(page, query), attempts=3)

        refs = await collect_result_refs(
            page=page,
            slow_ms=args.slow_ms,
            max_results=args.max_results,
        )
        discovered = len(refs)
        LOGGER.info("Resultados descubiertos: %s", discovered)

        for ref in refs:
            async def go_to_detail() -> None:
                await page.goto(ref.maps_url, wait_until="domcontentloaded")

            try:
                await retry_async(go_to_detail, attempts=2)
                await asyncio.sleep((args.slow_ms + random.randint(20, 150)) / 1000)
                record = await retry_async(
                    lambda: extract_business_record(page, query),
                    attempts=2,
                )
                if not record.nombre:
                    errors += 1
                    continue
                records.append(record)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                errors += 1
                LOGGER.warning("Error procesando %s: %s", ref.maps_url, exc)
                await page.screenshot(path=f"out/error_{errors}.png", full_page=False)
                content = await page.content()
                with open(f"out/error_{errors}.html", "w", encoding="utf-8") as handle:
                    handle.write(content)

        deduped = dedupe_records(records)
        duplicates = len(records) - len(deduped)

        export_csv(args.output, deduped)

        elapsed = time.perf_counter() - start_ts
        LOGGER.info("Ejecución finalizada")
        LOGGER.info(
            "discover=%s processed=%s valid=%s duplicates=%s errors=%s elapsed_s=%.2f",
            discovered,
            processed,
            len(deduped),
            duplicates,
            errors,
            elapsed,
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
