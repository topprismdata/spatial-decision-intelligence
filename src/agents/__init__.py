"""
Spatial Intelligence Agent Platform (4-Agent Layer).
Exports:
  * EntityResolutionAgent (Agent 1)
  * BoundaryReasoningAgent (Agent 2)
  * GeometryGenerationAgent (Agent 3)
  * GeometryQAAgent (Agent 4)
  * SpatialIntelligencePlatform (Orchestrator)
"""

from src.agents.entity_resolution_agent import EntityResolutionAgent, ResolvedEntityContext
from src.agents.boundary_reasoning_agent import BoundaryReasoningAgent, BoundaryConstraints
from src.agents.geometry_generation_agent import GeometryGenerationAgent, GeometryGenerationResult
from src.agents.geometry_qa_agent import GeometryQAAgent, QAAuditResult
from src.agents.orchestrator import SpatialIntelligencePlatform

__all__ = [
    "EntityResolutionAgent",
    "ResolvedEntityContext",
    "BoundaryReasoningAgent",
    "BoundaryConstraints",
    "GeometryGenerationAgent",
    "GeometryGenerationResult",
    "GeometryQAAgent",
    "QAAuditResult",
    "SpatialIntelligencePlatform",
]
