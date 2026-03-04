import csv

from src.domain import BusinessRecord
from src.pipeline.export_csv import export_csv


def test_export_csv_writes_headers_and_rows(tmp_path) -> None:
    out = tmp_path / "data.csv"
    rows = [
        BusinessRecord(
            nombre="Tienda A",
            telefono="123",
            direccion="Rua 1",
            web="https://a.com",
            rating="4.5",
            categoria="Ropa",
            source_query="q",
            retrieved_at_utc="2026-03-03T00:00:00+00:00",
            maps_url="https://maps.google.com/a",
        )
    ]
    export_csv(str(out), rows)

    with out.open("r", encoding="utf-8") as handle:
        data = list(csv.DictReader(handle))

    assert len(data) == 1
    assert data[0]["nombre"] == "Tienda A"
    assert data[0]["categoria"] == "Ropa"
