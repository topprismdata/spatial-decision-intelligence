"""P1-02 Boundary Segment: Polygon → BoundarySegment[] decomposition.

Each boundary segment has its own confidence score, allowing
localized validation of boundary quality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.coordinate.metric_crs import meters_per_degree_lat, meters_per_degree_lng


@dataclass(frozen=True)
class BoundarySegment:
    """A single segment of a polygon boundary with local confidence."""

    index: int  # Segment index (0-based)
    geometry_wkt: str  # LINESTRING for this segment
    length_m: float = 0.0  # Length in meters
    confidence: float = 0.0  # 0.0-1.0
    segment_type: str = "UNKNOWN"  # ROAD_ALIGNED, BUILDING_ALIGNED, OPEN_SPACE, INFERRED, etc.
    evidence: str = ""


@dataclass
class BoundaryDecomposition:
    """Complete decomposition of a polygon into segments."""

    polygon_id: str
    segments: list[BoundarySegment] = field(default_factory=list)
    overall_confidence: float = 0.0
    n_segments: int = 0
    total_length_m: float = 0.0

    @property
    def low_confidence_segments(self) -> list[BoundarySegment]:
        return [s for s in self.segments if s.confidence < 0.5]

    @property
    def high_confidence_segments(self) -> list[BoundarySegment]:
        return [s for s in self.segments if s.confidence >= 0.8]


class BoundarySegmenter:
    """Decomposes a polygon boundary into segments with local confidence.

    Segmentation strategies:
    1. Road-aligned segments: portions of boundary that follow roads
    2. Building-aligned segments: portions where buildings align with boundary
    3. Open-space segments: portions with no clear spatial evidence
    4. Corner-based: segments between sharp corners
    """

    MIN_SEGMENT_LENGTH_M = 10.0  # Minimum segment length
    MAX_SEGMENTS = 64  # Maximum number of segments per polygon

    def __init__(self):
        pass

    def decompose(
        self,
        polygon_id: str,
        polygon_wkt: str,
        road_network_wkt: Optional[list[str]] = None,
        building_footprints_wkt: Optional[list[str]] = None,
        ref_lat: float = 39.9,
        max_segments: int = 32,
    ) -> BoundaryDecomposition:
        """Decompose a polygon boundary into segments.

        Steps:
        1. Extract boundary coordinates
        2. Segment by natural breakpoints (corners, road intersections)
        3. Assign local confidence to each segment
        4. Compute overall confidence
        """
        from shapely import wkt as _wkt
        from src.coordinate.metric_service import MetricGeometryService
        _ms = MetricGeometryService()

        polygon = _wkt.loads(polygon_wkt)
        exterior = polygon.exterior

        if exterior is None:
            return BoundaryDecomposition(polygon_id=polygon_id)

        coords = list(exterior.coords)
        if len(coords) < 4:
            return BoundaryDecomposition(polygon_id=polygon_id)

        # Find breakpoints: sharp corners
        breakpoints = self._find_corner_breakpoints(coords)
        # Also add road intersection points
        if road_network_wkt:
            road_breakpoints = self._find_road_breakpoints(
                coords, road_network_wkt
            )
            breakpoints.update(road_breakpoints)

        # Build segments from breakpoints
        segments = self._build_segments(
            coords, sorted(breakpoints), polygon_id, ref_lat
        )

        # Assign confidence to each segment
        segments = self._assign_confidence(
            segments, polygon, road_network_wkt, building_footprints_wkt,
            ref_lat,
        )

        # Trim to max segments
        if len(segments) > max_segments:
            segments = segments[:max_segments]

        # Compute overall confidence (weighted by segment length)
        total_length = sum(s.length_m for s in segments)
        if total_length > 0:
            overall = sum(
                s.confidence * s.length_m for s in segments
            ) / total_length
        else:
            overall = 0.0

        return BoundaryDecomposition(
            polygon_id=polygon_id,
            segments=segments,
            overall_confidence=overall,
            n_segments=len(segments),
            total_length_m=total_length,
        )

    @staticmethod
    def _find_corner_breakpoints(
        coords: list[tuple[float, float]],
    ) -> set[int]:
        """Find sharp corners as natural breakpoints.

        A corner is "sharp" if the turning angle exceeds a threshold.
        """
        breakpoints = {0}  # Always include the first point
        n = len(coords) - 1  # Exclude closing point

        for i in range(1, n):
            prev = coords[i - 1]
            curr = coords[i]
            next_ = coords[(i + 1) % n]

            # Vectors
            v1 = (curr[0] - prev[0], curr[1] - prev[1])
            v2 = (next_[0] - curr[0], next_[1] - curr[1])

            # Dot product for angle
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            mag1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
            mag2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5

            if mag1 > 0 and mag2 > 0:
                cos_angle = dot / (mag1 * mag2)
                # Sharp corner if angle < 135° (cos > -0.707)
                if cos_angle > -0.707:
                    breakpoints.add(i)

        return breakpoints

    @staticmethod
    def _find_road_breakpoints(
        coords: list[tuple[float, float]],
        road_network: list[str],
    ) -> set[int]:
        """Find points where roads intersect the boundary."""
        from shapely import wkt as _wkt
        from shapely.geometry import Point

        breakpoints = set()
        try:
            for rwkt in road_network:
                road = _wkt.loads(rwkt)
                for i, (x, y) in enumerate(coords):
                    pt = Point(x, y)
                    if road.distance(pt) < 0.0001:  # ~10m at 40°N
                        breakpoints.add(i)
        except Exception:
            pass
        return breakpoints

    def _build_segments(
        self,
        coords: list[tuple[float, float]],
        breakpoints: list[int],
        polygon_id: str,
        ref_lat: float,
    ) -> list[BoundarySegment]:
        """Build segments between consecutive breakpoints."""
        # Segment length uses projected CRS via MetricGeometryService

        m_per_lat = meters_per_degree_lat(ref_lat)
        m_per_lng = meters_per_degree_lng(ref_lat)

        segments = []
        n = len(coords) - 1  # Exclude closing point

        for idx in range(len(breakpoints)):
            start = breakpoints[idx]
            end = breakpoints[(idx + 1) % len(breakpoints)]

            if end <= start:
                end += n

            # Get coordinates for this segment
            seg_coords = []
            for j in range(start, min(end + 1, n + 1)):
                seg_coords.append(coords[j % n])

            if len(seg_coords) < 2:
                continue

            # Build WKT
            coord_str = ", ".join(f"{x} {y}" for x, y in seg_coords)
            wkt = f"LINESTRING({coord_str})"

            # Compute length in meters
            length_m = 0.0
            for k in range(1, len(seg_coords)):
                dx = (seg_coords[k][0] - seg_coords[k - 1][0]) * m_per_lng
                dy = (seg_coords[k][1] - seg_coords[k - 1][1]) * m_per_lat
                length_m += (dx * dx + dy * dy) ** 0.5

            if length_m < self.MIN_SEGMENT_LENGTH_M:
                continue

            segments.append(BoundarySegment(
                index=len(segments),
                geometry_wkt=wkt,
                length_m=round(length_m, 2),
                confidence=0.5,  # Default: neutral
                segment_type="INFERRED",
                evidence="",
            ))

        return segments

    def _assign_confidence(
        self,
        segments: list[BoundarySegment],
        polygon,
        road_network: Optional[list[str]],
        building_footprints: Optional[list[str]],
        ref_lat: float,
    ) -> list[BoundarySegment]:
        """Assign confidence to each segment based on spatial evidence."""
        from shapely import wkt as _wkt

        result = []
        for seg in segments:
            seg_geom = _wkt.loads(seg.geometry_wkt)
            conf = 0.5  # Default
            seg_type = "INFERRED"
            evidence_parts = []

            # Check road alignment
            if road_network:
                max_road_conf = 0.0
                for rwkt in road_network:
                    road = _wkt.loads(rwkt)
                    if seg_geom.intersects(road):
                        intersection = seg_geom.intersection(road)
                        # How much of the segment overlaps with road
                        ratio = intersection.length / max(seg_geom.length, 0.001)
                        if ratio > 0.3:
                            conf = max(conf, 0.7 + ratio * 0.2)
                            seg_type = "ROAD_ALIGNED"
                            max_road_conf = max(max_road_conf, conf)
                            evidence_parts.append(f"road_aligned({ratio:.0%})")
                conf = max(conf, max_road_conf)

            # Check building alignment
            if building_footprints:
                for bwkt in building_footprints:
                    try:
                        building = _wkt.loads(bwkt)
                        if seg_geom.distance(building) < 0.0001:
                            conf = max(conf, 0.65)
                            seg_type = "BUILDING_ALIGNED"
                            evidence_parts.append("building_aligned")
                    except Exception:
                        pass

            result.append(BoundarySegment(
                index=seg.index,
                geometry_wkt=seg.geometry_wkt,
                length_m=seg.length_m,
                confidence=min(1.0, conf),
                segment_type=seg_type,
                evidence="; ".join(evidence_parts) if evidence_parts else "no_evidence",
            ))

        return result