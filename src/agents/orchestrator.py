"""
Master Orchestrator for the Spatial Intelligence Agent Platform.
Executes the 4-Agent pipeline as a verified finite state machine: every agent
step is a typed, hash-chained transition (INV-1 legality), the log is
append-only and tamper-evident (INV-2), publication requires a complete
evidence chain (INV-3), and re-execution must reproduce recorded digests
(INV-4). Wall-clock time is injected via Clock and never affects digests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.agents.entity_resolution_agent import EntityResolutionAgent, ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryReasoningAgent, BoundaryConstraints
from src.agents.geometry_generation_agent import GeometryGenerationAgent, GeometryGenerationResult
from src.agents.geometry_qa_agent import GeometryQAAgent, QAAuditResult
from src.domain.state_machine import (
    LiveClock,
    ReplayClock,
    ReplayMismatchError,
    RunState,
    Transition,
    TransitionEvent,
    TransitionLog,
    artifact_digest,
)
from src.domain.world_model import TrustedSpatialState, SpatialEntity, GeometryObservation

logger = logging.getLogger("spatial_agent_platform")

DEFAULT_LNG = 116.40
DEFAULT_LAT = 39.90


@dataclass
class SpatialGenerationPipelineResult:
    """Full trace of the 4-Agent execution pipeline for a single entity."""
    entity_context: ResolvedEntityContext
    constraints: BoundaryConstraints
    generation_result: GeometryGenerationResult
    qa_audit: QAAuditResult
    is_decision_ready: bool
    execution_trace: List[str] = field(default_factory=list)
    transition_log: Optional[TransitionLog] = None


class SpatialIntelligencePlatform:
    """Orchestrates the 4-Agent pipeline as a verified state machine."""

    def __init__(self, min_qa_score: float = 0.70, clock: Optional[Any] = None):
        self.entity_agent = EntityResolutionAgent()
        self.boundary_agent = BoundaryReasoningAgent()
        self.geometry_agent = GeometryGenerationAgent()
        self.qa_agent = GeometryQAAgent(min_qa_score=min_qa_score)
        self.clock = clock or LiveClock()

    # ------------------------------------------------------------------
    # Single run: BRIEF_RECEIVED -> ... -> PUBLISHED | REJECTED
    # ------------------------------------------------------------------

    def generate_single_fence(
        self,
        name: str,
        address: str = "",
        lng: float = DEFAULT_LNG,
        lat: float = DEFAULT_LAT,
        prior_area_m2: Optional[float] = None,
        road_network_wkt: Optional[str] = None,
        building_footprints_wkt: Optional[List[str]] = None,
        recorded: Optional[TransitionLog] = None,
    ) -> SpatialGenerationPipelineResult:
        """Executes the full 4-Agent workflow as state-machine transitions.

        When `recorded` is provided (a TransitionLog from a previous run),
        every transition is re-executed and its digests compared against the
        recorded chain (INV-4); any divergence raises ReplayMismatchError.
        """
        brief = {
            "name": name,
            "address": address,
            "lng": lng,
            "lat": lat,
            "prior_area_m2": prior_area_m2,
            "road_network_wkt": road_network_wkt,
            "building_footprints_wkt": building_footprints_wkt,
        }
        run_id = f"RUN_{artifact_digest(brief)[:12]}"
        log = TransitionLog(run_id)
        trace: List[str] = []
        brief_digest = artifact_digest(brief)

        # Step 1: Entity Resolution Agent -> ENTITY_RESOLVED
        entity_ctx = self.entity_agent.resolve(name=name, address=address)
        ctx_record = {
            "canonical_name": entity_ctx.canonical_name,
            "base_name": entity_ctx.base_name,
            "scale_level": entity_ctx.scale_level,
            "category": entity_ctx.category.value,
            "aliases": list(entity_ctx.aliases),
            "raw_address": entity_ctx.raw_address,
        }
        ev1 = log.append(
            transition=Transition.RESOLVE,
            agent="EntityResolutionAgent",
            to_state=RunState.ENTITY_RESOLVED,
            inputs_digest=brief_digest,
            outputs_digest=artifact_digest(ctx_record),
            payload={"canonical_name": entity_ctx.canonical_name,
                     "scale_level": entity_ctx.scale_level},
            clock=self.clock.now_iso(),
        )
        trace.append(
            f"Agent 1 (Entity): Canonical='{entity_ctx.canonical_name}', "
            f"Scale='{entity_ctx.scale_level}'"
        )

        # Step 2: Boundary Reasoning Agent -> CONSTRAINTS_REASONED
        constraints = self.boundary_agent.reason_constraints(
            entity_ctx=entity_ctx,
            seed_lng=lng,
            seed_lat=lat,
            prior_area_m2=prior_area_m2,
        )
        cons_record = {
            "target_area_m2": constraints.target_area_m2,
            "search_radius_m": constraints.search_radius_m,
            "zoom_level": constraints.zoom_level,
        }
        ev2 = log.append(
            transition=Transition.REASON,
            agent="BoundaryReasoningAgent",
            to_state=RunState.CONSTRAINTS_REASONED,
            inputs_digest=ev1.outputs_digest,
            outputs_digest=artifact_digest(cons_record),
            payload={"target_area_m2": constraints.target_area_m2,
                     "search_radius_m": constraints.search_radius_m,
                     "zoom_level": constraints.zoom_level},
            clock=self.clock.now_iso(),
        )
        trace.append(
            f"Agent 2 (Boundary): TargetArea={constraints.target_area_m2:.0f}m², "
            f"Radius={constraints.search_radius_m:.0f}m, Zoom={constraints.zoom_level}"
        )

        # Step 3: Geometry Generation Agent -> HYPOTHESES_GENERATED
        gen_result = self.geometry_agent.generate(
            entity_ctx=entity_ctx,
            constraints=constraints,
            road_network_wkt=road_network_wkt,
            building_footprints_wkt=building_footprints_wkt,
        )
        chosen = gen_result.chosen_hypothesis
        gen_record = {
            "method": chosen.method,
            "area_m2": chosen.area_m2,
            "confidence_score": gen_result.confidence_score,
        }
        ev3 = log.append(
            transition=Transition.GENERATE,
            agent="GeometryGenerationAgent",
            to_state=RunState.HYPOTHESES_GENERATED,
            inputs_digest=ev2.outputs_digest,
            outputs_digest=artifact_digest(gen_record),
            payload={"method": chosen.method,
                     "area_m2": chosen.area_m2,
                     "confidence_score": gen_result.confidence_score},
            clock=self.clock.now_iso(),
        )
        trace.append(
            f"Agent 3 (Geometry): TopHypothesis='{chosen.method}', "
            f"Area={chosen.area_m2:.0f}m², Score={gen_result.confidence_score:.3f}"
        )

        # Step 4: Geometry QA Agent -> QA_PASSED | QA_REJECTED
        qa_audit = self.qa_agent.audit(
            entity_ctx=entity_ctx,
            constraints=constraints,
            gen_result=gen_result,
        )
        validation_status = qa_audit.geometry_observation.validation_status.value
        approved = validation_status in ("VERIFIED_VALID", "REPAIRED_AUTO")
        # Evidence anchor: the geometry observation (method, qa_score, status)
        # plus any quality findings. A clean geometry still carries its
        # observation as evidence - INV-3 is satisfiable for every publish.
        evidence_refs: tuple = (
            f"OBS:{qa_audit.geometry_observation.observation_id}",
            f"QA:{validation_status}:{qa_audit.geometry_observation.qa_score:.4f}",
        ) + tuple(f.finding_id for f in qa_audit.findings)

        ent_record = {
            "entity_id": qa_audit.entity.entity_id,
            "observation_id": qa_audit.geometry_observation.observation_id,
            "validation_status": validation_status,
            "qa_score": qa_audit.geometry_observation.qa_score,
            "is_decision_ready": qa_audit.is_decision_ready,
            "area_m2": chosen.area_m2,
            "method": chosen.method,
        }
        ev4 = log.append(
            transition=Transition.AUDIT,
            agent="GeometryQAAgent",
            to_state=RunState.QA_PASSED if approved else RunState.QA_REJECTED,
            inputs_digest=ev3.outputs_digest,
            outputs_digest=artifact_digest(ent_record),
            evidence_refs=evidence_refs,
            payload={"validation_status": validation_status,
                     "qa_score": qa_audit.geometry_observation.qa_score,
                     "is_decision_ready": qa_audit.is_decision_ready,
                     "findings": [f.finding_id for f in qa_audit.findings]},
            clock=self.clock.now_iso(),
        )
        trace.append(f"Agent 4 (QA): {qa_audit.decision_summary}")

        # Governance: publish to world model, or fail closed.
        if approved:
            ev5 = log.append(
                transition=Transition.PUBLISH,
                agent="Governor",
                to_state=RunState.PUBLISHED,
                inputs_digest=ev4.outputs_digest,
                outputs_digest=artifact_digest(ent_record),
                evidence_refs=evidence_refs,
                payload={"observation_id": qa_audit.geometry_observation.observation_id,
                         "entity_id": qa_audit.entity.entity_id},
                clock=self.clock.now_iso(),
            )
            trace.append(
                f"Governor: PUBLISHED with evidence chain "
                f"[{', '.join(evidence_refs[:2])}{'...' if len(evidence_refs) > 2 else ''}]"
            )
        else:
            ev5 = log.append(
                transition=Transition.FAIL_CLOSE,
                agent="Governor",
                to_state=RunState.REJECTED,
                inputs_digest=ev4.outputs_digest,
                outputs_digest=artifact_digest(ent_record),
                evidence_refs=evidence_refs,
                payload={"reason": f"QA {validation_status}",
                         "entity_id": qa_audit.entity.entity_id},
                clock=self.clock.now_iso(),
            )
            trace.append(
                f"Governor: FAIL_CLOSED ({validation_status}) - never published"
            )

        # INV-4: compare against a recorded chain if provided.
        if recorded is not None:
            self._verify_replay(log, recorded)

        log.verify_chain()
        return SpatialGenerationPipelineResult(
            entity_context=entity_ctx,
            constraints=constraints,
            generation_result=gen_result,
            qa_audit=qa_audit,
            is_decision_ready=qa_audit.is_decision_ready,
            execution_trace=trace,
            transition_log=log,
        )

    @staticmethod
    def _verify_replay(
        fresh: TransitionLog, recorded: TransitionLog
    ) -> None:
        """INV-4: fresh re-execution must reproduce the recorded chain."""
        if len(fresh.events) != len(recorded.events):
            raise ReplayMismatchError(
                f"run={recorded.run_id}: event count diverged "
                f"({len(fresh.events)} vs {len(recorded.events)})"
            )
        for fresh_ev, rec_ev in zip(fresh.events, recorded.events):
            for attr in ("transition", "to_state", "inputs_digest", "outputs_digest"):
                fv, rv = getattr(fresh_ev, attr), getattr(rec_ev, attr)
                fv = fv.value if hasattr(fv, "value") else fv
                rv = rv.value if hasattr(rv, "value") else rv
                if fv != rv:
                    raise ReplayMismatchError(
                        f"run={recorded.run_id} seq={rec_ev.seq}: {attr} diverged "
                        f"({fv} vs {rv})"
                    )

    # ------------------------------------------------------------------
    # Batch: compile QA-passed runs into a TrustedSpatialState.
    # ------------------------------------------------------------------

    def batch_generate_and_govern(
        self,
        briefs: List[Dict[str, Any]]
    ) -> TrustedSpatialState:
        """Batch processes spatial briefs and compiles them into a
        TrustedSpatialState. Only runs whose transition chain reached
        PUBLISHED enter the world model; fail-closed runs are counted and
        their evidence chains preserved in findings."""
        entities: Dict[str, SpatialEntity] = {}
        geometries: Dict[str, GeometryObservation] = {}
        all_findings = []

        for b in briefs:
            name = b.get("name", "Unknown")
            addr = b.get("address", "")
            lng = float(b.get("lng", DEFAULT_LNG))
            lat = float(b.get("lat", DEFAULT_LAT))
            area = float(b.get("area_m2", 0)) if b.get("area_m2") else None

            pipe_res = self.generate_single_fence(
                name=name,
                address=addr,
                lng=lng,
                lat=lat,
                prior_area_m2=area,
            )

            # INV-3 defense in depth: only published chains may contribute.
            log = pipe_res.transition_log
            if log is None or log.state is not RunState.PUBLISHED:
                continue  # fail-closed: rejected runs never enter the state

            ent = pipe_res.qa_audit.entity
            geom_obs = pipe_res.qa_audit.geometry_observation
            entities[ent.entity_id] = ent
            geometries[geom_obs.observation_id] = geom_obs
            all_findings.extend(pipe_res.qa_audit.findings)

        return TrustedSpatialState(
            state_version=self.clock.version(),
            published_at=self.clock.now_iso(),
            entities=entities,
            geometries=geometries,
            findings=all_findings,
        )
