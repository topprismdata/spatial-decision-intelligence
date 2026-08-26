"""P1-04 VLM Vector Reasoning tests."""

from src.vlm import (
    VLMQueryType,
    VLMOutput,
    VLMPromptBuilder,
    VLMOutputParser,
    VLMEvaluationHarness,
)


class TestVLMOutput:
    def test_create(self):
        o = VLMOutput(
            road_semantic_judgment=[{"road": "Main St", "classification": "BOUNDARY"}],
            uncertainty=0.2,
        )
        assert o.road_semantic_judgment[0]["road"] == "Main St"
        assert o.uncertainty == 0.2

    def test_no_final_polygon(self):
        """VLM must NOT output a final trusted polygon."""
        o = VLMOutput(entity_assertion="Compound A")
        # No geometry field should exist
        assert not hasattr(o, "final_polygon")


class TestVLMPromptBuilder:
    def test_road_semantic_prompt(self):
        msgs = VLMPromptBuilder.build_road_semantic_prompt(
            "<svg>test</svg>", "Test Compound"
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert "BOUNDARY" in msgs[1]["content"]
        assert "Test Compound" in msgs[1]["content"]

    def test_building_grouping_prompt(self):
        msgs = VLMPromptBuilder.build_building_grouping_prompt(
            "<svg>test</svg>", "Test Compound"
        )
        assert "building_clusters" in msgs[1]["content"]

    def test_candidate_comparison_prompt(self):
        msgs = VLMPromptBuilder.build_candidate_comparison_prompt(
            "<svg>test</svg>", "Test", ["A", "B", "C"]
        )
        assert "A, B, C" in msgs[1]["content"]
        assert "road_alignment" in msgs[1]["content"]


class TestVLMOutputParser:
    def test_parse_json_direct(self):
        result = VLMOutputParser.parse_json('{"roads": [{"classification": "BOUNDARY"}]}')
        assert result is not None
        assert result["roads"][0]["classification"] == "BOUNDARY"

    def test_parse_json_markdown(self):
        text = '```json\n{"roads": [{"classification": "BOUNDARY"}]}\n```'
        result = VLMOutputParser.parse_json(text)
        assert result is not None

    def test_parse_json_embedded(self):
        text = 'Here is my analysis: {"roads": [{"classification": "BOUNDARY"}]} END'
        result = VLMOutputParser.parse_json(text)
        assert result is not None

    def test_parse_road_semantic(self):
        text = '{"roads": [{"description": "Main St", "classification": "BOUNDARY", "confidence": 0.9, "evidence": "follows compound edge"}]}'
        output = VLMOutputParser.parse_road_semantic(text)
        assert output.road_semantic_judgment is not None
        assert len(output.road_semantic_judgment) == 1
        assert output.road_semantic_judgment[0]["classification"] == "BOUNDARY"

    def test_parse_candidate_comparison(self):
        text = '{"candidates": [{"label": "A", "road_alignment": 0.9, "building_enclosure": 0.8, "excludes_contamination": true, "plausibility": 0.85, "evidence": "follows road"}], "preferred": "A", "uncertainty": 0.2}'
        output = VLMOutputParser.parse_candidate_comparison(text)
        assert output.candidate_preference == "A"
        assert output.uncertainty == 0.2


class TestVLMEvaluationHarness:
    def test_locked_subset(self):
        harness = VLMEvaluationHarness(["case-1", "case-2"])
        assert harness.locked_cases == ["case-1", "case-2"]

    def test_record_valid(self):
        harness = VLMEvaluationHarness(["case-1"])
        result = harness.record(
            case_id="case-1",
            query_type=VLMQueryType.ROAD_SEMANTIC,
            vlm_output=VLMOutput(),
            baseline_accuracy=0.75,
            gold_accuracy=0.85,
        )
        assert result.baseline_accuracy == 0.75
        assert result.vlm_accuracy == 0.85

    def test_record_invalid_case(self):
        harness = VLMEvaluationHarness(["case-1"])
        try:
            harness.record(
                case_id="case-999",
                query_type=VLMQueryType.ROAD_SEMANTIC,
                vlm_output=VLMOutput(),
                baseline_accuracy=0.75,
            )
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_summary(self):
        harness = VLMEvaluationHarness(["case-1", "case-2"])
        harness.record("case-1", VLMQueryType.ROAD_SEMANTIC, VLMOutput(), 0.70, gold_accuracy=0.85, cost_tokens=500)
        harness.record("case-2", VLMQueryType.ROAD_SEMANTIC, VLMOutput(), 0.80, gold_accuracy=0.90, cost_tokens=600)
        s = harness.summary()
        assert s["n_cases"] == 2
        assert s["baseline_mean_accuracy"] == 0.75
        assert s["vlm_mean_accuracy"] == 0.875
        assert s["vlm_improvement"] == 0.125
        assert s["mean_cost_tokens"] == 550.0