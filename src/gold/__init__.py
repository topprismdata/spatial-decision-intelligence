"""R5 Gold Adjudication: Source Manifest, Gold Assertion, Entity/Boundary Gold State.

G1–G8 Protocol, EvidenceBundle, GoldReviewConflict, GoldCaseVersion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class GoldState(str, Enum):
    GOLD_RESOLVED = "GOLD_RESOLVED"
    GOLD_PARTIAL = "GOLD_PARTIAL"
    GOLD_UNRESOLVED = "GOLD_UNRESOLVED"


class EvidenceSufficiency(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class SegmentStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    SUPPORTED = "SUPPORTED"
    UNCERTAIN = "UNCERTAIN"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTED = "CONFLICTED"


class BuildingMembershipState(str, Enum):
    MEMBER = "MEMBER"
    NON_MEMBER = "NON_MEMBER"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class DependencyType(str, Enum):
    INDEPENDENT = "INDEPENDENT"
    PARTIALLY_DEPENDENT = "PARTIALLY_DEPENDENT"
    DERIVED = "DERIVED"
    UNKNOWN = "UNKNOWN"


class SourceFamily(str, Enum):
    OPEN_MAP = "OPEN_MAP"
    OPEN_BUILDING = "OPEN_BUILDING"
    OPEN_PLACE = "OPEN_PLACE"
    PUBLIC_GOV_RECORD = "PUBLIC_GOV_RECORD"
    PUBLIC_WEB_RECORD = "PUBLIC_WEB_RECORD"
    OPEN_EO = "OPEN_EO"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class SourceSemanticRole(str, Enum):
    RESIDENTIAL_LANDUSE = "RESIDENTIAL_LANDUSE"
    KNOWN_RESIDENTIAL_BOUNDARY = "KNOWN_RESIDENTIAL_BOUNDARY"
    PROPERTY_MANAGEMENT_AREA = "PROPERTY_MANAGEMENT_AREA"
    BUILDING_FOOTPRINT = "BUILDING_FOOTPRINT"
    ROAD = "ROAD"
    PLACE_POINT = "PLACE_POINT"
    PARCEL = "PARCEL"
    ADMINISTRATIVE_AREA = "ADMINISTRATIVE_AREA"
    OTHER = "OTHER"


class AuthorityScope(str, Enum):
    OFFICIAL_NAME = "OFFICIAL_NAME"
    ADDRESS = "ADDRESS"
    ADMINISTRATIVE_MEMBERSHIP = "ADMINISTRATIVE_MEMBERSHIP"
    PROPERTY_MANAGEMENT = "PROPERTY_MANAGEMENT"
    PLANNING = "PLANNING"
    OTHER_REGULATORY = "OTHER_REGULATORY"


class CueType(str, Enum):
    ROAD = "ROAD"
    BUILDING = "BUILDING"
    WALL = "WALL"
    FENCE = "FENCE"
    WATER = "WATER"
    BARRIER = "BARRIER"
    VEGETATION = "VEGETATION"
    OPEN_POLYGON = "OPEN_POLYGON"
    SEMANTIC_NAME = "SEMANTIC_NAME"
    OTHER = "OTHER"