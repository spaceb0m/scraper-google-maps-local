from __future__ import annotations

import re

import pytest

from server import _make_output_path, _slugify


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
