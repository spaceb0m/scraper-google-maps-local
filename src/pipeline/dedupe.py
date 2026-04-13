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
        url_key = f"url:{normalize_maps_url(record.maps_url)}" if record.maps_url else None
        fallback_key = f"fallback:{make_fallback_key(record)}"
        if (url_key and url_key in seen) or fallback_key in seen:
            continue
        if url_key:
            seen.add(url_key)
        seen.add(fallback_key)
        out.append(record)
    return out
