"""P0-04 Observation Adapter: Overture Maps.

Fetches Overture Maps data (buildings, transportation, places, base) 
and converts to Observation contracts.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Sequence

from src.domain.contracts import Observation
from src.observation import ObservationAdapter, SourceManifest


class OvertureAdapter(ObservationAdapter):
    """Adapter for Overture Maps data.

    Overture provides global open data for buildings, transportation,
    places, and base (administrative boundaries).
    Data is expected in GeoJSON format (from local cache or S3/URL).
    """

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache_dir = cache_dir or self.DATA_DIR

    def manifest(self) -> SourceManifest:
                return SourceManifest(
            source="Overture Maps",
            dataset="overture-2026-07-release",
            theme="buildings",
            release="2026-07-release",
            source_attribution="Overture Maps Foundation",
            license="varies_by_theme",
            license_version="",
            license_url="https://overturemaps.org/about/faq/",
            url="https://overturemaps.org",
            query="buildings in Beijing",
            record_count=0,
        )

    def fetch(self, **kwargs) -> Sequence[Observation]:
        """Fetch Overture observations.

        Supports:
        - theme: "buildings", "transportation", "places", "base"
        - bbox: (min_lat, min_lon, max_lat, max_lon)
        - cache_path: path to local GeoJSON file
        """
        cache_path = kwargs.get("cache_path")
        if cache_path:
            return self._from_geojson(cache_path, kwargs.get("source_label", "Overture"))

        theme = kwargs.get("theme", "buildings")
        source_label = kwargs.get("source_label", f"Overture_{theme}")
        geojson_path = os.path.join(self._cache_dir, theme, "beijing.geojson")
        if os.path.exists(geojson_path):
            return self._from_geojson(geojson_path, source_label)

        return []

    @staticmethod
    def _from_geojson(path: str, source_label: str) -> list[Observation]:
        with open(path) as f:
            data = json.load(f)

        features = data.get("features", [])
        observations = []

        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry")

            if not geom:
                continue

            # Convert geometry to WKT
            geom_type = geom.get("type", "")
            coords = geom.get("coordinates", [])

            if geom_type == "Polygon":
                ring = coords[0] if coords else []
                wkt_coords = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                if not wkt_coords:
                    continue
                wkt = f"POLYGON(({wkt_coords}))"
            elif geom_type == "MultiPolygon":
                rings = []
                for polygon in coords:
                    ring = polygon[0] if polygon else []
                    ring_str = ", ".join(f"{c[0]} {c[1]}" for c in ring)
                    rings.append(f"({ring_str})")
                wkt = f"MULTIPOLYGON({', '.join(rings)})"
            elif geom_type == "Point":
                wkt = f"POINT({coords[0]} {coords[1]})"
            else:
                continue

            feature_id = props.get("id", props.get("overture_id", ""))
            name = props.get("name", props.get("names", {}).get("primary", ""))
            class_val = props.get("class", props.get("type", ""))

            observed_features = [f"overture/{feature_id}"]
            if name:
                observed_features.append(name)
            if class_val:
                observed_features.append(f"class={class_val}")

            observations.append(Observation(
                source=source_label,
                source_record_id=f"overture/{feature_id}",
                observed_features=tuple(observed_features),
                raw_geometry=wkt,
                provenance=f"overture:{path}",
            ))

        return observations