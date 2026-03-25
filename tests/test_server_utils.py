from __future__ import annotations

import re

import pytest

from server import _load_history, _make_output_path, _save_history, _slugify


def test_slugify_removes_accents():
    assert _slugify("Santiago de Compostela, España") == "santiago_de_compostela_espana"


def test_slugify_lowercases():
    assert _slugify("MADRID") == "madrid"


def test_slugify_replaces_special_chars():
    assert _slugify("tiendas de ropa") == "tiendas_de_ropa"


def test_slugify_collapses_underscores():
    # comma + space → single _
    assert "__" not in _slugify("a, b")


def test_slugify_truncates_to_40():
    long_text = "a" * 60
    assert len(_slugify(long_text)) <= 40


def test_make_output_path_format():
    path = _make_output_path("Madrid, España", "restaurantes")
    assert re.match(
        r"out/madrid_espana_restaurantes_\d{8}_\d{6}\.csv", path
    ), f"Unexpected path: {path}"


def test_make_output_path_uses_out_prefix():
    path = _make_output_path("Vigo", "bares")
    assert path.startswith("out/")
    assert path.endswith(".csv")


def test_save_and_load_history(tmp_path):
    import server
    original_jobs = dict(server.jobs)
    original_path = server.HISTORY_PATH

    server.HISTORY_PATH = tmp_path / "history.json"
    server.jobs = {
        "job-1": {
            "city": "Madrid",
            "category": "bares",
            "started_at": "2026-03-25T10:00:00",
            "status": "done",
            "valid_count": 42,
            "output": "out/madrid_bares_20260325_100000.csv",
            "lines": ["log line"],
            "proc": None,
        }
    }

    _save_history()
    assert server.HISTORY_PATH.exists()

    server.jobs = {}
    _load_history()

    assert "job-1" in server.jobs
    assert server.jobs["job-1"]["city"] == "Madrid"
    assert server.jobs["job-1"]["valid_count"] == 42
    assert server.jobs["job-1"]["lines"] == []
    assert server.jobs["job-1"]["proc"] is None

    server.jobs = original_jobs
    server.HISTORY_PATH = original_path


def test_load_history_missing_file(tmp_path):
    import server
    original_path = server.HISTORY_PATH
    server.HISTORY_PATH = tmp_path / "nonexistent.json"
    server.jobs = {}
    _load_history()  # must not raise
    assert server.jobs == {}
    server.HISTORY_PATH = original_path


def test_load_history_corrupt_file(tmp_path):
    import server
    original_path = server.HISTORY_PATH
    corrupt = tmp_path / "history.json"
    corrupt.write_text("not valid json", encoding="utf-8")
    server.HISTORY_PATH = corrupt
    server.jobs = {}
    _load_history()  # must not raise
    assert server.jobs == {}
    server.HISTORY_PATH = original_path
