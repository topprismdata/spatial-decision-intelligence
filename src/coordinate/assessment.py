"""
Module M1: Coordinate Intelligence - Diagnoses coordinate systems and normalizes to WGS84.
"""

from typing import Tuple, Optional, Dict, Any
from shapely import wkt
from shapely.geometry import Point, Polygon
from src.domain.models import SourceRecord, CoordinateStatus, CoordinateAssessment
from src.coordinate.transforms import gcj02_to_wgs84, wgs84_to_gcj02, transform_geometry_wkt


class CoordinateIntelligence:
    """Diagnoses and standardizes coordinates to WGS84."""

    @staticmethod
    def assess_and_normalize(record: SourceRecord) -> Tuple[CoordinateAssessment, float, float, Optional[str]]:
        """
        Assess coordinate status and return:
        (assessment, norm_lng_wgs84, norm_lat_wgs84, norm_polygon_wkt_wgs84)
        """
        raw_lng = record.point_raw_lng
        raw_lat = record.point_raw_lat
        raw_wkt = record.geometry_raw_wkt

        notes = []
        is_point_missing_or_zero = (raw_lng is None or raw_lat is None or (raw_lng == 0 and raw_lat == 0))

        # 1. Parse raw polygon and compute GCJ02 vs WGS84 polygon centroids
        poly_centroid_gcj02 = None
        norm_wkt_wgs84 = None
        poly_centroid_wgs84 = None

        if raw_wkt:
            try:
                geom = wkt.loads(raw_wkt)
                poly_centroid_gcj02 = geom.centroid
                # In current dataset, polygon coordinates are in GCJ-02 -> transform to WGS84
                norm_wkt_wgs84 = transform_geometry_wkt(raw_wkt, gcj02_to_wgs84)
                if norm_wkt_wgs84:
                    norm_geom = wkt.loads(norm_wkt_wgs84)
                    poly_centroid_wgs84 = norm_geom.centroid
            except Exception as e:
                notes.append(f"Polygon parse error: {str(e)}")

        # 2. Diagnose Point
        if is_point_missing_or_zero:
            # Case A: Point is missing/zero, reconstruct point from WGS84 polygon centroid
            if poly_centroid_wgs84:
                norm_lng = poly_centroid_wgs84.x
                norm_lat = poly_centroid_wgs84.y
                status = CoordinateStatus.SYSTEMATIC_OFFSET
                notes.append("Raw point was (0,0) or null; reconstructed from transformed polygon centroid.")
                assessment = CoordinateAssessment(
                    source_record_id=record.source_record_id,
                    coordinate_status=status,
                    point_crs="RECONSTRUCTED_WGS84",
                    polygon_crs="GCJ02_TRANSFORMED_TO_WGS84",
                    selected_transform="GCJ02_TO_WGS84",
                    delta_lng=0.0,
                    delta_lat=0.0,
                    confidence=0.95,
                    notes=notes
                )
                return assessment, norm_lng, norm_lat, norm_wkt_wgs84
            else:
                status = CoordinateStatus.CRS_UNKNOWN
                notes.append("Both point and polygon are missing/invalid.")
                assessment = CoordinateAssessment(
                    source_record_id=record.source_record_id,
                    coordinate_status=status,
                    point_crs="UNKNOWN",
                    polygon_crs="UNKNOWN",
                    selected_transform=None,
                    delta_lng=0.0,
                    delta_lat=0.0,
                    confidence=0.1,
                    notes=notes
                )
                return assessment, 0.0, 0.0, None

        # Case B: Point exists (Raw point is in WGS84)
        norm_lng = raw_lng
        norm_lat = raw_lat

        if poly_centroid_gcj02 and poly_centroid_wgs84:
            # Check offset between raw point (WGS84) and raw polygon (GCJ02)
            d_lng_raw = poly_centroid_gcj02.x - raw_lng
            d_lat_raw = poly_centroid_gcj02.y - raw_lat

            # Check offset between raw point (WGS84) and transformed polygon (WGS84)
            d_lng_norm = poly_centroid_wgs84.x - norm_lng
            d_lat_norm = poly_centroid_wgs84.y - norm_lat

            # If raw offset is around ~0.006 lng and ~0.001 lat, it confirms Point=WGS84, Polygon=GCJ02
            if abs(d_lng_raw - 0.006) < 0.003 and abs(d_lat_raw - 0.001) < 0.003:
                status = CoordinateStatus.POINT_POLYGON_CRS_CONFLICT
                notes.append("Systematic WGS84 Point vs GCJ02 Polygon offset successfully aligned.")
                confidence = 0.98
            elif abs(d_lng_norm) > 0.05 or abs(d_lat_norm) > 0.05:
                status = CoordinateStatus.MIXED_CRS
                notes.append(f"Extreme Point-Polygon distance after alignment ({d_lng_norm:.4f}, {d_lat_norm:.4f}).")
                confidence = 0.50
            else:
                status = CoordinateStatus.CONFIRMED_WGS84
                confidence = 0.90

            assessment = CoordinateAssessment(
                source_record_id=record.source_record_id,
                coordinate_status=status,
                point_crs="WGS84",
                polygon_crs="GCJ02_TRANSFORMED_TO_WGS84",
                selected_transform="GCJ02_TO_WGS84",
                delta_lng=float(d_lng_norm),
                delta_lat=float(d_lat_norm),
                confidence=confidence,
                notes=notes
            )
        else:
            status = CoordinateStatus.CONFIRMED_WGS84
            assessment = CoordinateAssessment(
                source_record_id=record.source_record_id,
                coordinate_status=status,
                point_crs="WGS84",
                polygon_crs="NONE",
                selected_transform=None,
                delta_lng=0.0,
                delta_lat=0.0,
                confidence=0.85,
                notes=notes
            )

        return assessment, norm_lng, norm_lat, norm_wkt_wgs84
