from __future__ import annotations

import json

import pytest

from src.comunidad.dataset import (
    get_poblacion_municipio,
    list_comunidades,
    load_municipios,
)

FIXTURE = {
    "Galicia": {
        "provincias": ["A Coruña"],
        "municipios": [
            {"nombre": "Vigo", "provincia": "Pontevedra", "poblacion": 293642},
            {"nombre": "Aldea", "provincia": "A Coruña", "poblacion": 1200},
            {"nombre": "Carballo", "provincia": "A Coruña", "poblacion": 31370},
        ],
    },
    "Cataluña": {
        "provincias": ["Barcelona"],
        "municipios": [
            {"nombre": "Barcelona", "provincia": "Barcelona", "poblacion": 1620343},
        ],
    },
}


@pytest.fixture()
def dataset_path(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return str(p)


def test_list_comunidades_alphabetic(dataset_path):
    assert list_comunidades(dataset_path=dataset_path) == ["Cataluña", "Galicia"]


def test_load_municipios_filters_by_min_poblacion(dataset_path):
    result = load_municipios("Galicia", 5000, dataset_path=dataset_path)
    nombres = [m["nombre"] for m in result]
    assert "Vigo" in nombres
    assert "Carballo" in nombres
    assert "Aldea" not in nombres


def test_load_municipios_sorted_by_poblacion_asc(dataset_path):
    """Los pequeños primero: encajan con avatares de cabecera comarcal."""
    result = load_municipios("Galicia", 5000, dataset_path=dataset_path)
    assert result[0]["nombre"] == "Carballo"
    assert result[-1]["nombre"] == "Vigo"


def test_load_municipios_unknown_raises(dataset_path):
    with pytest.raises(KeyError):
        load_municipios("Cantabria", 5000, dataset_path=dataset_path)


def test_get_poblacion_municipio_match(dataset_path):
    assert get_poblacion_municipio("Vigo", dataset_path=dataset_path) == 293642


def test_get_poblacion_municipio_case_insensitive(dataset_path):
    assert get_poblacion_municipio("vigo", dataset_path=dataset_path) == 293642
    assert get_poblacion_municipio("BARCELONA", dataset_path=dataset_path) == 1620343


def test_get_poblacion_municipio_not_found(dataset_path):
    assert get_poblacion_municipio("Inventado", dataset_path=dataset_path) is None
