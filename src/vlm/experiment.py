"""P1-04 VLM Vector Reasoning: structured VLM experiments for spatial semantic reasoning.

Per spec section 34:
- VLM requires a strict Experiment Brief before starting
- Input: deterministic scene renderings (from P1-03)
- Output: structured judgments only (no final trusted polygon)
- Evaluation: locked test subset, compares without-VLM vs with-VLM
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VLMQueryType(str, Enum):
    """Types of queries VLM can answer about a scene."""

    ROAD_SEMANTIC = "road_semantic"  # Is this road a boundary or internal?
    BUILDING_GROUPING = "building_grouping"  # Which buildings belong together?
    PHASE_SEPARATION = "phase_separation"  # Are there visible phases?
    MIXED_USE_EXCLUSION = "mixed_use_exclusion"  # Is there non-residential contamination?
    CANDIDATE_COMPARISON = "candidate_comparison"  # Which candidate boundary is best?
    ENTITY_ASSERTION = "entity_assertion"  # Is this a valid entity?
    SPATIAL_RELATION = "spatial_relation"  # What is the relation between entities?
    UNCERTAINTY = "uncertainty"  # How confident is the VLM in its judgment?


@dataclass
class VLMExperimentBrief:
    """Strict experiment brief required before any VLM experiment (spec section 34).

    Must document: failure type, baseline performance, why deterministic fails,
    expected VLM capability, input scene, structured output, success metric, cost metric.
    """

    brief_id: str
    failure_type: str  # Which F-code this experiment targets
    query_type: VLMQueryType
    baseline_performance: str  # Current deterministic performance
    why_deterministic_fails: str  # Specific limitation
    expected_vlm_capability: str  # What VLM should add
    input_description: str  # What the scene renders
    output_schema: dict  # JSON schema for structured output
    success_metric: str  # How to measure success
    cost_metric: str  # How to measure cost (tokens, latency)
    locked_test_subset: list[str] = field(default_factory=list)  # Case IDs


@dataclass
class VLMOutput:
    """Structured output from VLM (spec section 35).

    VLM may output: Entity Assertion, Spatial Relation, Candidate Preference,
    Include/Exclude Region, Road Semantic Judgment, Uncertainty.
    VLM must NOT output: final trusted polygon.
    """

    entity_assertion: Optional[str] = None  # Entity name or type
    spatial_relation: Optional[list[dict]] = None  # [{source, target, relation}]
    candidate_preference: Optional[str] = None  # Which candidate is preferred
    include_region: Optional[str] = None  # WKT region to include
    exclude_region: Optional[str] = None  # WKT region to exclude
    road_semantic_judgment: Optional[list[dict]] = None  # [{road, is_boundary, reason}]
    uncertainty: Optional[float] = None  # 0.0-1.0

    _raw_text: str = ""  # Raw VLM response for debugging


# ── Prompt Builder ────────────────────────────────────────────────────────────


class VLMPromptBuilder:
    """Builds structured prompts for VLM from scene renderings.

    Each prompt includes:
    1. Scene description (from SVG or structured data)
    2. Task specification
    3. Output format (JSON schema)
    4. Constraints (no final polygon, must cite evidence)
    """

    SYSTEM_PROMPT = (
        "You are a spatial reasoning assistant analyzing maps and satellite scenes. "
        "Your task is to provide structured semantic judgments about the scene. "
        "You must:\n"
        "1. Only state what you can observe in the provided scene\n"
        "2. Cite specific visual evidence for each judgment\n"
        "3. Report uncertainty when the scene is ambiguous\n"
        "4. NEVER output a final trusted polygon geometry\n"
        "5. NEVER invent data not present in the scene\n"
        "Output your response as a valid JSON object matching the requested schema."
    )

    @classmethod
    def build_road_semantic_prompt(
        cls, scene_svg: str, entity_name: str
    ) -> list[dict]:
        """Build a prompt asking VLM to classify road semantics.

        Question: Is each road a boundary or internal to the compound?
        """
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyze this scene of '{entity_name}'.\n\n"
                    "For each road visible in the scene, determine:\n"
                    "1. Is this road a BOUNDARY road (separating the compound from outside)?\n"
                    "2. Is this road an INTERNAL road (inside the compound)?\n"
                    "3. Is this road UNRELATED (passing through but not relevant)?\n\n"
                    "Output JSON:\n"
                    "{\n"
                    '  "roads": [\n'
                    "    {\n"
                    '      "description": "road location/color",\n'
                    '      "classification": "BOUNDARY|INTERNAL|UNRELATED",\n'
                    '      "confidence": 0.0-1.0,\n'
                    '      "evidence": "what you see"\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    f"Scene:\n{scene_svg[:3000]}"
                ),
            },
        ]

    @classmethod
    def build_building_grouping_prompt(
        cls, scene_svg: str, entity_name: str
    ) -> list[dict]:
        """Ask VLM to group buildings into logical clusters."""
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyze this scene of '{entity_name}'.\n\n"
                    "Group the visible buildings into logical clusters:\n"
                    "1. Which buildings clearly belong to the same compound?\n"
                    "2. Which buildings are separated by roads or other barriers?\n"
                    "3. Are there different building clusters that might be different phases?\n\n"
                    "Output JSON:\n"
                    "{\n"
                    '  "building_clusters": [\n'
                    "    {\n"
                    '      "cluster_id": 1,\n'
                    '      "building_count": 5,\n'
                    '      "description": "location/pattern",\n'
                    '      "likely_phase": "description or null",\n'
                    '      "confidence": 0.0-1.0\n'
                    "    }\n"
                    "  ],\n"
                    '  "separated_by_road": true|false,\n'
                    '  "evidence": "what you see"\n'
                    "}\n\n"
                    f"Scene:\n{scene_svg[:3000]}"
                ),
            },
        ]

    @classmethod
    def build_candidate_comparison_prompt(
        cls, scene_svg: str, entity_name: str,
        candidate_labels: list[str],
    ) -> list[dict]:
        """Ask VLM to compare candidate boundaries."""
        labels_str = ", ".join(candidate_labels)
        return [
            {"role": "system", "content": cls.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Analyze this scene of '{entity_name}'.\n\n"
                    f"Compare the candidate boundaries: {labels_str}\n"
                    "For each candidate:\n"
                    "1. Does it follow visible roads?\n"
                    "2. Does it enclose the visible buildings?\n"
                    "3. Does it exclude non-residential areas?\n"
                    "4. How natural/plausible does the boundary look?\n\n"
                    "Output JSON:\n"
                    "{\n"
                    '  "candidates": [\n'
                    "    {\n"
                    '      "label": "candidate name",\n'
                    '      "road_alignment": 0.0-1.0,\n'
                    '      "building_enclosure": 0.0-1.0,\n'
                    '      "excludes_contamination": true|false,\n'
                    '      "plausibility": 0.0-1.0,\n'
                    '      "evidence": "what you see"\n'
                    "    }\n"
                    "  ],\n"
                    '  "preferred": "candidate label or null",\n'
                    '  "uncertainty": 0.0-1.0\n'
                    "}\n\n"
                    f"Scene:\n{scene_svg[:3000]}"
                ),
            },
        ]


# ── Output Parser ──────────────────────────────────────────────────────────────


class VLMOutputParser:
    """Parses structured output from VLM responses.

    Handles: JSON extraction, validation against schema, fallback for malformed responses.
    """

    @staticmethod
    def parse_json(text: str) -> Optional[dict]:
        """Extract JSON from VLM response text.

        Handles markdown code blocks, leading/trailing text, and malformed JSON.
        """
        import json
        import re

        # Try direct parse
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def parse_road_semantic(text: str) -> VLMOutput:
        parsed = VLMOutputParser.parse_json(text)
        if not parsed:
            return VLMOutput(_raw_text=text)

        roads = parsed.get("roads", [])
        return VLMOutput(
            road_semantic_judgment=roads,
            uncertainty=parsed.get("uncertainty"),
            _raw_text=text,
        )

    @staticmethod
    def parse_candidate_comparison(text: str) -> VLMOutput:
        parsed = VLMOutputParser.parse_json(text)
        if not parsed:
            return VLMOutput(_raw_text=text)

        candidates = parsed.get("candidates", [])
        preferred = parsed.get("preferred")
        return VLMOutput(
            candidate_preference=preferred,
            road_semantic_judgment=[
                {
                    "description": c.get("label", ""),
                    "classification": "BOUNDARY" if c.get("road_alignment", 0) > 0.5 else "INTERNAL",
                    "confidence": c.get("road_alignment", 0),
                    "evidence": c.get("evidence", ""),
                }
                for c in candidates
            ],
            uncertainty=parsed.get("uncertainty"),
            _raw_text=text,
        )


# ── Evaluation Harness ─────────────────────────────────────────────────────────


@dataclass
class VLMEvaluationResult:
    """Result of comparing VLM vs deterministic baseline on a test case."""

    case_id: str
    query_type: VLMQueryType
    vlm_output: VLMOutput
    baseline_accuracy: float  # Deterministic baseline accuracy on this case
    vlm_accuracy: Optional[float] = None  # VLM accuracy (requires gold label)
    vlm_agreement: Optional[float] = None  # VLM vs baseline agreement
    vlm_cost_tokens: int = 0
    vlm_latency_ms: float = 0.0


class VLMEvaluationHarness:
    """Harness for evaluating VLM vs deterministic baselines.

    Must use a locked test subset (spec section 34.1).
    Compares without-VLM vs with-VLM on identical cases.
    """

    def __init__(self, locked_test_subset: list[str]):
        self._locked = locked_test_subset
        self._results: list[VLMEvaluationResult] = []

    @property
    def locked_cases(self) -> list[str]:
        return list(self._locked)

    def record(
        self,
        case_id: str,
        query_type: VLMQueryType,
        vlm_output: VLMOutput,
        baseline_accuracy: float,
        gold_accuracy: Optional[float] = None,
        cost_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> VLMEvaluationResult:
        if case_id not in self._locked:
            raise ValueError(
                f"Case {case_id} not in locked test subset. "
                f"Locked: {self._locked}"
            )

        result = VLMEvaluationResult(
            case_id=case_id,
            query_type=query_type,
            vlm_output=vlm_output,
            baseline_accuracy=baseline_accuracy,
            vlm_accuracy=gold_accuracy,
            vlm_cost_tokens=cost_tokens,
            vlm_latency_ms=latency_ms,
        )
        self._results.append(result)
        return result

    def summary(self) -> dict:
        if not self._results:
            return {"error": "no results"}

        baseline_accs = [r.baseline_accuracy for r in self._results]
        vlm_accs = [r.vlm_accuracy for r in self._results if r.vlm_accuracy is not None]
        costs = [r.vlm_cost_tokens for r in self._results]

        return {
            "n_cases": len(self._results),
            "baseline_mean_accuracy": sum(baseline_accs) / len(baseline_accs),
            "vlm_mean_accuracy": sum(vlm_accs) / len(vlm_accs) if vlm_accs else None,
            "vlm_improvement": (
                sum(vlm_accs) / len(vlm_accs) - sum(baseline_accs) / len(baseline_accs)
                if vlm_accs else None
            ),
            "mean_cost_tokens": sum(costs) / len(costs) if costs else 0,
        }