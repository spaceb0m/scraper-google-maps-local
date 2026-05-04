from __future__ import annotations

import re
from typing import Optional, Tuple

_COORDS_AT_RE = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")
_COORDS_DATA_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")


def coords_from_maps_url(url: str) -> Tuple[Optional[float], Optional[float]]:
    """Extrae (lat, lon) de un URL de Google Maps. Soporta dos formatos:
    - .../@LAT,LON,ZOOMz/...
    - .../data=!4m...!3dLAT!4dLON!...
    Devuelve (None, None) si no encuentra ninguno."""
    if not url:
        return None, None
    m = _COORDS_DATA_RE.search(url)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _COORDS_AT_RE.search(url)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None
