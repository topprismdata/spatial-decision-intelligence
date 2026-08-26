"""P0-04 Observation Adapter Contract: Base adapter and registry.

All data sources must enter the system through Observations.
No Source Adapter may directly create TRUSTED Entity Geometry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from src.domain.contracts import Observation


@dataclass(frozen=True)
class SourceManifest:
    """P0-09 Source Manifest: traceable provenance for every data source.

    All benchmark data must be traceable.
    License is dataset-release metadata, not an adapter constant.
    For multi-theme sources (e.g. Overture), each theme has its own manifest.
    """
    source: str
    dataset: str = ""
    theme: str = ""
    release: str = ""
    source_attribution: str = ""
    license: str = ""
    license_version: str = ""
    license_url: str = ""
    url: str = ""
    query: str = ""
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    record_count: int = 0


class ObservationAdapter(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> Sequence[Observation]:
        ...
    @abstractmethod
    def manifest(self) -> SourceManifest:
        ...


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, ObservationAdapter] = {}
    def register(self, name: str, adapter: ObservationAdapter) -> None:
        self._adapters[name] = adapter
    def get(self, name: str) -> ObservationAdapter:
        return self._adapters[name]
    def all(self) -> dict[str, ObservationAdapter]:
        return dict(self._adapters)
    def all_manifests(self) -> list[SourceManifest]:
        return [a.manifest() for a in self._adapters.values()]