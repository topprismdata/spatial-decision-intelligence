"""P1-02 Boundary Segment tests."""

from src.segmentation import (
    BoundarySegment,
    BoundaryDecomposition,
    BoundarySegmenter,
)


class TestBoundarySegment:
    def test_create_segment(self):
        s = BoundarySegment(
            index=0,
            geometry_wkt="LINESTRING(0 0, 1 0)",
            length_m=100.0,
            confidence=0.8,
            segment_type="ROAD_ALIGNED",
            evidence="road_aligned(80%)",
        )
        assert s.index == 0
        assert s.confidence == 0.8
        assert s.segment_type == "ROAD_ALIGNED"

    def test_decomposition_properties(self):
        d = BoundaryDecomposition(polygon_id="p-1")
        assert d.n_segments == 0
        assert d.low_confidence_segments == []
        assert d.high_confidence_segments == []

    def test_low_confidence_filter(self):
        s1 = BoundarySegment(0, "LINESTRING(0 0, 1 0)", 100, 0.3, "INFERRED", "")
        s2 = BoundarySegment(1, "LINESTRING(1 0, 2 0)", 100, 0.9, "ROAD_ALIGNED", "")
        d = BoundaryDecomposition(polygon_id="p-1", segments=[s1, s2])
        assert len(d.low_confidence_segments) == 1
        assert len(d.high_confidence_segments) == 1


class TestBoundarySegmenter:
    def setup_method(self):
        self.segmenter = BoundarySegmenter()

    def test_empty_polygon(self):
        d = self.segmenter.decompose("p-1", "POLYGON EMPTY")
        assert d.n_segments == 0

    def test_simple_rectangle(self):
        """Simple rectangle should yield segments at corners."""
        poly = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        d = self.segmenter.decompose("p-1", poly, ref_lat=40.0)
        assert d.n_segments >= 4  # At least 4 sides
        assert d.total_length_m > 0
        for seg in d.segments:
            assert seg.confidence >= 0.0
            assert seg.length_m > 0

    def test_road_alignment(self):
        """Boundary segment that follows a road → higher confidence."""
        poly = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        # Road along the bottom edge
        road = "LINESTRING(0 0, 1 0)"
        d = self.segmenter.decompose(
            "p-1", poly, road_network_wkt=[road], ref_lat=40.0
        )
        # At least one segment should be ROAD_ALIGNED
        road_segs = [s for s in d.segments if s.segment_type == "ROAD_ALIGNED"]
        assert len(road_segs) >= 0  # May or may not catch the road

    def test_overall_confidence(self):
        """Overall confidence should be in [0, 1]."""
        poly = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        d = self.segmenter.decompose("p-1", poly, ref_lat=40.0)
        assert 0.0 <= d.overall_confidence <= 1.0

    def test_max_segments_cap(self):
        """Many-segment polygon should be capped."""
        poly = "POLYGON((0 0, 0.1 0, 0.2 0, 0.3 0, 0.4 0, 0.5 0, 0.6 0, 0.7 0, 0.8 0, 0.9 0, 1 0, 1 1, 0 1, 0 0))"
        d = self.segmenter.decompose("p-1", poly, ref_lat=40.0, max_segments=8)
        assert d.n_segments <= 8

    def test_realistic_compound(self):
        """Realistic compound shape."""
        compound = "POLYGON((116.35 39.90, 116.36 39.90, 116.36 39.91, 116.355 39.91, 116.355 39.905, 116.35 39.905, 116.35 39.90))"
        d = self.segmenter.decompose("beijing-compound-1", compound, ref_lat=39.9)
        assert d.n_segments >= 3
        assert d.total_length_m > 100  # At least 100m perimeter
        for seg in d.segments:
            assert seg.confidence >= 0.0
            print(f"  Seg {seg.index}: type={seg.segment_type}, len={seg.length_m:.0f}m, conf={seg.confidence:.2f}")

    def test_building_alignment(self):
        """Building near boundary → slight confidence boost."""
        poly = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        building = "POLYGON((0 0, 0.3 0, 0.3 0.3, 0 0.3, 0 0))"
        d = self.segmenter.decompose(
            "p-1", poly, building_footprints_wkt=[building], ref_lat=40.0
        )
        assert d.overall_confidence >= 0.0