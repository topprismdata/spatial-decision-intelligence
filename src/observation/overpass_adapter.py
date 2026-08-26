"""P0-04 Observation Adapter: OSM via Overpass API.

Fetches OpenStreetMap data using the Overpass API and converts to Observation contracts.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Sequence

from src.domain.contracts import Observation
from src.observation import ObservationAdapter, SourceManifest


class OverpassAdapter(ObservationAdapter):
    """Adapter for OSM data via Overpass API.

    Supports querying by bounding box or from cached local files.
    """

    DEFAULT_BASE_URL = "https://overpass-api.de/api/interpreter"
    DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache_dir: Optional[str] = None,
    ):
        self._base_url = base_url
        self._cache_dir = cache_dir or os.path.join(self.DATA_DIR, "roads")

    def manifest(self) -> SourceManifest:
        return SourceManifest(
            source="OpenStreetMap",
            version="2026-08-20",
            license="ODbL (https://opendatacommons.org/licenses/odbl/)",
            url="https://www.openstreetmap.org",
            query="Overpass API: area=Beijing highway=* (all road types)",
            record_count=0,
        )

    def fetch(self, **kwargs) -> Sequence[Observation]:
        """Fetch OSM observations.

        Supports:
        - bbox: (min_lat, min_lon, max_lat, max_lon) tuple
        - query: Overpass QL string
        - cache_path: path to local cached JSON file
        - feature_type: "roads" or "buildings"
        """
        cache_path = kwargs.get("cache_path")
        if cache_path:
            return self._from_cache(cache_path, kwargs.get("source_label", "OSM"))

        feature_type = kwargs.get("feature_type", "roads")
        fixtures_dir = os.path.join(self.DATA_DIR, "beijing_fixtures")

        if feature_type in ("residential", "landuse"):
            res_fixture = os.path.join(fixtures_dir, "residential_500.json")
            if os.path.exists(res_fixture):
                return self._from_cache(res_fixture, kwargs.get("source_label", "OSM_landuse"))

        if feature_type == "roads":
            roads_fixture = os.path.join(fixtures_dir, "roads_strong_500.json")
            if os.path.exists(roads_fixture):
                return self._from_cache(roads_fixture, kwargs.get("source_label", "OSM_roads"))
            if os.path.isdir(self._cache_dir):
                return self._from_directory(self._cache_dir, source_label="OSM_roads")

        bbox = kwargs.get("bbox")
        query = kwargs.get("query")
        if not query and bbox:
            min_lng, min_lat, max_lng, max_lat = bbox
            tag_filter = 'way["landuse"="residential"]' if feature_type in ("residential", "landuse") else 'way["highway"]'
            query = f"""
                [out:json][timeout:60];
                (
                    {tag_filter}({min_lat},{min_lng},{max_lat},{max_lng});
                );
                out geom;
            """
        if query:
            return self._fetch_overpass(query, kwargs.get("source_label", "OSM"))

        return []

    def _from_cache(self, path: str, source_label: str) -> list[Observation]:
        with open(path) as f:
            data = json.load(f)
        return self._parse_overpass_response(data, source_label, os.path.basename(path))

    def _from_directory(self, dir_path: str, source_label: str) -> list[Observation]:
        observations = []
        for fname in sorted(os.listdir(dir_path)):
            if fname.endswith(".json"):
                fpath = os.path.join(dir_path, fname)
                with open(fpath) as f:
                    data = json.load(f)
                observations.extend(
                    self._parse_overpass_response(data, source_label, fname)
                )
        return observations

    def _fetch_overpass(
        self, query: str, source_label: str
    ) -> list[Observation]:
        """Execute a live Overpass query and return observations."""
        import urllib.request
        import urllib.parse

        url = f"{self._base_url}?data={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SpatialDecisionIntelligence/1.0"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return self._parse_overpass_response(data, source_label, query[:60])

    @staticmethod
    def _parse_overpass_response(
        data: dict, source_label: str, provenance_hint: str
    ) -> list[Observation]:
        observations = []
        for elem in data.get("elements", []):
            if elem.get("type") != "way":
                continue

            # Build WKT linestring from geometry
            geom = elem.get("geometry") or elem.get("bounds")
            if not geom:
                continue

            if isinstance(geom, dict):
                # bounds object
                coords = [
                    (geom["minlon"], geom["minlat"]),
                    (geom["maxlon"], geom["maxlat"]),
                ]
            else:
                coords = [(p["lon"], p["lat"]) for p in geom]

            if len(coords) < 2:
                continue

            if len(coords) >= 4 and coords[0] == coords[-1]:
                wkt_coords = ", ".join(f"{lng} {lat}" for lng, lat in coords)
                wkt = f"POLYGON(({wkt_coords}))"
            else:
                wkt_coords = ", ".join(f"{lng} {lat}" for lng, lat in coords)
                wkt = f"LINESTRING({wkt_coords})"

            tags = elem.get("tags", {})
            highway = tags.get("highway", "")
            name = tags.get("name", "")

            observed_features = [f"osm/way/{elem['id']}"]
            if name:
                observed_features.append(name)
            observed_features.append(f"highway={highway}")

            observations.append(Observation(
                source=source_label,
                source_record_id=f"osm/way/{elem['id']}",
                observed_features=tuple(observed_features),
                raw_geometry=wkt,
                provenance=f"overpass:{provenance_hint}",
            ))

        return observations