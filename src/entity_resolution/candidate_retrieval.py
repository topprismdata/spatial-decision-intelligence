"""
Module M3: Candidate Retrieval Engine - Uses STRtree spatial index and lexical blocking.
"""

from typing import List, Dict, Tuple, Set, Any
from shapely import wkt
from shapely.strtree import STRtree
from shapely.geometry import Polygon, MultiPolygon, Point
from src.domain.models import SourceRecord
from src.coordinate.metric_service import MetricGeometryService
_metric_svc = MetricGeometryService()


class CandidateRetrievalEngine:
    """Retrieves high-recall candidate pairs for Entity Resolution."""

    @staticmethod
    def retrieve_candidate_pairs(
        records: List[SourceRecord],
        norm_geoms: Dict[str, Any],  # source_id -> shapely geometry
        norm_coords: Dict[str, Tuple[float, float]],  # source_id -> (lng, lat)
        buffer_meters: float = 300.0  # default ~300m search radius
    ) -> List[Tuple[SourceRecord, SourceRecord]]:
        """
        Generates candidate pairs using Spatial STRtree + Lexical Blocking per city.
        """
        # Group records by city
        city_records: Dict[str, List[SourceRecord]] = {}
        for r in records:
            city_records.setdefault(r.city_raw, []).append(r)

        candidate_pairs_set: Set[Tuple[str, str]] = set()
        record_map = {r.source_record_id: r for r in records}

        for city, recs in city_records.items():
            valid_recs = []
            geometries = []

            for r in recs:
                geom = norm_geoms.get(r.source_record_id)
                if geom and not geom.is_empty:
                    valid_recs.append(r)
                    geometries.append(geom.buffer(_metric_svc.snap_tolerance_deg(buffer_meters, r.point_raw_lat or 39.9)))
                else:
                    # Point fallback
                    coords = norm_coords.get(r.source_record_id)
                    if coords and coords[0] != 0:
                        pt_geom = Point(coords[0], coords[1]).buffer(_metric_svc.snap_tolerance_deg(buffer_meters, coords[1]))
                        valid_recs.append(r)
                        geometries.append(pt_geom)

            if len(geometries) > 1:
                tree = STRtree(geometries)
                for idx, target_geom in enumerate(geometries):
                    r_a = valid_recs[idx]
                    intersecting_indices = tree.query(target_geom)
                    for j in intersecting_indices:
                        if idx < j:
                            r_b = valid_recs[j]
                            candidate_pairs_set.add((r_a.source_record_id, r_b.source_record_id))

            # Lexical blocking: Exact and partial name prefix matches within city
            name_prefix_map: Dict[str, List[SourceRecord]] = {}
            for r in recs:
                norm_name = r.name_raw.replace(" ", "").replace("（", "(").replace("）", ")")
                # Remove common brackets
                if "(" in norm_name:
                    norm_name = norm_name.split(")")[-1]
                if len(norm_name) >= 3:
                    prefix = norm_name[:3]
                    name_prefix_map.setdefault(prefix, []).append(r)

            for prefix, group in name_prefix_map.items():
                if 1 < len(group) <= 50:  # Avoid ultra common prefix explosions
                    for i in range(len(group)):
                        for j in range(i + 1, len(group)):
                            id_a, id_b = group[i].source_record_id, group[j].source_record_id
                            pair_key = (min(id_a, id_b), max(id_a, id_b))
                            candidate_pairs_set.add(pair_key)

        result_pairs = []
        for id_a, id_b in candidate_pairs_set:
            result_pairs.append((record_map[id_a], record_map[id_b]))

        return result_pairs
