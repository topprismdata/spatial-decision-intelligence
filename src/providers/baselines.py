"""R2 Baseline Providers: ExistingOpenBoundary, RoadBlock, BuildingCluster, AreaPrior.

Design Note v1.1 §3. All output PROPOSED only.
"""

from __future__ import annotations

import math
from typing import Optional

from src.domain.contracts import (
    BoundaryHypothesis,
    Evidence,
    EvidenceType,
    HypothesisStatus,
    ProviderResult,
    ProviderStatus,
)
from src.providers import (
    BuildingSourcePolicy,
    ProviderHypothesis,
    ProviderOutput,
    ProviderProvenance,
    ProviderRequest,
    RoadProfileVariant,
)


def _metric_service():
    from src.coordinate import MetricCRSStrategy, GeometryTransformer
    return MetricCRSStrategy(), GeometryTransformer()


def _compute_area_m2(wkt_str: str) -> float:
    """Compute area in m² via MetricGeometryService."""
    from src.coordinate.metric_service import MetricGeometryService
    return MetricGeometryService().area_m2(wkt_str)

def _seed_distance_m(geom_wkt: str, lng: float, lat: float) -> float:
    from shapely import wkt as _wkt
    from shapely.geometry import Point
    geom = _wkt.loads(geom_wkt)
    pt = Point(lng, lat)
    return geom.distance(pt) * 111_000.0


# ── ExistingOpenBoundaryProvider ─────────────────────────────────────────────


class ExistingOpenBoundaryProvider:
    """B1: Returns existing open polygons as boundary candidates."""

    SEARCH_RADIUS_M = 500.0

    def __init__(self):
        self._version = "1.0"

    def generate(self, request: ProviderRequest) -> ProviderOutput:
        seed = request.seed_observations[0] if request.seed_observations else None
        if not seed:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)

        from src.coordinate.metric_crs import bbox_from_center
        bbox = bbox_from_center(seed.point[0], seed.point[1], self.SEARCH_RADIUS_M)

        hypotheses = []
        evidence_list = []

        from shapely import wkt as _wkt
        from shapely.geometry import Point
        seed_pt = Point(seed.point[0], seed.point[1])
        uncertainty_deg = seed.uncertainty_radius_m / 111_000.0

        # Load OSM landuse=residential polygons
        from src.observation.overpass_adapter import OverpassAdapter
        adapter = OverpassAdapter()
        observations = adapter.fetch(bbox=bbox, feature_type="residential", source_label="OSM_landuse")

        for obs in observations:
            if not obs.raw_geometry:
                continue
            try:
                geom = _wkt.loads(obs.raw_geometry)
                if geom.geom_type not in ("Polygon", "MultiPolygon"):
                    continue
                if geom.is_empty or not geom.is_valid:
                    continue
                if not geom.intersects(seed_pt.buffer(uncertainty_deg)):
                    continue

                name_present = any(f.startswith("name=") or not f.startswith("osm/") and not f.startswith("landuse=") for f in obs.observed_features)
                dist = _seed_distance_m(obs.raw_geometry, seed.point[0], seed.point[1])
                area_m2 = _compute_area_m2(obs.raw_geometry)

                h = BoundaryHypothesis(
                    entity_id=request.target_entity_id,
                    geometry=obs.raw_geometry,
                    generator="ExistingOpenBoundaryProvider",
                    status=HypothesisStatus.PROPOSED,
                )
                ph = ProviderHypothesis(
                    hypothesis=h,
                    generation_score=0.5,
                    provider_features={
                        "name_present": 1.0 if name_present else 0.0,
                        "source_semantic_role": "RESIDENTIAL_LANDUSE",
                        "seed_distance_m": round(dist, 2),
                        "polygon_area_m2": round(area_m2, 2),
                    },
                )
                hypotheses.append(ph)
                evidence_list.append(Evidence(
                    source=obs.source, evidence_type=EvidenceType.GEOMETRY,
                    content=obs.raw_geometry[:200], confidence=0.5,
                ))
            except Exception:
                continue

        if not hypotheses:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)
        return ProviderOutput(
            status=ProviderStatus.APPLICABLE,
            hypotheses=tuple(hypotheses), evidence=tuple(evidence_list),
            provenance=ProviderProvenance(
                provider_id="ExistingOpenBoundaryProvider", provider_version=self._version,
                parameter_profile="landuse=residential, name_as_feature",
            ),
        )


# ── RoadBlockProvider ────────────────────────────────────────────────────────


class RoadBlockProvider:
    """B2: Road-based candidates with STRONG_ONLY and STRONG_PLUS_WEAK families."""

    STRONG_TAGS = frozenset({"primary", "secondary", "tertiary", "trunk", "motorway"})
    WEAK_TAGS = frozenset({"primary_link", "secondary_link", "tertiary_link", "service"})
    EXCLUDED_TAGS = frozenset({"footway", "path", "cycleway", "bridleway", "track", "pedestrian", "steps"})
    SEARCH_RADIUS_M = 500.0

    def __init__(self):
        self._version = "1.0"

    def generate(self, request: ProviderRequest) -> ProviderOutput:
        seed = request.seed_observations[0] if request.seed_observations else None
        if not seed:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)

        from src.coordinate.metric_crs import bbox_from_center
        bbox = bbox_from_center(seed.point[0], seed.point[1], self.SEARCH_RADIUS_M)

        hypotheses = []
        evidence_list = []

        from shapely import wkt as _wkt
        from shapely.geometry import Point
        seed_pt = Point(seed.point[0], seed.point[1])
        uncertainty_deg = seed.uncertainty_radius_m / 111_000.0

        for variant in RoadProfileVariant:
            try:
                roads = self._load_roads_for_variant(variant, bbox)
                blocks = self._polygonize_blocks(roads)
                for block in blocks:
                    if block.geom_type != "Polygon" or block.is_empty or not block.is_valid:
                        continue
                    if not block.intersects(seed_pt.buffer(uncertainty_deg)):
                        continue
                    dist = _seed_distance_m(block.wkt, seed.point[0], seed.point[1])
                    area_m2 = _compute_area_m2(block.wkt)
                    h = BoundaryHypothesis(
                        entity_id=request.target_entity_id,
                        geometry=block.wkt,
                        generator=f"RoadBlockProvider_{variant.value}",
                        status=HypothesisStatus.PROPOSED,
                    )
                    ph = ProviderHypothesis(
                        hypothesis=h,
                        generation_score=0.4,
                        provider_features={
                            "road_profile_variant": variant.value,
                            "seed_distance_m": round(dist, 2),
                            "block_area_m2": round(area_m2, 2),
                        },
                    )
                    hypotheses.append(ph)
            except Exception:
                continue

        if not hypotheses:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)
        return ProviderOutput(
            status=ProviderStatus.APPLICABLE,
            hypotheses=tuple(hypotheses),
            provenance=ProviderProvenance(
                provider_id="RoadBlockProvider", provider_version=self._version,
                parameter_profile="strong/weak/excluded versioned profile",
            ),
        )

    def _load_roads_for_variant(self, variant: RoadProfileVariant, bbox):
        from shapely.ops import unary_union
        allowed = set(self.STRONG_TAGS)
        if variant == RoadProfileVariant.STRONG_PLUS_WEAK:
            allowed |= set(self.WEAK_TAGS)

        geoms = []
        from src.observation.overpass_adapter import OverpassAdapter
        adapter = OverpassAdapter()
        observations = adapter.fetch(bbox=bbox, feature_type="roads")
        for obs in observations:
            highway_tag = next((f.split("=", 1)[1] for f in obs.observed_features if f.startswith("highway=")), "")
            if highway_tag in allowed:
                try:
                    geoms.append(_wkt.loads(obs.raw_geometry))
                except Exception:
                    pass
        return unary_union(geoms) if geoms else None

    @staticmethod
    def _polygonize_blocks(road_network):
        from shapely.ops import polygonize, unary_union
        if road_network is None:
            return []
        buffered = road_network.buffer(0.00005)  # ~5m buffer to form closed regions
        return list(polygonize(unary_union(buffered)))


# ── BuildingClusterProvider ──────────────────────────────────────────────────


class BuildingClusterProvider:
    """B3/B5: Building cluster candidates with BuildingSourcePolicy."""

    CLUSTER_DISTANCE_M = 30.0
    SEARCH_RADIUS_M = 500.0

    def __init__(self):
        self._version = "1.0"

    def generate(self, request: ProviderRequest, source_policy: BuildingSourcePolicy = BuildingSourcePolicy.OSM_ONLY) -> ProviderOutput:
        seed = request.seed_observations[0] if request.seed_observations else None
        if not seed:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)

        from src.coordinate.metric_crs import bbox_from_center
        bbox = bbox_from_center(seed.point[0], seed.point[1], self.SEARCH_RADIUS_M)

        hypotheses = []
        evidence_list = []

        from shapely import wkt as _wkt
        from shapely.geometry import Point, MultiPoint
        from shapely.ops import unary_union

        seed_pt = Point(seed.point[0], seed.point[1])
        uncertainty_deg = seed.uncertainty_radius_m / 111_000.0
        cluster_deg = self.CLUSTER_DISTANCE_M / 111_000.0

        sources = {
            BuildingSourcePolicy.OSM_ONLY: ["OSM"],
            BuildingSourcePolicy.OVERTURE_ONLY: ["Overture"],
            BuildingSourcePolicy.MICROSOFT_ONLY: ["Microsoft"],
            BuildingSourcePolicy.MULTI_SOURCE: ["OSM", "Overture", "Microsoft"],
        }.get(source_policy, ["OSM"])

        for source in sources:
            buildings = self._load_buildings(source, bbox)
            if not buildings:
                continue

            clusters = self._cluster_buildings(buildings, cluster_deg)
            for cluster_pts in clusters:
                if len(cluster_pts) < 3:
                    continue
                from src.geometry.concave_hull import hull_for_cluster
                hull_geom = hull_for_cluster(cluster_pts) or MultiPoint(cluster_pts).convex_hull
                if hull_geom.geom_type != "Polygon" or hull_geom.is_empty:
                    continue
                if not hull_geom.intersects(seed_pt.buffer(uncertainty_deg)):
                    continue
                dist = _seed_distance_m(hull_geom.wkt, seed.point[0], seed.point[1])
                area_m2 = _compute_area_m2(hull_geom.wkt)

                h = BoundaryHypothesis(
                    entity_id=request.target_entity_id,
                    geometry=hull_geom.wkt,
                    generator=f"BuildingClusterProvider_{source}",
                    status=HypothesisStatus.PROPOSED,
                )
                ph = ProviderHypothesis(
                    hypothesis=h,
                    generation_score=0.45,
                    provider_features={
                        "building_count": len(cluster_pts),
                        "seed_distance_m": round(dist, 2),
                        "cluster_area_m2": round(area_m2, 2),
                        "source_policy": source_policy.value,
                    },
                )
                hypotheses.append(ph)

        if not hypotheses:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)
        return ProviderOutput(
            status=ProviderStatus.APPLICABLE,
            hypotheses=tuple(hypotheses),
            provenance=ProviderProvenance(
                provider_id="BuildingClusterProvider", provider_version=self._version,
                parameter_profile=f"cluster_distance={self.CLUSTER_DISTANCE_M}m, policy={source_policy.value}",
            ),
        )

    @staticmethod
    def _load_buildings(source: str, bbox):
        from shapely import wkt as _wkt
        from shapely.geometry import Polygon
        buildings = []
        if source == "OSM":
            from src.observation.overpass_adapter import OverpassAdapter
            adapter = OverpassAdapter()
            observations = adapter.fetch(bbox=bbox, feature_type="roads")
            for obs in observations:
                if obs.raw_geometry and "building" in str(obs.observed_features).lower():
                    try:
                        g = _wkt.loads(obs.raw_geometry)
                        if g.geom_type in ("Polygon", "MultiPolygon"):
                            buildings.append(g)
                    except Exception:
                        pass
        elif source == "Overture":
            from src.observation.overture_adapter import OvertureAdapter
            adapter = OvertureAdapter()
            observations = adapter.fetch(theme="buildings")
            for obs in observations:
                try:
                    g = _wkt.loads(obs.raw_geometry)
                    buildings.append(g)
                except Exception:
                    pass
        elif source == "Microsoft":
            from src.observation.microsoft_adapter import MicrosoftBuildingsAdapter
            adapter = MicrosoftBuildingsAdapter()
            observations = adapter.fetch()
            for obs in observations:
                try:
                    g = _wkt.loads(obs.raw_geometry)
                    buildings.append(g)
                except Exception:
                    pass
        return buildings

    @staticmethod
    def _cluster_buildings(buildings, threshold_deg):
        """Simple DBSCAN-like clustering using centroid distance."""
        centroids = [(g.centroid.x, g.centroid.y, g) for g in buildings]
        visited = [False] * len(centroids)
        clusters = []
        for i in range(len(centroids)):
            if visited[i]:
                continue
            cluster = []
            queue = [i]
            while queue:
                idx = queue.pop(0)
                if visited[idx]:
                    continue
                visited[idx] = True
                cluster.append((centroids[idx][0], centroids[idx][1]))
                for j in range(len(centroids)):
                    if not visited[j]:
                        dx = centroids[i][0] - centroids[j][0]
                        dy = centroids[i][1] - centroids[j][1]
                        if (dx * dx + dy * dy) ** 0.5 < threshold_deg:
                            queue.append(j)
            if cluster:
                clusters.append(cluster)
        return clusters


# ── AreaPriorBaseline ────────────────────────────────────────────────────────


class AreaPriorBaseline:
    """B0: Circular buffer from seed point + AreaPrior. EXPERIMENTAL BASELINE."""

    def __init__(self):
        self._version = "1.0"

    def generate(self, request: ProviderRequest) -> ProviderOutput:
        seed = request.seed_observations[0] if request.seed_observations else None
        priors = request.optional_priors
        if not seed or not priors or not priors.area_prior:
            return ProviderOutput(status=ProviderStatus.NOT_APPLICABLE)

        area_m2 = priors.area_prior.value_m2
        radius_m = math.sqrt(area_m2 / math.pi)

        from shapely.geometry import Point
        from src.coordinate.metric_service import MetricGeometryService
        _ms = MetricGeometryService()

        tol_deg = _ms.snap_tolerance_deg(radius_m, seed.point[1])
        circle = Point(seed.point[0], seed.point[1]).buffer(tol_deg)

        bh = BoundaryHypothesis(
            entity_id=request.target_entity_id,
            geometry=circle.wkt,
            generator="AreaPriorBaseline",
            status=HypothesisStatus.PROPOSED,
        )
        ph = ProviderHypothesis(
            hypothesis=bh, generation_score=0.1,
            provider_features={
                "area_prior_m2": area_m2,
                "radius_m": round(radius_m, 2),
                "baseline_type": "EXPERIMENTAL",
            },
        )

        return ProviderOutput(
            status=ProviderStatus.APPLICABLE,
            hypotheses=(ph,),
            provenance=ProviderProvenance(
                provider_id="AreaPriorBaseline", provider_version=self._version,
                parameter_profile=f"area_prior={area_m2}m²",
            ),
        )