"""B8-V: VLMRoadInterpreter. Uses VLM for structured road semantic judgment.

Outputs RoadSemanticAssertion. No polygon generation.
Minimal experimental vector rasterizer for VLM visual input.
"""

from __future__ import annotations

import json
from typing import Optional

from src.road_semantics import (
    CompoundSplitSupport,
    Producer,
    RoadContinuity,
    RoadRole,
    RoadSemanticAssertion,
    VLMExperimentManifest,
)


VLM_SYSTEM_PROMPT = """You are a road semantic analysis assistant. Analyze the road network in the scene.

For each road segment, determine:
1. ROAD_ROLE: Is this a PUBLIC_SEPARATOR (public city road strongly separating areas), INTERNAL_ACCESS (internal compound road), WEAK_SEPARATOR (service road, fire lane, ambiguous boundary), or AMBIGUOUS?
2. CONTINUITY: Does the road go THROUGH the area, TERMINATE within it, or is it LOCAL?
3. COMPOUND_SPLIT: Does the road SUPPORT splitting the two sides into separate compounds, AGAINST splitting, or is it UNKNOWN?

Output JSON:
{"road_segments": [{"segment_id": "road_1", "road_role": "PUBLIC_SEPARATOR", "continuity": "THROUGH", "compound_split_support": "SUPPORT", "confidence": 0.9}]}
"""


class VLMRoadInterpreter:
    """VLM-based road semantic interpreter.

    Uses structured prompt + JSON output parsing.
    For production, would use an actual VLM API call.
    """

    def __init__(self):
        self.manifest = VLMExperimentManifest(
            model_name="gpt-4o",
            model_version="2026-08",
            prompt_version="1.0",
            system_prompt_hash="abc123",
            input_schema="scene_svg+road_labels",
            visual_input_spec="800x800 SVG with roads, buildings, candidate boundaries",
            context_window=128000,
            temperature=0.0,
            top_p=1.0,
            seed=42,
            max_tokens=1024,
            retry_policy="retry_once_on_parse_error",
            structured_output_schema='{"road_segments": [{"segment_id": "str", "road_role": "str", "continuity": "str", "compound_split_support": "str", "confidence": "float"}]}',
            inference_runtime="mock",
        )

    def interpret(self, scene_svg: str, road_labels: list[str]) -> list[RoadSemanticAssertion]:
        """Interpret road semantics from scene.

        In a real experiment, this would call the VLM API with the scene SVG.
        Here we parse the structured output.
        """
        # Simulate VLM response parsing
        try:
            # Attempt to parse structured JSON from VLM response
            response = self._call_vlm(scene_svg, road_labels)
            return self._parse_response(response, road_labels)
        except Exception:
            # Fallback: return ambiguous for all roads
            return [RoadSemanticAssertion(
                road_segment_id=r,
                road_role="AMBIGUOUS",
                continuity="LOCAL",
                compound_split_support="UNKNOWN",
                producer=Producer.VLM,
            ) for r in road_labels]

    def _call_vlm(self, scene_svg: str, road_labels: list[str]) -> str:
        """Simulated VLM call. In production, would call actual VLM API."""
        # This is a mock; in real experiment, replace with actual API call
        mock_response = json.dumps({
            "road_segments": [
                {
                    "segment_id": label,
                    "road_role": "PUBLIC_SEPARATOR",
                    "continuity": "THROUGH",
                    "compound_split_support": "SUPPORT",
                    "confidence": 0.85,
                }
                for label in road_labels[:3]
            ]
        })
        return mock_response

    @staticmethod
    def _parse_response(response: str, road_labels: list[str]) -> list[RoadSemanticAssertion]:
        """Parse VLM JSON response into RoadSemanticAssertion list."""
        data = json.loads(response)
        segments = data.get("road_segments", [])
        assertions = []
        role_map = {
            "PUBLIC_SEPARATOR": RoadRole.PUBLIC_SEPARATOR,
            "INTERNAL_ACCESS": RoadRole.INTERNAL_ACCESS,
            "WEAK_SEPARATOR": RoadRole.WEAK_SEPARATOR,
            "AMBIGUOUS": RoadRole.AMBIGUOUS,
        }
        cont_map = {
            "THROUGH": RoadContinuity.THROUGH,
            "TERMINATING": RoadContinuity.TERMINATING,
            "LOCAL": RoadContinuity.LOCAL,
        }
        split_map = {
            "SUPPORT": CompoundSplitSupport.SUPPORT,
            "AGAINST": CompoundSplitSupport.AGAINST,
            "UNKNOWN": CompoundSplitSupport.UNKNOWN,
        }
        for seg in segments:
            sid = seg.get("segment_id", "")
            role = role_map.get(seg.get("road_role", ""), RoadRole.AMBIGUOUS)
            cont = cont_map.get(seg.get("continuity", ""), RoadContinuity.LOCAL)
            split = split_map.get(seg.get("compound_split_support", ""), CompoundSplitSupport.UNKNOWN)
            confidence = seg.get("confidence", 0.5)
            assertions.append(RoadSemanticAssertion(
                road_segment_id=sid,
                road_role=role,
                continuity=cont,
                compound_split_support=split,
                evidence_features={"vlm_confidence": confidence},
                producer=Producer.VLM,
            ))
        return assertions