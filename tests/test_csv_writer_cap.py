"""Tests del cap global max_records en StreamingCsvWriter."""
from __future__ import annotations

import asyncio

import pytest

from src.domain import BusinessRecord
from src.pipeline.csv_writer import StreamingCsvWriter


def _record(n: int) -> BusinessRecord:
    return BusinessRecord(
        nombre=f"Negocio {n}",
        telefono="",
        direccion=f"Calle {n}",
        web="",
        rating="",
        categoria="",
        source_query="",
        retrieved_at_utc="",
        maps_url=f"https://maps.google.com/p/{n}",
    )


async def _make_and_write(path: str, max_records: int, n: int) -> StreamingCsvWriter:
    writer = StreamingCsvWriter(path, max_records=max_records)
    for i in range(n):
        await writer.write_record(_record(i))
    return writer


def test_writer_no_cap_writes_all(tmp_path):
    writer = asyncio.run(_make_and_write(str(tmp_path / "a.csv"), 0, 5))
    assert writer.total_written == 5
    assert writer.is_full is False


def test_writer_cap_stops_writing(tmp_path):
    writer = asyncio.run(_make_and_write(str(tmp_path / "b.csv"), 3, 10))
    assert writer.total_written == 3
    assert writer.is_full is True


def test_writer_cap_zero_means_unlimited(tmp_path):
    writer = asyncio.run(_make_and_write(str(tmp_path / "c.csv"), 0, 50))
    assert writer.total_written == 50
    assert writer.is_full is False
