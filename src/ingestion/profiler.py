"""
Module M0: Data Profiler - Computes dataset health and risks as specified in v2.0 Section 13.
"""

from typing import List, Dict, Any
import numpy as np
from shapely import wkt
from shapely.geometry import Polygon, MultiPolygon
from src.domain.models import SourceRecord


class DatasetProfiler:
    """Computes comprehensive health report for a batch of SourceRecords."""

    @staticmethod
    def profile(records: List[SourceRecord]) -> Dict[str, Any]:
        total_count = len(records)
        if total_count == 0:
            return {"error": "Empty dataset"}

        # 1. Field Completeness
        name_nulls = sum(1 for r in records if not r.name_raw)
        address_nulls = sum(1 for r in records if not r.address_raw)
        point_nulls = sum(1 for r in records if r.point_raw_lng is None or r.point_raw_lat is None)
        zero_points = sum(1 for r in records if r.point_raw_lng == 0 or r.point_raw_lat == 0)
        geom_nulls = sum(1 for r in records if not r.geometry_raw_wkt)
        admin_nulls = sum(1 for r in records if not r.city_raw or not r.district_raw)

        # 2. City & Province distribution
        city_counts: Dict[str, int] = {}
        province_counts: Dict[str, int] = {}
        for r in records:
            c = r.city_raw or "未知"
            p = r.province_raw or "未知"
            city_counts[c] = city_counts.get(c, 0) + 1
            province_counts[p] = province_counts.get(p, 0) + 1

        # 3. Duplicate analysis
        name_map: Dict[str, List[str]] = {}
        point_map: Dict[str, List[str]] = {}
        wkt_map: Dict[str, List[str]] = {}

        for r in records:
            # Name in same city
            city_name_key = f"{r.city_raw}_{r.name_raw}"
            name_map.setdefault(city_name_key, []).append(r.source_record_id)

            if r.point_raw_lng is not None and r.point_raw_lat is not None:
                pt_key = f"{r.point_raw_lng:.6f}_{r.point_raw_lat:.6f}"
                point_map.setdefault(pt_key, []).append(r.source_record_id)

            if r.geometry_raw_wkt:
                wkt_map.setdefault(r.geometry_raw_wkt, []).append(r.source_record_id)

        same_city_name_dups = {k: v for k, v in name_map.items() if len(v) > 1}
        same_point_dups = {k: v for k, v in point_map.items() if len(v) > 1}
        same_wkt_dups = {k: v for k, v in wkt_map.items() if len(v) > 1}

        # 4. Point-Polygon Offset & Geometry Validity stats
        offsets_lng = []
        offsets_lat = []
        invalid_geom_count = 0
        zero_area_count = 0
        areas = []
        vertex_counts = []

        for r in records:
            if r.geometry_raw_wkt:
                try:
                    geom = wkt.loads(r.geometry_raw_wkt)
                    if not geom.is_valid:
                        invalid_geom_count += 1
                    area = geom.area
                    areas.append(area)
                    if area == 0:
                        zero_area_count += 1

                    if isinstance(geom, Polygon):
                        v_cnt = len(geom.exterior.coords)
                        vertex_counts.append(v_cnt)
                    elif isinstance(geom, MultiPolygon):
                        v_cnt = sum(len(p.exterior.coords) for p in geom.geoms)
                        vertex_counts.append(v_cnt)

                    centroid = geom.centroid
                    if r.point_raw_lng is not None and r.point_raw_lat is not None:
                        if r.point_raw_lng > 70 and r.point_raw_lat > 10:  # valid point range
                            d_lng = centroid.x - r.point_raw_lng
                            d_lat = centroid.y - r.point_raw_lat
                            offsets_lng.append(d_lng)
                            offsets_lat.append(d_lat)
                except Exception:
                    invalid_geom_count += 1

        offset_stats = {}
        if offsets_lng:
            offset_stats = {
                "sample_size": len(offsets_lng),
                "d_lng_mean": float(np.mean(offsets_lng)),
                "d_lng_median": float(np.median(offsets_lng)),
                "d_lng_std": float(np.std(offsets_lng)),
                "d_lat_mean": float(np.mean(offsets_lat)),
                "d_lat_median": float(np.median(offsets_lat)),
                "d_lat_std": float(np.std(offsets_lat)),
            }

        report = {
            "total_records": total_count,
            "field_completeness": {
                "name_null_rate": name_nulls / total_count,
                "address_null_rate": address_nulls / total_count,
                "point_null_rate": point_nulls / total_count,
                "zero_points_count": zero_points,
                "geometry_null_rate": geom_nulls / total_count,
                "admin_null_rate": admin_nulls / total_count,
            },
            "geographic_distribution": {
                "provinces": province_counts,
                "cities": city_counts
            },
            "duplicate_risk": {
                "same_city_name_duplicate_groups": len(same_city_name_dups),
                "same_city_name_duplicate_records": sum(len(v) for v in same_city_name_dups.values()),
                "same_point_duplicate_groups": len(same_point_dups),
                "same_point_duplicate_records": sum(len(v) for v in same_point_dups.values()),
                "identical_wkt_duplicate_groups": len(same_wkt_dups),
            },
            "geometry_distribution": {
                "invalid_geometry_count": invalid_geom_count,
                "zero_area_count": zero_area_count,
                "vertex_count_stats": {
                    "mean": float(np.mean(vertex_counts)) if vertex_counts else 0,
                    "median": float(np.median(vertex_counts)) if vertex_counts else 0,
                    "max": int(np.max(vertex_counts)) if vertex_counts else 0,
                    "min": int(np.min(vertex_counts)) if vertex_counts else 0,
                },
                "area_stats_deg2": {
                    "mean": float(np.mean(areas)) if areas else 0,
                    "median": float(np.median(areas)) if areas else 0,
                    "max": float(np.max(areas)) if areas else 0,
                    "min": float(np.min(areas)) if areas else 0,
                }
            },
            "coordinate_risk": {
                "point_polygon_offset": offset_stats,
                "systematic_offset_detected": True if offset_stats and abs(offset_stats["d_lng_median"] - 0.006) < 0.002 else False,
                "inferred_offset_type": "WGS84_POINT_VS_GCJ02_POLYGON" if offset_stats and abs(offset_stats["d_lng_median"] - 0.006) < 0.002 else "UNKNOWN"
            }
        }
        return report
