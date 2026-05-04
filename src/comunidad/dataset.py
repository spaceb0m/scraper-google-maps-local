"""Carga del dataset estático de municipios por comunidad autónoma."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_DEFAULT_DATASET = Path(__file__).resolve().parents[2] / "config" / "municipios_es.json"


def _read_dataset(dataset_path: Optional[str] = None) -> Dict:
    path = Path(dataset_path) if dataset_path else _DEFAULT_DATASET
    return json.loads(path.read_text(encoding="utf-8"))


def list_comunidades(dataset_path: Optional[str] = None) -> List[str]:
    """Devuelve la lista de comunidades disponibles en orden alfabético."""
    data = _read_dataset(dataset_path)
    return sorted(data.keys())


def load_municipios(
    comunidad: str,
    min_poblacion: int,
    dataset_path: Optional[str] = None,
) -> List[Dict]:
    """Devuelve municipios de la comunidad con población >= min_poblacion,
    ordenados de menor a mayor población (los pequeños primero — encajan mejor
    con los avatares de cabecera comarcal y permiten validar resultados rápido
    antes de afrontar las grandes urbes)."""
    data = _read_dataset(dataset_path)
    if comunidad not in data:
        raise KeyError(f"Comunidad desconocida: {comunidad}")
    municipios = data[comunidad].get("municipios", [])
    filtered = [m for m in municipios if int(m.get("poblacion", 0)) >= min_poblacion]
    filtered.sort(key=lambda m: int(m.get("poblacion", 0)))
    return filtered


def get_poblacion_municipio(
    nombre: str,
    dataset_path: Optional[str] = None,
) -> Optional[int]:
    """Busca un municipio por nombre (case-insensitive) en todas las CCAA.
    Devuelve la población o None si no se encuentra."""
    data = _read_dataset(dataset_path)
    target = nombre.strip().lower()
    for ccaa in data.values():
        for m in ccaa.get("municipios", []):
            if m["nombre"].strip().lower() == target:
                return int(m["poblacion"])
    return None
