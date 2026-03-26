from __future__ import annotations

import json
from pathlib import Path
from typing import List


def load_brands(path: str) -> List[str]:
    """Lee la lista de marcas excluidas desde un fichero JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [str(b) for b in data.get("brands", [])]


def is_excluded(name: str, brands: List[str]) -> bool:
    """Devuelve True si el nombre contiene alguna marca (case-insensitive, subcadena)."""
    name_lower = name.lower()
    return any(brand.lower() in name_lower for brand in brands)
