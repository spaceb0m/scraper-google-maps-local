import json
import pytest
from src.analyzer.brand_filter import load_brands, is_excluded


def test_is_excluded_exact_match():
    brands = ["ZARA", "MANGO"]
    assert is_excluded("ZARA", brands) is True


def test_is_excluded_substring():
    brands = ["Adolfo Dominguez"]
    assert is_excluded("Adolfo Dominguez (Santiago de Compostela)", brands) is True


def test_is_excluded_case_insensitive():
    brands = ["ZARA"]
    assert is_excluded("zara kids", brands) is True


def test_is_not_excluded():
    brands = ["ZARA", "MANGO"]
    assert is_excluded("Tienda de zapatos", brands) is False


def test_is_excluded_empty_brands():
    assert is_excluded("ZARA", []) is False


def test_load_brands(tmp_path):
    config = tmp_path / "brands.json"
    config.write_text(json.dumps({"brands": ["ZARA", "MANGO"]}), encoding="utf-8")
    brands = load_brands(str(config))
    assert brands == ["ZARA", "MANGO"]


def test_load_brands_empty_file(tmp_path):
    config = tmp_path / "brands.json"
    config.write_text(json.dumps({}), encoding="utf-8")
    assert load_brands(str(config)) == []
