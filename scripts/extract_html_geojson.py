"""Extract embedded Leaflet L.polygon data from generated map HTML into GeoJSON.

Usage: python3 scripts/extract_html_geojson.py <map.html> <out.geojson>

Handles the generated-map pattern: L.polygon([[lat,lng],...], {...}) with
optional chained .bindTooltip("...") / .bindPopup("..."). Re-emits GeoJSON
Polygon features in [lng, lat] order with a `label` property from the
tooltip/popup when present.

Format guarantees (post-processing):
  - every linear ring is closed (RFC 7946): first point == last point
  - degenerate rings (< 4 closed points) dropped
  - self-intersecting polygons repaired via shapely make_valid
  - surviving geometry re-validated; unrecoverable candidates dropped
"""

import json
import re
import sys


def extract_balanced(text: str, start: int, open_ch: str = "[",
                     close_ch: str = "]") -> tuple[str, int]:
    """Return the balanced bracket group starting at `start` (text[start]
    must be open_ch) and the index just after it."""
    depth = 0
    i = start
    in_str = False
    quote = ""
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                in_str = False
        else:
            if ch in "'\"":
                in_str = True
                quote = ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1], i + 1
        i += 1
    raise ValueError("unbalanced group")


def rings_to_geometry(rings_json: str) -> dict:
    """Leaflet L.polygon(rings): one exterior + optional holes, [lat,lng]."""
    rings = json.loads(rings_json)
    if rings and isinstance(rings[0][0], (int, float)):
        rings = [rings]  # single flat ring without nesting
    coords = [
        [[float(pt[1]), float(pt[0])] for pt in ring]  # -> [lng,lat]
        for ring in rings
        if len(ring) >= 3
    ]
    return {"type": "Polygon", "coordinates": coords}


def _close_rings(geometry: dict) -> dict:
    """RFC 7946: linear rings must be closed. Drops degenerate rings."""
    coords = []
    for ring in geometry["coordinates"]:
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        if len(ring) >= 4:
            coords.append(ring)
    return {"type": geometry["type"], "coordinates": coords}


def _repair(geometry: dict):
    """Close rings, then shapely make_valid for self-intersections.
    Returns (geometry, repaired_flag) or None when unrecoverable."""
    from shapely.geometry import shape as sh_shape, mapping as sh_mapping
    from shapely.validation import make_valid

    closed = _close_rings(geometry)
    if not closed["coordinates"]:
        return None
    try:
        sh = sh_shape(closed)
        was_valid = sh.is_valid
        if not was_valid:
            sh = make_valid(sh)
        if sh.is_empty:
            return None
        m = sh_mapping(sh)
        if m["type"] == "GeometryCollection":
            polys = [g for g in m["geometries"]
                     if g["type"] in ("Polygon", "MultiPolygon")]
            if not polys:
                return None
            if len(polys) == 1 and polys[0]["type"] == "Polygon":
                m = polys[0]
            else:
                multi = [p["coordinates"] for p in polys
                         if p["type"] == "Polygon"]
                multi += [p["coordinates"] for p in polys
                          if p["type"] == "MultiPolygon"]
                m = {"type": "MultiPolygon", "coordinates": multi}
        return m, not was_valid
    except Exception:
        return None


LABEL_RE = re.compile(
    r"\.bind(?:Tooltip|Popup)\(\s*(?:function\(.*?\)\s*{\s*return\s*)?[`'\"](.+?)[`'\"]",
    re.S,
)


def extract(html_path: str, out_path: str) -> dict:
    html = open(html_path, encoding="utf-8", errors="replace").read()
    features = []
    repaired = dropped = 0
    idx = 0
    n_poly = html.count("L.polygon(")
    while True:
        pos = html.find("L.polygon(", idx)
        if pos < 0:
            break
        idx = pos + 10
        try:
            bracket_at = html.index("[", idx)
        except ValueError:
            break
        if bracket_at - idx > 200:  # not a literal array -> skip
            continue
        try:
            rings_json, after = extract_balanced(html, bracket_at)
        except (ValueError, json.JSONDecodeError):
            continue
        window = html[after:after + 800]
        m = LABEL_RE.search(window)
        label = ""
        if m:
            label = re.sub(r"<[^>]+>", " ", m.group(1))
            label = re.sub(r"\s+", " ", label).strip()[:200]
        try:
            geometry = rings_to_geometry(rings_json)
        except (json.JSONDecodeError, ValueError, TypeError, IndexError):
            continue
        result = _repair(geometry)
        if result is None:
            dropped += 1
            continue
        fixed, was_repaired = result
        if was_repaired:
            repaired += 1
        props: dict = {}
        if label:
            props["label"] = label
        features.append({"type": "Feature",
                         "properties": props,
                         "geometry": fixed})
    fc = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(fc, fh, ensure_ascii=False)
    return {"polygons_in_html": n_poly, "features_written": len(features),
            "repaired": repaired, "dropped": dropped}


if __name__ == "__main__":
    stats = extract(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[1]} -> {sys.argv[2]}: {stats}")
