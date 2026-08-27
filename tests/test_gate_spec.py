"""
Tests for the Declarative Gate Specification engine
(src/validation/gate_spec.py).

Covers:
  INV-9  spec/data separation - interpreter is domain-blind
  INV-10 fail-closed loading - unknown ops/nodes raise at construction
  INV-11 totality - missing facts fail constraints, never raise
  semantics: operators, combinators, blocked/must/warns polarity,
  GateSpec serialization round-trip, and a new-domain spec written as
  pure data (the 'school profile' seam).
"""

import pytest

from src.validation.gate_spec import (
    AllOf,
    AnyOf,
    Fact,
    GateSpec,
    MinCount,
    NoneMatch,
    Not,
    SpecError,
    WarnIf,
    constraint_from_dict,
    constraint_to_dict,
    evaluate_spec,
)


# ---------------------------------------------------------------------------
# INV-10: fail-closed spec construction.
# ---------------------------------------------------------------------------

def test_unknown_operator_rejected_at_load():
    with pytest.raises(SpecError):
        Fact(field="area_m2", op="magic_op", value=1).validate()


def test_unknown_node_rejected_at_deserialize():
    with pytest.raises(SpecError):
        constraint_from_dict({"node": "quantum", "field": "x"})


def test_empty_combinator_rejected():
    with pytest.raises(SpecError):
        AllOf(children=()).validate()
    with pytest.raises(SpecError):
        AnyOf(children=()).validate()


def test_serialization_round_trip():
    spec = GateSpec(
        gate_id="roundtrip",
        blocked=NoneMatch(field="evidence", substrings=("conflict",)),
        must=AllOf(children=(
            Fact(field="area_m2", op="between", value=(10.0, 20.0)),
            MinCount(field="evidence", n=1),
            WarnIf(child=Not(child=Fact(field="compactness_ok", op="eq", value=True))),
        )),
    )
    reborn = GateSpec.from_dict(spec.to_dict())
    assert reborn.gate_id == spec.gate_id
    assert reborn.must == spec.must
    assert reborn.blocked == spec.blocked


# ---------------------------------------------------------------------------
# INV-11: totality over sparse facts.
# ---------------------------------------------------------------------------

def test_missing_fact_fails_never_raises():
    spec = GateSpec(gate_id="t", must=Fact(field="area_m2", op="gt", value=0))
    outcome = evaluate_spec(spec, {})  # no facts at all
    assert outcome.status == "FAILED"
    assert not outcome.decision_ready


def test_none_fact_in_arithmetic_op_fails_safely():
    spec = GateSpec(gate_id="t", must=Fact(field="x", op="gte", value=5))
    assert evaluate_spec(spec, {"x": None}).status == "FAILED"


# ---------------------------------------------------------------------------
# Operator semantics.
# ---------------------------------------------------------------------------

def test_between_operator():
    spec = GateSpec(gate_id="t",
                    must=Fact(field="a", op="between", value=(1, 3)))
    assert evaluate_spec(spec, {"a": 2}).status == "PASSED"
    assert evaluate_spec(spec, {"a": 3}).status == "PASSED"   # inclusive
    assert evaluate_spec(spec, {"a": 0.9}).status == "FAILED"


def test_none_match_scans_list_content():
    spec = GateSpec(gate_id="t",
                    must=NoneMatch(field="evidence", substrings=("conflict",)))
    ok = evaluate_spec(spec, {"evidence": ["osm landuse", "poi point"]})
    bad = evaluate_spec(spec, {"evidence": ["conflict_contradiction found"]})
    assert ok.status == "PASSED"
    assert bad.status == "FAILED"


def test_not_and_anyof_combinators():
    spec = GateSpec(gate_id="t", must=AnyOf(children=(
        Fact(field="a", op="eq", value=1),
        Not(child=Fact(field="b", op="eq", value=2)),
    )))
    assert evaluate_spec(spec, {"a": 1, "b": 2}).status == "PASSED"
    assert evaluate_spec(spec, {"a": 9, "b": 2}).status == "FAILED"
    assert evaluate_spec(spec, {"a": 9, "b": 3}).status == "PASSED"


# ---------------------------------------------------------------------------
# blocked / must / warns polarity.
# ---------------------------------------------------------------------------

def test_blocked_holding_hardens_outcome():
    spec = GateSpec(
        gate_id="t",
        blocked=Fact(field="corrupt", op="eq", value=True),
        must=Fact(field="ok", op="eq", value=True),
        warns=WarnIf(child=Fact(field="pretty", op="eq", value=True)),
    )
    # blocked fires even though must would pass: BLOCKED, not warnable.
    out = evaluate_spec(spec, {"corrupt": True, "ok": True, "pretty": True})
    assert out.status == "BLOCKED"
    assert not out.decision_ready


def test_must_fail_beats_warns():
    spec = GateSpec(
        gate_id="t",
        must=Fact(field="ok", op="eq", value=True),  # fails when ok=False
        warns=WarnIf(child=Fact(field="pretty", op="eq", value=True)),
    )
    out = evaluate_spec(spec, {"ok": False, "pretty": True})
    assert out.status == "FAILED"


def test_warnif_failure_downgrades_to_warned():
    spec = GateSpec(
        gate_id="t",
        must=Fact(field="ok", op="eq", value=True),
        warns=WarnIf(child=Fact(field="pretty", op="eq", value=True)),
    )
    assert evaluate_spec(spec, {"ok": True, "pretty": True}).status == "PASSED"
    out = evaluate_spec(spec, {"ok": True, "pretty": False})
    assert out.status == "WARNED"
    assert out.decision_ready  # warned stays consumable


def test_toplevel_warns_warnif_convention():
    # warns wrapped in WarnIf: finding non-emptiness signals the warning.
    spec = GateSpec(
        gate_id="t",
        must=Fact(field="ok", op="eq", value=True),
        warns=WarnIf(child=Fact(field="weak", op="eq", value=False)),
    )
    assert evaluate_spec(spec, {"ok": True, "weak": False}).status == "PASSED"
    assert evaluate_spec(spec, {"ok": True, "weak": True}).status == "WARNED"


def test_toplevel_warns_raw_constraint_convention():
    # raw warns: failing the constraint produces the warning.
    spec = GateSpec(
        gate_id="t",
        must=Fact(field="ok", op="eq", value=True),
        warns=Fact(field="weak", op="eq", value=False),
    )
    assert evaluate_spec(spec, {"ok": True, "weak": False}).status == "PASSED"
    assert evaluate_spec(spec, {"ok": True, "weak": True}).status == "WARNED"


# ---------------------------------------------------------------------------
# The 'new domain = new data' seam: a school profile written as pure data.
# ---------------------------------------------------------------------------

SCHOOL_GEOMETRY_SPEC = {
    "gate_id": "GeometryGate/SchoolProfile",
    "blocked": {
        "node": "any_of",
        "children": [
            {"node": "fact", "field": "wkt_empty", "op": "eq", "value": True},
            {"node": "fact", "field": "wkt_parse_error", "op": "present"},
            {"node": "fact", "field": "geom_is_valid", "op": "eq", "value": False},
        ],
    },
    "must": {
        "node": "all_of",
        "children": [
            # Schools are smaller than compounds: 2_000 .. 200_000 m2.
            {"node": "fact", "field": "area_m2", "op": "between",
             "value": [2_000.0, 200_000.0]},
        ],
    },
    "warns": {
        "node": "warn_if",
        "child": {"node": "fact", "field": "compactness_ok",
                  "op": "eq", "value": True},
    },
}


def test_new_domain_spec_as_pure_data():
    """No engine code touched: a school profile loads from a dict and
    evaluates with different bounds than the residential default."""
    spec = GateSpec.from_dict(SCHOOL_GEOMETRY_SPEC)

    same_polygon = {"wkt_empty": False, "wkt_parse_error": None,
                    "geom_is_valid": True, "compactness_ok": True}

    school_sized = dict(same_polygon, area_m2=15_000.0)
    compound_sized = dict(same_polygon, area_m2=900_000.0)

    assert evaluate_spec(spec, school_sized).status == "PASSED"
    assert evaluate_spec(spec, compound_sized).status == "FAILED"

    from src.validation.pipeline import GEOMETRY_SPEC
    assert evaluate_spec(GEOMETRY_SPEC, compound_sized).status == "PASSED"
