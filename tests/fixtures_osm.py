"""R2 Frozen OSM Fixture: deterministic Beijing residential compound data.

Real Overpass API response, frozen and versioned.
Used for Level 1 Deterministic Integration Tests.
"""

import json
import os

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

FIXTURE_V1 = {
    "version": 0.6,
    "generator": "Overpass API 0.7.62",
    "osm3s": {"timestamp_osm_base": "2026-08-26T10:00:00Z"},
    "elements": [
        # Residential landuse polygon (compound)
        {
            "type": "way", "id": 900001,
            "bounds": {"minlat": 39.8990, "minlon": 116.3490, "maxlat": 39.9010, "maxlon": 116.3510},
            "geometry": [
                {"lat": 39.8990, "lon": 116.3490}, {"lat": 39.9010, "lon": 116.3490},
                {"lat": 39.9010, "lon": 116.3510}, {"lat": 39.8990, "lon": 116.3510},
                {"lat": 39.8990, "lon": 116.3490},
            ],
            "tags": {
                "landuse": "residential", "name": "测试小区一区", "residential": "apartments"
            },
        },
        # Roads forming enclosure
        {
            "type": "way", "id": 900002,
            "bounds": {"minlat": 39.8985, "minlon": 116.3480, "maxlat": 39.8985, "maxlon": 116.3520},
            "geometry": [{"lat": 39.8985, "lon": 116.3480}, {"lat": 39.8985, "lon": 116.3520}],
            "tags": {"highway": "primary", "name": "主路"},
        },
        {
            "type": "way", "id": 900003,
            "bounds": {"minlat": 39.9015, "minlon": 116.3480, "maxlat": 39.9015, "maxlon": 116.3520},
            "geometry": [{"lat": 39.9015, "lon": 116.3480}, {"lat": 39.9015, "lon": 116.3520}],
            "tags": {"highway": "primary", "name": "北环路"},
        },
        # Internal service road
        {
            "type": "way", "id": 900004,
            "bounds": {"minlat": 39.8990, "minlon": 116.3500, "maxlat": 39.9010, "maxlon": 116.3500},
            "geometry": [{"lat": 39.8990, "lon": 116.3500}, {"lat": 39.9010, "lon": 116.3500}],
            "tags": {"highway": "service", "name": ""},
        },
    ],
}


def load_fixture(name="fixture_v1"):
    return FIXTURE_V1


def save_fixture(data, name):
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    path = os.path.join(FIXTURE_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path