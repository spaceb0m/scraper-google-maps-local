from __future__ import annotations

import hashlib

from src.domain import BusinessRecord


def normalize_maps_url(url: str) -> str:
    return url.strip().split("?")[0]


def make_fallback_key(record: BusinessRecord) -> str:
    raw = "|".join([
        record.nombre.lower().strip(),
        record.direccion.lower().strip(),
        record.telefono.lower().strip(),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def dedupe_records(records: list[BusinessRecord]) -> list[BusinessRecord]:
    seen: set[str] = set()
    out: list[BusinessRecord] = []
    for record in records:
        if record.maps_url:
            key = f"url:{normalize_maps_url(record.maps_url)}"
        else:
            key = f"fallback:{make_fallback_key(record)}"
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out
