from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Tuple

LOGGER = logging.getLogger(__name__)


@dataclass
class Sector:
    lat: float
    lon: float
    zoom: int
    cell_deg: float = 0.003  # tamaño de la celda en grados (~330 m); usado para subdivisión adaptativa

    def bbox(self, buffer: float = 0.1) -> Tuple[float, float, float, float]:
        """Devuelve (min_lat, max_lat, min_lon, max_lon) con un buffer proporcional al tamaño de celda.
        El buffer del 10% evita rechazar negocios en el borde exacto de la celda."""
        half = self.cell_deg / 2 * (1 + buffer)
        return (self.lat - half, self.lat + half, self.lon - half, self.lon + half)


def build_sector_grid(
    bbox: tuple,
    cell_deg: float = 0.003,
    zoom: int = 16,
) -> list:
    """Divide el bounding box en una cuadrícula de sectores."""
    min_lat, max_lat, min_lon, max_lon = bbox
    sectors = []
    lat = min_lat + cell_deg / 2
    while lat <= max_lat:
        lon = min_lon + cell_deg / 2
        while lon <= max_lon:
            sectors.append(Sector(lat=round(lat, 6), lon=round(lon, 6), zoom=zoom, cell_deg=cell_deg))
            lon += cell_deg
        lat += cell_deg
    return sectors


def filter_by_polygon(sectors: list, geojson: Optional[dict]) -> list:
    """Filtra sectores cuyo centro queda fuera del polígono de la zona."""
    if not geojson:
        LOGGER.warning("Sin polígono GeoJSON — usando todos los sectores del bbox")
        return sectors
    try:
        from shapely.geometry import Point, shape  # type: ignore
        polygon = shape(geojson)
        filtered = [s for s in sectors if polygon.contains(Point(s.lon, s.lat))]
        LOGGER.info(
            "GeoFilter: %d/%d sectores dentro del polígono",
            len(filtered), len(sectors),
        )
        return filtered
    except ImportError:
        LOGGER.warning("shapely no instalado — sin filtro geográfico")
        return sectors
