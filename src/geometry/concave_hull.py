"""R14-P1 Concave hull via restricted Delaunay-style edge elimination.

Duckham et al. (2008)-style "s-hull": repeatedly remove the longest hull
edge whose replacement diagonal keeps the polygon simple and satisfies a
maximum-edge-length constraint derived from the cluster's NN distance.
Zero-dependency (pure shapely), unlike the `alphashape` package which
pulls in scipy.

References:
- Duckham, Kulik, Worboys, Galton (2008): Efficient generation of simple
  polygons for characterizing the shape of a set of points in the plane,
  Pattern Recognition 41(10).
"""

from __future__ import annotations

from typing import Sequence

from shapely.geometry import LineString, MultiPoint, Polygon
from shapely.geometry import Point

from shapely.ops import unary_union


def _mean_nn_distance(pts):
    """Mean nearest-neighbour distance — Duckham's density scale."""
    import math
    n = len(pts)
    total = 0.0
    for i, p in enumerate(pts):
        best = min(
            math.hypot(p[0] - q[0], p[1] - q[1])
            for j, q in enumerate(pts) if j != i
        )
        total += best
    return total / max(n, 1)




def _segment_intersect_ok(polygon: Polygon, new_edge: LineString) -> bool:
    """New diagonal may touch the ring only at its two endpoints; it must
    not exit or run along the boundary elsewhere."""
    a, b = new_edge.coords[0], new_edge.coords[-1]
    for p in (a, b):
        if not polygon.touches(Point(p)) and not polygon.contains(Point(p)):
            return False
    interior = LineString(list(new_edge.coords))
    return not polygon.exterior.crosses(interior)


def concave_hull(
    points: Sequence[tuple[float, float]],
    k: float = 0.3,
) -> Optional[Polygon]:
    """Compute a concave hull tighter than the convex hull.

    k ∈ (0, 1]: allowed-vertex-removal ratio. A vertex may be deleted
    when its replacement diagonal is shorter than k × (current longest
    hull edge). Larger k → more concave/tighter output; k→0 degenerates
    to the convex hull. Falls back to convex hull for <4 points or
    unstable refinement.
    """
    pts = [(float(x), float(y)) for x, y in points]
    multi = MultiPoint(pts)
    poly = multi.convex_hull
    if len(pts) < 4 or poly.geom_type != "Polygon":
        return poly if poly.geom_type == "Polygon" else None

    # Adaptive threshold: iterate with a decaying allowance on the polygon's
    # own longest edge. Each pass permits eliminating any vertex whose
    # removal diagonal is shorter than k * longest-remaining-edge. This
    # relative rule opens large bays (L-shape inner quadrant) even when the
    # absolute gap dwarfs point spacing, while ear vertices along dense
    # edges go first because their diagonals are comparatively tiny.
    changed = True
    guard = 0
    while changed and guard < 100:
        guard += 1
        changed = False
        ring = list(poly.exterior.coords)[:-1]
        n = len(ring)
        # Duckham criterion: an edge may be eliminated when its replacement
        # diagonal is shorter than the max allowed length. Longer current
        # edges with short diagonals open the bays.
        longest = max(
            LineString([ring[i], ring[(i + 1) % n]]).length for i in range(n)
        )
        allow = k * longest
        candidates = []
        for i in range(n):
            j = (i + 2) % n
            a, b, c = ring[i], ring[(i + 1) % n], ring[j]
            diag = LineString([a, c])
            if diag.length > allow:
                continue
            tri = Polygon([a, b, c])
            if tri.area <= 0:
                continue
            if len(ring) <= 4:
                break
            new_ring = [p for idx, p in enumerate(ring) if idx != (i + 1) % n]
            new_poly = Polygon(new_ring)
            if not new_poly.is_valid or new_poly.area <= 0:
                continue
            if not _segment_intersect_ok(new_poly, diag):
                continue
            candidates.append((tri.area, i))
        if not candidates:
            break
        _, best_i = min(candidates)
        ring = list(poly.exterior.coords)[:-1]
        if len(ring) <= 4:
            break  # triangle: cannot shrink further
        ring.pop((best_i + 1) % len(ring))
        new_poly = Polygon(ring)
        if not new_poly.is_valid or new_poly.area <= 0:
            continue
        poly = new_poly
        changed = True
    return poly


def hull_for_cluster(points: Sequence[tuple[float, float]]) -> Optional[Polygon]:
    """Public entry replacing MultiPoint(...).convex_hull in providers."""
    return concave_hull(points, k=0.8)
