"""Tests for R14-P1 concave hull (Duckham-style edge elimination)."""

import math

from shapely.geometry import Polygon

from src.geometry.concave_hull import concave_hull, hull_for_cluster


def _l_shape_points():
    """L-shaped cluster where the convex hull badly over-covers."""
    pts = []
    # Vertical bar
    for y in range(0, 101, 10):
        pts.append((0.0, float(y)))
        pts.append((10.0, float(y)))
    # Horizontal foot
    for x in range(20, 101, 10):
        pts.append((float(x), 0.0))
        pts.append((float(x), 10.0))
    return [(x / 100.0, y / 100.0) for x, y in pts]


class TestConcaveHull:
    def test_returns_valid_polygon(self):
        hull = hull_for_cluster(_l_shape_points())
        assert isinstance(hull, Polygon)
        assert hull.is_valid

    def test_tighter_or_equal_than_convex(self):
        pts = _l_shape_points()
        convex = Polygon(pts).convex_hull if len(pts) >= 3 else None
        from shapely.geometry import MultiPoint
        convex = MultiPoint(pts).convex_hull
        hull = hull_for_cluster(pts)
        assert hull.area <= convex.area + 1e-9

    def test_l_shape_recovers_concavity(self):
        # Convex hull of the L covers the missing quadrant; a good concave
        # hull should cut away at least some of that empty bay.
        pts = _l_shape_points()
        from shapely.geometry import MultiPoint
        convex = MultiPoint(pts).convex_hull
        hull = hull_for_cluster(pts)
        assert hull.area < convex.area * 0.995

    def test_degenerate_few_points_fall_back_to_convex(self):
        triangle = [(0, 0), (1, 0), (0.5, 1)]
        hull = hull_for_cluster(triangle)
        assert isinstance(hull, Polygon)
        assert abs(hull.area - 0.5) < 1e-9

    def test_guarded_against_infinite_loop(self):
        import time
        pts = [
            (math.cos(t), math.sin(t))
            for t in [i * math.pi / 12 for i in range(24)]
        ]
        start = time.time()
        hull = hull_for_cluster(pts)
        assert (time.time() - start) < 2.0
        assert isinstance(hull, Polygon)

    def test_output_shrinks_but_stays_close(self):
        # Duckham hulls legitimately drop interior ear vertices; the contract
        # we need is: valid polygon, area strictly below convex, and the
        # retained region still covers a solid share of the point extent.
        pts = _l_shape_points()
        from shapely.geometry import MultiPoint
        hull = hull_for_cluster(pts)
        convex = MultiPoint(pts).convex_hull
        assert convex.contains(hull)
        assert hull.area >= convex.area * 0.5
