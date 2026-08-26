"""P0-04 Observation Adapter: Microsoft Buildings.

Fetches Microsoft Global ML Building Footprints data and converts to Observation contracts.
Source: https://github.com/microsoft/GlobalMLBuildingFootprints
"""

from __future__ import annotations

import json
import os
from typing import Optional, Sequence

from src.domain.contracts import Observation
from src.observation import ObservationAdapter, SourceManifest


class MicrosoftBuildingsAdapter(ObservationAdapter):
    """Adapter for Microsoft Global ML Building Footprints.

    Footprints are available as GeoJSON per geographic region.
    """

    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache_dir = cache_dir or os.path.join(self.DATA_DIR, "buildings")

    def manifest(self) -> SourceManifest:
        return SourceManifest(
            source="Microsoft Global ML Building Footprints",
            version="2025-12-release",
            license="CDLA-Permissive-1.0 (https://cdla.dev/permissive-1-0/)",
            url="https://github.com/microsoft/GlobalMLBuildingFootprints",
            query="Beijing building footprints",
            record_count=0,
        )

    def fetch(self, **kwargs) -> Sequence[Observation]:
        """Fetch Microsoft Buildings observations.

        Supports:
        - cache_path: path to local GeoJSON file
        - bbox: (min_lat, min_lon, max_lat, max_lon) — not yet implemented
        """
        cache_path = kwargs.get("cache_path")
        source_label = kwargs.get("source_label", "Microsoft_Buildings")

        if cache_path:
            return self._from_geojson(cache_path, source_label)

        # Check cached directory
        for fname in sorted(os.listdir(self._cache_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self._cache_dir, fname)
                return self._from_geojson(fpath, source_label)

        return []

    @staticmethod
    def _from_geojson(path: str, source_label: str) -> list[Observation]:
        with open(path) as f:
            data = json.load(f)

        observations = []
        features = data.get("features", [])

        for feat in features:
            geom = feat.get("geometry")
            if not geom or geom.get("type") != "Polygon":
                continue

            coords = geom.get("coordinates", [[]])[0]
            wkt_coords = ", ".join(f"{c[0]} {c[1]}" for c in coords)
            wkt = f"POLYGON(({wkt_coords}))"

            props = feat.get("properties", {})
            fid = props.get("id", props.get("feature_id", ""))
            confidence = props.get("confidence", props.get("score", ""))

            observed_features = [f"ms_building/{fid or 'unknown'}"]
            if confidence:
                observed_features.append(f"confidence={confidence}")

            observations.append(Observation(
                source=source_label,
                source_record_id=f"ms_building/{fid}" if fid else "",
                observed_features=tuple(observed_features),
                raw_geometry=wkt,
                provenance=f"microsoft_buildings:{path}",
            ))

        return observations