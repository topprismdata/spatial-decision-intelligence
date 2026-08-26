"""R8 RoadSemanticAssertion: common contract for B8-D and B8-V.

Both interpreters output the same schema, consumed by the same Ranking Adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RoadRole(str, Enum):
    PUBLIC_SEPARATOR = "PUBLIC_SEPARATOR"  # 公共城市道路构成强分隔
    INTERNAL_ACCESS = "INTERNAL_ACCESS"    # 小区内部道路
    WEAK_SEPARATOR = "WEAK_SEPARATOR"      # 服务道路/消防通道/模糊边界
    AMBIGUOUS = "AMBIGUOUS"                # 无法判断


class RoadContinuity(str, Enum):
    THROUGH = "THROUGH"          # 贯穿整片区域
    TERMINATING = "TERMINATING"  # 在区域内终止
    LOCAL = "LOCAL"              # 局部短连接


class CompoundSplitSupport(str, Enum):
    SUPPORT = "SUPPORT"          # 支持将两侧分为不同 Compound
    AGAINST = "AGAINST"          # 不支持分割
    UNKNOWN = "UNKNOWN"          # 证据不足


class Producer(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"  # B8-D
    VLM = "VLM"                      # B8-V


@dataclass(frozen=True)
class RoadSemanticAssertion:
    road_segment_id: str = ""
    road_role: RoadRole = RoadRole.AMBIGUOUS
    continuity: RoadContinuity = RoadContinuity.LOCAL
    compound_split_support: CompoundSplitSupport = CompoundSplitSupport.UNKNOWN
    evidence_features: dict[str, float] = field(default_factory=dict)
    producer: Producer = Producer.DETERMINISTIC


@dataclass(frozen=True)
class VLMExperimentManifest:
    model_name: str = ""
    model_version: str = ""
    prompt_version: str = ""
    system_prompt_hash: str = ""
    input_schema: str = ""
    visual_input_spec: str = ""
    context_window: int = 0
    temperature: float = 0.0
    top_p: float = 0.0
    seed: int = 42
    max_tokens: int = 0
    retry_policy: str = ""
    structured_output_schema: str = ""
    inference_runtime: str = ""