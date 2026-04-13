from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import logging
import time
from pathlib import Path
from typing import List

import openpyxl

from src.analyzer.brand_filter import is_excluded, load_brands
from src.analyzer.fingerprint import detect_platform, fetch_page, is_social_url
from src.utils.logging import setup_logging

LOGGER = logging.getLogger(__name__)

# CSV field names (must match the scraper output)
_CSV_FIELDS = [
    "nombre", "telefono", "direccion", "web",
    "rating", "categoria", "source_query", "retrieved_at_utc", "maps_url",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Maps Scraper — Analyzer")
    parser.add_argument("--csv-path", required=True, help="Ruta al CSV de entrada")
    parser.add_argument(
        "--brands-path",
        default="config/excluded_brands.json",
        help="Ruta al JSON de marcas excluidas",
    )
    return parser


def _derive_xlsx_path(csv_path: str) -> str:
    return str(Path(csv_path).with_suffix(".xlsx"))


def _read_csv(csv_path: str) -> List[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def _dedup_rows(rows: List[dict]) -> List[dict]:
    seen: set = set()
    out: List[dict] = []
    for row in rows:
        raw = "|".join([
            row.get("nombre", "").lower().strip(),
            row.get("direccion", "").lower().strip(),
            row.get("telefono", "").lower().strip(),
        ])
        key = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


async def _run(args: argparse.Namespace) -> None:
    start_ts = time.perf_counter()

    brands = load_brands(args.brands_path)
    LOGGER.info("Marcas excluidas cargadas: %d", len(brands))

    rows = _read_csv(args.csv_path)
    rows = _dedup_rows(rows)
    LOGGER.info("Registros en CSV: %d", len(rows))

    xlsx_path = _derive_xlsx_path(args.csv_path)

    metrics = {"filtered": 0, "analyzed": 0, "stores": 0, "errors": 0}
    analysis_rows: List[dict] = []

    for row in rows:
        nombre = row.get("nombre", "")
        web = row.get("web", "").strip()

        if is_excluded(nombre, brands):
            metrics["filtered"] += 1
            LOGGER.info("[filtrado] %s", nombre)
            _emit_stats(metrics)
            continue

        # Normalizar URL: añadir https:// si falta protocolo
        if web and not web.startswith(("http://", "https://")):
            web = "https://" + web

        # Determine store status
        if not web or is_social_url(web):
            es_tienda = "-"
            tecnologia = "-"
        else:
            html = await fetch_page(web)
            if html is None:
                es_tienda = "-"
                tecnologia = "-"
                metrics["errors"] += 1
            else:
                is_store, platform = detect_platform(html)
                es_tienda = "Sí" if is_store else "No"
                tecnologia = platform if platform else "-"
                if is_store:
                    metrics["stores"] += 1

        metrics["analyzed"] += 1
        analysis_rows.append({**row, "es_tienda": es_tienda, "tecnologia": tecnologia})

        LOGGER.info(
            "[analizado] %s | web=%s | tienda=%s | plataforma=%s",
            nombre, web or "(sin web)", es_tienda, tecnologia,
        )
        _emit_stats(metrics)

    # Write XLSX
    wb = openpyxl.Workbook()

    # Sheet 1: original data
    ws1 = wb.active
    ws1.title = "Datos originales"
    if rows:
        headers = list(rows[0].keys())
        ws1.append(headers)
        for row in rows:
            ws1.append([row.get(h, "") for h in headers])

    # Sheet 2: analysis results
    ws2 = wb.create_sheet("Análisis")
    if analysis_rows:
        analysis_headers = list(analysis_rows[0].keys())
        ws2.append(analysis_headers)
        for row in analysis_rows:
            ws2.append([row.get(h, "") for h in analysis_headers])

    wb.save(xlsx_path)
    LOGGER.info("XLSX guardado: %s", xlsx_path)

    elapsed = time.perf_counter() - start_ts
    LOGGER.info(
        "── Resumen análisis ──\ntotal=%d filtrados=%d analizados=%d tiendas=%d errores=%d elapsed_s=%.2f",
        len(rows),
        metrics["filtered"],
        metrics["analyzed"],
        metrics["stores"],
        metrics["errors"],
        elapsed,
    )
    _emit_stats(metrics)


def _emit_stats(metrics: dict) -> None:
    LOGGER.info(
        "ASTATS filtered=%d analyzed=%d stores=%d errors=%d",
        metrics["filtered"], metrics["analyzed"], metrics["stores"], metrics["errors"],
    )


def main() -> None:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
