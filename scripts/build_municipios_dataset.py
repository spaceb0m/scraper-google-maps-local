"""Genera config/municipios_es.json a partir de Wikipedia.

Fuente: https://es.wikipedia.org/wiki/Anexo:Municipios_de_España_por_población
Esta página contiene 1300+ municipios de España con población >= 5.000 hab,
organizados en varias tablas por tramo de población. Se parsean todas las
tablas y se agrupan por comunidad autónoma.

Uso:
    python scripts/build_municipios_dataset.py [--output config/municipios_es.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

WIKIPEDIA_URL = "https://es.wikipedia.org/wiki/Anexo:Municipios_de_Espa%C3%B1a_por_poblaci%C3%B3n"

# Las celdas vienen tipo "Madrid&nbsp;Madrid" — bandera+nombre. Quedarnos
# con el lado derecho (texto sin enlace).
_NBSP = " "


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 scraper-google-maps-local/0.8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _clean_cell(raw: str) -> str:
    """Limpia una celda HTML: quita tags, comprime espacios."""
    # Sustituir &nbsp; (incluso en forma char) por espacio normal
    text = raw.replace("&nbsp;", " ").replace(_NBSP, " ")
    # Quitar tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decodificar entidades HTML básicas
    text = text.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    # Comprimir espacios
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedup_text(text: str) -> str:
    """'Madrid Madrid' / 'La CoruñaLa Coruña' -> 'Madrid' / 'La Coruña'.
    El texto viene duplicado porque hay un icono (alt) + enlace con el mismo nombre."""
    # Caso 1: texto exactamente duplicado sin separador en medio (longitud par)
    n = len(text)
    if n >= 2 and n % 2 == 0:
        half = n // 2
        if text[:half] == text[half:]:
            return text[:half].strip()
    # Caso 2: separado por espacio: dividir por palabras
    parts = text.split()
    np = len(parts)
    if np >= 2 and np % 2 == 0:
        h = np // 2
        if parts[:h] == parts[h:]:
            return " ".join(parts[:h])
    return text


def _parse_population(text: str) -> int:
    """'1 731 649' o '5 015' -> entero."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def parse_wikipedia(html: str) -> List[Dict]:
    """Parsea todas las tablas wikitable y devuelve lista de municipios."""
    tables = re.findall(
        r'<table[^>]*class="[^"]*wikitable[^"]*"[^>]*>(.*?)</table>',
        html, re.DOTALL,
    )
    municipios: List[Dict] = []
    for table_html in tables:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
        for row in rows:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.DOTALL)
            if len(cells) < 5:
                continue
            cleaned = [_clean_cell(c) for c in cells]
            # Saltar cabeceras (rank no es número)
            if not re.match(r"^\d+", cleaned[0]):
                continue
            try:
                rank = int(re.match(r"^\d+", cleaned[0]).group(0))
            except Exception:
                continue
            nombre = _dedup_text(cleaned[1])
            poblacion = _parse_population(cleaned[2])
            provincia = _dedup_text(cleaned[3])
            ccaa = _dedup_text(cleaned[4])
            if poblacion < 5000 or not nombre or not ccaa:
                continue
            municipios.append({
                "rank": rank,
                "nombre": nombre,
                "poblacion": poblacion,
                "provincia": provincia,
                "comunidad": ccaa,
            })
    return municipios


def group_by_ccaa(municipios: List[Dict]) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for m in municipios:
        ccaa = m["comunidad"]
        if ccaa not in out:
            out[ccaa] = {"provincias": [], "municipios": []}
        if m["provincia"] not in out[ccaa]["provincias"]:
            out[ccaa]["provincias"].append(m["provincia"])
        out[ccaa]["municipios"].append({
            "nombre": m["nombre"],
            "provincia": m["provincia"],
            "poblacion": m["poblacion"],
        })
    # Ordenar municipios por población descendente y provincias alfabéticamente
    for ccaa in out.values():
        ccaa["provincias"].sort()
        ccaa["municipios"].sort(key=lambda x: -x["poblacion"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="config/municipios_es.json")
    args = parser.parse_args()

    print(f"Descargando {WIKIPEDIA_URL} ...", file=sys.stderr)
    html = _fetch(WIKIPEDIA_URL)
    print(f"  {len(html)} bytes", file=sys.stderr)

    municipios = parse_wikipedia(html)
    print(f"Total municipios parseados: {len(municipios)}", file=sys.stderr)

    grouped = group_by_ccaa(municipios)
    print(f"Comunidades autónomas: {len(grouped)}", file=sys.stderr)
    for name, data in sorted(grouped.items()):
        print(f"  {name:35s}  {len(data['municipios']):4d} municipios", file=sys.stderr)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nEscrito: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
