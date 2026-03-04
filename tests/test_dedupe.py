from src.domain import BusinessRecord
from src.pipeline.dedupe import dedupe_records


def _record(**kwargs):
    base = dict(
        nombre="A",
        telefono="",
        direccion="Calle 1",
        web="",
        rating="",
        categoria="Ropa",
        source_query="q",
        retrieved_at_utc="2026-03-03T00:00:00+00:00",
        maps_url="",
    )
    base.update(kwargs)
    return BusinessRecord(**base)


def test_dedupe_by_maps_url() -> None:
    r1 = _record(maps_url="https://maps.google.com/place/abc?hl=es")
    r2 = _record(maps_url="https://maps.google.com/place/abc?hl=en")
    result = dedupe_records([r1, r2])
    assert len(result) == 1


def test_dedupe_by_fallback() -> None:
    r1 = _record(nombre="Tienda X", direccion="Rua A", telefono="123")
    r2 = _record(nombre="tienda x", direccion="Rua A", telefono="123")
    result = dedupe_records([r1, r2])
    assert len(result) == 1
