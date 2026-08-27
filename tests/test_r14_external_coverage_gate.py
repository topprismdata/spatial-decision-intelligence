"""Tests for R14-P2 ExternalCoverageGate (Amap-coverage baseline rule).

Rule under test: OSM residential polygon that is unnamed AND has no
residential POI in the external gazetteer ⇒ BLOCKED (→ REJECTED),
because it is most likely farmland/scrub mislabeled as landuse=residential.
"""

import pytest

from src.domain.contracts import ValidationStatus
from src.validation.external_coverage_gate import (
    ExternalCoverageGate,
    PolygonContext,
)


class _StaticProvider:
    """Returns True only for coordinates in _hits."""

    def __init__(self, hits=()):
        self._hits = {(round(a, 4), round(b, 4)) for a, b in hits}

    def has_residential_poi(self, lng, lat, radius_m=200.0):
        return (round(lng, 4), round(lat, 4)) in self._hits


class TestExternalCoverageGate:
    def test_named_polygon_passes_unconditionally(self):
        gate = ExternalCoverageGate(
            poi_provider=_StaticProvider(hits=[(116.33695, 40.07754)])
        )
        ctx = PolygonContext(osm_name="龙腾苑二区", centroid_lng=116.33, centroid_lat=40.07)
        result = gate.validate(ctx)
        assert result.status == ValidationStatus.PASSED
        assert result.decision_ready is True

    def test_unnamed_no_provider_warns_not_blocks(self):
        # No provider wired: the gate must abstain, not fabricate coverage.
        gate = ExternalCoverageGate(poi_provider=None)
        ctx = PolygonContext(osm_name="", centroid_lng=116.78, centroid_lat=40.34)
        result = gate.validate(ctx)
        assert result.status == ValidationStatus.WARNED
        assert "no_provider_wired" in result.findings[0]
        assert result.decision_ready is True

    def test_unnamed_with_poi_hit_passes_with_warning(self):
        gate = ExternalCoverageGate(
            poi_provider=_StaticProvider(hits=[(116.33695, 40.07754)])
        )
        ctx = PolygonContext(
            osm_name="   ",  # whitespace-only counts as unnamed
            centroid_lng=116.33695,
            centroid_lat=40.07754,
        )
        result = gate.validate(ctx)
        assert result.status == ValidationStatus.WARNED
        assert any("unnamed_but_poi_hit" in f for f in result.findings)
        assert result.decision_ready is True

    def test_unnamed_without_poi_blocked(self):
        # The core P2 rule.
        gate = ExternalCoverageGate(poi_provider=_StaticProvider(hits=[]))
        ctx = PolygonContext(osm_name=None, centroid_lng=116.7827, centroid_lat=40.3442)
        result = gate.validate(ctx)
        assert result.status == ValidationStatus.BLOCKED
        assert result.decision_ready is False
        assert any("unnamed_and_no_poi" in f for f in result.findings)
        assert any("probable_non_residential_landuse" in f for f in result.findings)

    def test_resolve_disposition_maps_blocked_to_rejected(self):
        from src.validation.pipeline import FinalDisposition, ValidationPipeline

        gate_results = [
            type("R", (), {"status": ValidationStatus.BLOCKED,
                           "validator": "ExternalCoverageGate"})()
        ]
        disposition = ValidationPipeline.resolve_final_disposition(gate_results)
        assert disposition == FinalDisposition.REJECTED

    def test_batch_semantics_farmland_rejected_compound_kept(self):
        # Realistic batch slice: one Miyun farmland polygon vs one hit-backed one.
        provider = _StaticProvider(hits=[(116.4501, 39.5502)])  # e.g. 长城溪溪小镇 area
        gate = ExternalCoverageGate(poi_provider=provider)

        farmland = PolygonContext(osm_name="", centroid_lng=116.7827, centroid_lat=40.3442)
        compound = PolygonContext(osm_name="", centroid_lng=116.4501, centroid_lat=39.5502)

        assert gate.validate(farmland).status == ValidationStatus.BLOCKED
        assert gate.validate(compound).status == ValidationStatus.WARNED
