"""
Perception Operator Algebra (Proposal 4: Plugin Layer).

Perception algorithms (OSM providers, road-block polygonizers, cluster
hulls, future SAM/VLM models) are composable operators with typed stages:

    generate : ObservationBundle -> [SpatialHypothesis]
    refine   : SpatialHypothesis x ObservationBundle -> SpatialHypothesis
    verify   : SpatialHypothesis x ObservationBundle -> VerifyReport

Composition is data: a PerceptionPipeline is a list of operator ids resolved
through an OperatorRegistry. New perception models plug in by registration -
the reasoning layer (ranking, gates, disposition) never changes and never
sees a concrete algorithm class (INV-12).

Provenance invariant (INV-13): every hypothesis carries an append-only
lineage tuple of operator ids; refine appends, never rewrites. A published
boundary's full perceptual causal chain is readable from the hypothesis.

Veto semantics (INV-14): verify operators never delete hypotheses - they
attach VerifyReports. A vetoed hypothesis survives with `verified=False`,
so downstream gates apply fail-closed policy on explicit evidence rather
than on silent absence. (Deleting candidates in the perception layer would
hide exactly the information the gates exist to reason about.)

The layer is domain-blind: no ontology, no geometry library imports beyond
shapely WKT handling in adapters; the core module imports nothing from
src.providers or src.agents.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data currency.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservationBundle:
    """The only thing perception operators may consume. Domain-blind:
    carriers are opaque key/value payloads; operators declare what they
    read via their `requires` set (checked at run time)."""

    seed_lng: float
    seed_lat: float
    target_entity_id: str = ""
    prior_area_m2: Optional[float] = None
    carriers: Dict[str, Any] = field(default_factory=dict)  # e.g. "roads_wkt", "buildings_wkt", "imagery_ref"

    def carrier(self, key: str) -> Any:
        return self.carriers.get(key)


@dataclass(frozen=True)
class SpatialHypothesis:
    """Operator-level boundary candidate with append-only lineage."""

    geometry_wkt: str
    method: str
    lineage: Tuple[str, ...] = ()          # e.g. ("gen:osm_face", "ref:concave_hull")
    metrics: Dict[str, Any] = field(default_factory=dict)

    def with_lineage(self, op_id: str, **metric_updates: Any) -> "SpatialHypothesis":
        """INV-13: refine produces a NEW hypothesis; lineage only grows.
        `method` keeps the ORIGINAL generator id - the lineage tuple is the
        full chain, the method is who produced the geometry."""
        metrics = dict(self.metrics)
        metrics.update(metric_updates)
        return SpatialHypothesis(
            geometry_wkt=self.geometry_wkt,
            method=self.method,
            lineage=self.lineage + (op_id,),
            metrics=metrics,
        )


@dataclass(frozen=True)
class VerifyReport:
    """Result of one verify operator on one hypothesis."""

    op_id: str
    passed: bool
    findings: Tuple[str, ...] = ()
    metrics: Dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ScoredCandidate:
    """Pipeline output handed to the reasoning layer."""

    hypothesis: SpatialHypothesis
    reports: Tuple[VerifyReport, ...] = ()

    @property
    def vetoed(self) -> bool:
        return any(not r.passed for r in self.reports)


# ---------------------------------------------------------------------------
# Operator interfaces.
# ---------------------------------------------------------------------------

class GenerateOp(ABC):
    op_id: str = ""
    requires: FrozenSet[str] = frozenset()

    def check_requirements(self, obs: ObservationBundle) -> None:
        missing = [k for k in self.requires if obs.carrier(k) is None]
        if missing:
            raise KeyError(f"{self.op_id} missing carriers: {missing}")

    @abstractmethod
    def generate(self, obs: ObservationBundle) -> List[SpatialHypothesis]:
        """Produce zero or more candidate hypotheses. Zero is a valid,
        honest output (evidence not applicable)."""


class RefineOp(ABC):
    op_id: str = ""
    requires: FrozenSet[str] = frozenset()

    @abstractmethod
    def refine(self, hyp: SpatialHypothesis,
               obs: ObservationBundle) -> SpatialHypothesis:
        """Return a refined hypothesis (or an equivalent copy with grown
        lineage when the op is a no-op for this input)."""


class VerifyOp(ABC):
    op_id: str = ""

    @abstractmethod
    def verify(self, hyp: SpatialHypothesis,
               obs: ObservationBundle) -> VerifyReport:
        """Judge a hypothesis. Never mutates or removes it (INV-14)."""


# ---------------------------------------------------------------------------
# Registry and pipeline.
# ---------------------------------------------------------------------------

class OperatorRegistry:
    """The plug-in seam (INV-12). Operators register by id and stage; the
    pipeline resolves ids through this registry, so adding a SAM or VLM
    operator is a registration, not an architecture change."""

    def __init__(self) -> None:
        self._generate: Dict[str, GenerateOp] = {}
        self._refine: Dict[str, RefineOp] = {}
        self._verify: Dict[str, VerifyOp] = {}

    def register_generate(self, op: GenerateOp) -> "OperatorRegistry":
        self._generate[op.op_id] = op
        return self

    def register_refine(self, op: RefineOp) -> "OperatorRegistry":
        self._refine[op.op_id] = op
        return self

    def register_verify(self, op: VerifyOp) -> "OperatorRegistry":
        self._verify[op.op_id] = op
        return self

    def resolve_generate(self, op_id: str) -> GenerateOp:
        if op_id not in self._generate:
            raise KeyError(f"unregistered generate op '{op_id}'")
        return self._generate[op_id]

    def resolve_refine(self, op_id: str) -> RefineOp:
        if op_id not in self._refine:
            raise KeyError(f"unregistered refine op '{op_id}'")
        return self._refine[op_id]

    def resolve_verify(self, op_id: str) -> VerifyOp:
        if op_id not in self._verify:
            raise KeyError(f"unregistered verify op '{op_id}'")
        return self._verify[op_id]


@dataclass(frozen=True)
class PipelinePlan:
    """Composition as data (serializable)."""

    generate_ops: Tuple[str, ...] = ()
    refine_ops: Tuple[str, ...] = ()
    verify_ops: Tuple[str, ...] = ()


class PerceptionPipeline:
    """Executes a plan against a registry. Fan-out generate, then chain
    refines (each sees the previous op's output), then run verifies."""

    def __init__(self, registry: OperatorRegistry, plan: PipelinePlan) -> None:
        self._registry = registry
        self.plan = plan

    def run(self, obs: ObservationBundle) -> List[ScoredCandidate]:
        candidates: List[SpatialHypothesis] = []
        for gen_id in self.plan.generate_ops:
            op = self._registry.resolve_generate(gen_id)
            op.check_requirements(obs)
            for hyp in op.generate(obs):
                current = hyp
                for ref_id in self.plan.refine_ops:
                    rop = self._registry.resolve_refine(ref_id)
                    if rop.requires and any(
                        obs.carrier(k) is None for k in rop.requires
                    ):
                        continue  # refinement without its carrier: no-op
                    current = rop.refine(current, obs)
                candidates.append(current)

        scored: List[ScoredCandidate] = []
        for hyp in candidates:
            reports: List[VerifyReport] = []
            for ver_id in self.plan.verify_ops:
                vop = self._registry.resolve_verify(ver_id)
                reports.append(vop.verify(hyp, obs))
            scored.append(ScoredCandidate(hypothesis=hyp,
                                          reports=tuple(reports)))
        return scored
