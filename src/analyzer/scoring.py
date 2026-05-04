"""Sistema de scoring de prioridad comercial parametrizable.

Lee `config/scoring_weights.json`, `config/scoring_avatars.json` y
`config/eci_locations.json` y devuelve para cada negocio un dict con
puntuación 0–100, tramo de prioridad y justificación legible.

El módulo NO cachea las configs — cada llamada a `load_*` re-lee el JSON,
permitiendo modificar pesos/avatares en caliente entre ejecuciones del
analizador.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_WEIGHTS = _REPO_ROOT / "config" / "scoring_weights.json"
_DEFAULT_AVATARS = _REPO_ROOT / "config" / "scoring_avatars.json"
_DEFAULT_ECI = _REPO_ROOT / "config" / "eci_locations.json"


# ─── Loaders ────────────────────────────────────────────────────────────

def load_weights(path: Optional[str] = None) -> Dict:
    p = Path(path) if path else _DEFAULT_WEIGHTS
    return json.loads(p.read_text(encoding="utf-8"))


def load_avatares(path: Optional[str] = None) -> List[Dict]:
    p = Path(path) if path else _DEFAULT_AVATARS
    return json.loads(p.read_text(encoding="utf-8"))["avatares"]


def load_eci_locations(path: Optional[str] = None) -> List[Dict]:
    p = Path(path) if path else _DEFAULT_ECI
    return json.loads(p.read_text(encoding="utf-8"))["centros"]


# ─── Geometría ──────────────────────────────────────────────────────────

from src.geo.coords import coords_from_maps_url  # noqa: F401  (re-exportado para compatibilidad)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearest_eci_distance_km(
    lat: float, lon: float, eci_locations: List[Dict],
) -> Tuple[float, str]:
    """Devuelve (distancia_km, ciudad_eci) del centro ECI más cercano."""
    best_d, best_name = float("inf"), ""
    for eci in eci_locations:
        d = haversine_km(lat, lon, eci["lat"], eci["lon"])
        if d < best_d:
            best_d, best_name = d, eci["ciudad"]
    return best_d, best_name


# ─── Conteo de tiendas por marca ────────────────────────────────────────

_NUM_RE = re.compile(r"\d+")
_PAREN_RE = re.compile(r"\([^)]*\)")
_PUNCT_RE = re.compile(r"[\-_,\.\|/&]")


def normalize_brand_key(name: str) -> str:
    """Normaliza el nombre quitando paréntesis, números y puntuación."""
    s = (name or "").lower().strip()
    s = _PAREN_RE.sub("", s)
    s = _NUM_RE.sub("", s)
    s = _PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _brand_signature(name: str) -> str:
    """Firma de marca: primera palabra significativa (>=3 chars) del nombre normalizado.
    Se evita usar palabras genéricas comunes como 'tienda', 'moda'."""
    full = normalize_brand_key(name)
    if not full:
        return ""
    blocked = {"tienda", "tiendas", "moda", "modas", "boutique", "shop", "store", "the", "los", "las", "el", "la"}
    for word in full.split():
        if len(word) >= 3 and word not in blocked:
            return word
    # Fallback: primera palabra
    return full.split()[0] if full else ""


def count_stores_by_brand(rows: List[Dict], name_field: str = "nombre") -> Dict[str, int]:
    """Devuelve {firma_marca: nº de filas con esa firma}."""
    counts: Dict[str, int] = {}
    for r in rows:
        sig = _brand_signature(r.get(name_field, ""))
        if not sig:
            continue
        counts[sig] = counts.get(sig, 0) + 1
    return counts


def num_tiendas_for(name: str, brand_counts: Dict[str, int]) -> int:
    """Devuelve cuántas tiendas tiene la marca de este negocio (mín 1)."""
    sig = _brand_signature(name)
    return brand_counts.get(sig, 1) if sig else 1


# ─── Scoring por criterio ───────────────────────────────────────────────

def _band_score(value: float, bands: List[Dict], min_key: str, max_key: str) -> Tuple[int, str]:
    for b in bands:
        if b[min_key] <= value <= b[max_key]:
            return int(b["puntos"]), str(b["etiqueta"])
    return 0, "fuera de banda"


def score_distancia_eci(distancia_km: float, weights: Dict) -> Tuple[int, str]:
    bands = weights["criterios"]["distancia_eci"]["bandas"]
    return _band_score(distancia_km, bands, "min_km", "max_km")


def score_poblacion(poblacion: int, weights: Dict) -> Tuple[int, str]:
    bands = weights["criterios"]["poblacion_municipio"]["bandas"]
    return _band_score(poblacion, bands, "min", "max")


def score_num_tiendas(n: int, weights: Dict) -> Tuple[int, str]:
    bands = weights["criterios"]["num_tiendas"]["bandas"]
    return _band_score(n, bands, "min", "max")


def score_madurez_digital(
    madurez: str, weights: Dict, tecnologia: Optional[str] = None,
) -> Tuple[int, str]:
    cfg = weights["criterios"]["madurez_digital"]
    if madurez == "ecommerce_funcional" and tecnologia:
        por_tec = cfg.get("por_tecnologia", {}) or {}
        if tecnologia in por_tec:
            return int(por_tec[tecnologia]), f"ecommerce_funcional ({tecnologia})"
    pts = int(cfg["valores"].get(madurez, 0))
    return pts, madurez


# ─── Scoring de avatar ──────────────────────────────────────────────────

def _avatar_check(ctx: Dict, criterios: Dict) -> Tuple[int, int]:
    """Devuelve (cumplidos, total_aplicables). El criterio ecommerce sólo cuenta
    cuando el avatar lo requiere — si no lo requiere, no se evalúa (ni suma ni resta)."""
    total = 0
    cumple = 0

    pmin, pmax = criterios["poblacion_municipio"]
    total += 1
    if pmin <= int(ctx.get("poblacion") or 0) <= pmax:
        cumple += 1

    dmin, dmax = criterios["distancia_eci_km"]
    d = ctx.get("distancia_eci_km", -1)
    total += 1
    if d is not None and d >= 0 and dmin <= d <= dmax:
        cumple += 1

    tmin, tmax = criterios["num_tiendas"]
    total += 1
    if tmin <= int(ctx.get("num_tiendas") or 0) <= tmax:
        cumple += 1

    if criterios.get("ecommerce_requerido", False):
        total += 1
        if ctx.get("ecommerce", False):
            cumple += 1

    return cumple, total


def score_avatar(
    ctx: Dict, avatares: List[Dict], weights: Dict,
) -> Tuple[int, str, Optional[int]]:
    """Devuelve (puntos, etiqueta, avatar_id) del mejor avatar que encaja."""
    valores = weights["criterios"]["encaje_avatar"]["valores"]
    best_pts = 0
    best_label = "no encaja con ningún avatar"
    best_id: Optional[int] = None
    for av in avatares:
        cumple, total = _avatar_check(ctx, av["criterios"])
        if cumple == total:
            pts = int(valores["encaje_claro"])
            label = f"encaje claro con Avatar {av['id']} ({av['nombre']})"
        elif cumple >= int(av.get("encaje_parcial_si_cumple_n", 2)):
            pts = int(valores["encaje_parcial"])
            label = f"encaje parcial con Avatar {av['id']} ({av['nombre']})"
        else:
            continue
        if pts > best_pts:
            best_pts, best_label, best_id = pts, label, av["id"]
    return best_pts, best_label, best_id


# ─── Tramo de prioridad ─────────────────────────────────────────────────

def tramo_for_score(puntos: int, weights: Dict) -> Tuple[str, str]:
    tramos = sorted(weights["tramos_prioridad"], key=lambda t: -int(t["min_puntos"]))
    for t in tramos:
        if puntos >= int(t["min_puntos"]):
            return str(t["id"]), str(t["etiqueta"])
    return "P4", "Prioridad mínima"


# ─── Cálculo total ──────────────────────────────────────────────────────

def compute_score(
    ctx: Dict,
    eci_locations: List[Dict],
    avatares: List[Dict],
    weights: Dict,
) -> Dict:
    """ctx admite: lat, lon, poblacion, num_tiendas, madurez.
    madurez ∈ {'ecommerce_funcional', 'solo_redes_sociales', 'sin_presencia'}.
    """
    breakdown: Dict[str, Dict] = {}
    justif_parts: List[str] = []

    # Distancia ECI
    if ctx.get("lat") is not None and ctx.get("lon") is not None and eci_locations:
        d, eci_name = nearest_eci_distance_km(ctx["lat"], ctx["lon"], eci_locations)
        pts_d, et_d = score_distancia_eci(d, weights)
        breakdown["distancia_eci"] = {
            "puntos": pts_d, "valor_km": round(d, 1), "etiqueta": et_d, "eci": eci_name,
        }
        justif_parts.append(f"ECI {eci_name} a {round(d, 1)}km [{et_d}={pts_d}pts]")
        ctx["distancia_eci_km"] = d
    else:
        breakdown["distancia_eci"] = {"puntos": 0, "valor_km": None, "etiqueta": "sin coordenadas"}
        justif_parts.append("sin coordenadas (0pts dist)")
        ctx["distancia_eci_km"] = -1
        pts_d = 0

    # Población
    pob = int(ctx.get("poblacion") or 0)
    pts_p, et_p = score_poblacion(pob, weights)
    breakdown["poblacion"] = {"puntos": pts_p, "valor": pob, "etiqueta": et_p}
    justif_parts.append(f"pob {pob:,} [{et_p}={pts_p}pts]")

    # Núm tiendas
    n_t = int(ctx.get("num_tiendas") or 1)
    pts_t, et_t = score_num_tiendas(n_t, weights)
    breakdown["num_tiendas"] = {"puntos": pts_t, "valor": n_t, "etiqueta": et_t}
    justif_parts.append(f"{n_t} tiendas [{et_t}={pts_t}pts]")

    # Madurez digital
    madurez = ctx.get("madurez", "sin_presencia")
    tecnologia = ctx.get("tecnologia")
    pts_m, et_m = score_madurez_digital(madurez, weights, tecnologia)
    breakdown["madurez_digital"] = {"puntos": pts_m, "valor": madurez, "etiqueta": et_m}
    justif_parts.append(f"madurez={et_m} [{pts_m}pts]")

    # Avatar
    ctx["ecommerce"] = ctx.get("madurez") == "ecommerce_funcional"
    pts_a, et_a, av_id = score_avatar(ctx, avatares, weights)
    breakdown["avatar"] = {"puntos": pts_a, "valor_avatar_id": av_id, "etiqueta": et_a}
    justif_parts.append(f"{et_a} [{pts_a}pts]")

    total = pts_d + pts_p + pts_t + pts_m + pts_a
    pid, plabel = tramo_for_score(total, weights)

    return {
        "puntuacion_total": total,
        "prioridad": pid,
        "prioridad_etiqueta": plabel,
        "justificacion": "; ".join(justif_parts),
        "breakdown": breakdown,
    }
