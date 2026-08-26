# M0: Existing Repository Baseline Classification

**Date:** 2026-08-26
**Method:** Read-only analysis of all 26 Python source files under `src/`
**Purpose:** Classify all existing assets into KEEP / REFACTOR / EXPERIMENTAL per spec categories before any changes

---

## 1. File-by-File Analysis

### 1.1 `src/domain/models.py` — Core Domain Models (v1)

**Capabilities:** Defines the foundational data model for the platform:
- Enums: `EntityType` (6 residential/commercial types), `CoordinateStatus` (8 states), `RelationType` (12 relation types), `GeometrySourceType` (8 sources), `QADomain` (5 domains)
- Dataclasses: `SourceRecord` (frozen/immutable), `CoordinateAssessment`, `GeometryVersion`, `CanonicalEntity`, `EntityRelation`, `QAResult`

**Key classes/functions:**
- `SourceRecord` — immutable input record, never mutated
- `CanonicalEntity` — canonical identity with versioned geometry
- `EntityRelation` — typed relation between records with explain codes
- `QAResult` — quality assessment with score, issues, decision

**Design patterns:** Data-Model-First, Immutable Source Records, Enum-based closed schemas, Dataclass composition

**Spec categories:** `SpatialEntity` (partial — CanonicalEntity is the v1 precursor), `ValidationStatus` (absent — not in this file), `QualityFinding` (absent — v1 uses QAResult instead)

**Classification: KEEP** — Core domain types are foundational and functional. However, note that `world_model.py` introduces a parallel/overlapping set of dataclasses (SpatialEntity, QualityFinding, etc.) — this is intentional layering: `models.py` holds the v1 batch-processing data model, while `world_model.py` holds the v2 World Model Integrity Layer.

---

### 1.2 `src/domain/world_model.py` — World Model Integrity Layer

**Capabilities:** Defines the v2 spatial world model data contracts:
- Enums: `EntityCategory` (8 categories), `ValidationStatus` (5 states), `FindingSeverity` (CRITICAL/WARNING/INFO)
- Dataclasses: `EvidencePacket`, `DecisionImpact`, `QualityFinding`, `GeometryObservation`, `SpatialRelation`, `ReviewDisposition`, `SpatialEntity`, `TrustedSpatialState`

**Key classes/functions:**
- `TrustedSpatialState` — aggregate: entities, geometries, relations, findings, dispositions. Has `get_decision_ready_entities(consumer_name)` and `summary_stats()`
- `QualityFinding` — linked to `EvidencePacket` + `DecisionImpact`
- `SpatialEntity` — first-class entity with `is_decision_ready` flag
- `GeometryObservation` — geometric boundary with `ValidationStatus`
- `SpatialRelation` — verified relation with IoU, distance, semantic similarity, cross-encoder score
- `ReviewDisposition` — human-in-the-loop action record

**Design patterns:** Aggregate Root (TrustedSpatialState), Consumer-aware gating, Immutable records, Separation of findings from entities

**Spec categories covered:** `SpatialEntity`, `GeometryObservation`, `SpatialRelation`, `ValidationStatus`, `QualityFinding`, `DecisionImpact`, `ReviewDisposition`, `Fail-Closed` (via `get_decision_ready_entities`)

**Classification: KEEP** — Clean, well-designed v2 domain model. The only file that fully implements the spec categories `SpatialEntity`, `GeometryObservation`, `SpatialRelation`, `ValidationStatus`, `QualityFinding`, `DecisionImpact`, `ReviewDisposition`.

---

### 1.3 `src/coordinate/assessment.py` — Coordinate Intelligence

**Capabilities:**
- `CoordinateIntelligence.assess_and_normalize(record)` — detects CRS of point vs polygon, normalizes to WGS84
- Handles 5 cases: missing/zero point (reconstruct from polygon), point=WGS84 vs polygon=GCJ02 conflict, mixed CRS, confirmed WGS84, CRS unknown
- Returns `CoordinateAssessment` + normalized coordinates + WKT

**Key classes/functions:**
- `CoordinateIntelligence` — static method `assess_and_normalize()`

**Design patterns:** Strategy pattern (single static method), Defensive diagnostics, Explicit uncertainty reporting

**Spec categories covered:** `Coordinate Alignment` (primary)

**Classification: KEEP** — Core coordinate intelligence is well-implemented and validated against real data. The WGS84/GCJ02 detection heuristic (offset ~0.006/0.001) is empirically validated.

---

### 1.4 `src/coordinate/transforms.py` — Coordinate Transformations

**Capabilities:**
- WGS84 ↔ GCJ02 (Mars) transformations using standard math
- BD09 ↔ GCJ02 transformations
- `transform_geometry_wkt()` — vertex-by-vertex WKT polygon transformation
- `out_of_china()` — fast bypass for non-Chinese coordinates

**Key functions:** `wgs84_to_gcj02`, `gcj02_to_wgs84`, `bd09_to_gcj02`, `bd09_to_wgs84`, `transform_geometry_wkt`

**Design patterns:** Pure functions, No external dependencies beyond math, Industry-standard GCJ02 algorithm

**Spec categories covered:** `Coordinate Alignment` (supporting)

**Classification: KEEP** — Standard, proven implementation of Chinese coordinate transformations. No changes needed.

---

### 1.5 `src/geometry/validation.py` — Geometry QA Engine

**Capabilities:**
- `GeometryQAEngine.validate_and_extract_features()` — validates WKT polygons, performs topological healing, extracts 15+ geometric features
- Handles: empty geometry, unparseable WKT, self-intersection (auto-heal via `make_valid`), GeometryCollection extraction
- Feature extraction: area (deg² and m²), perimeter, vertex count, hole count, compactness (Polsby-Popper), convexity, aspect ratio, rect_length/width, mean_width, max_width (via MaximumInscribedCircle)
- Scoring rules: sliver detection (<500m²), oversized (>1.5M m²), narrow strip, jagged boundary, elongated block, low compactness
- Returns `QAResult` with score, issues, decision (PASS/WARN/REVIEW)

**Key classes/functions:**
- `GeometryQAEngine` — static method `validate_and_extract_features()`

**Design patterns:** Deterministic rule engine, Auto-healing with graceful degradation, Empirically validated thresholds (9,039 fences)

**Spec categories covered:** `Geometry QA` (primary)

**Classification: KEEP** — Comprehensive, well-engineered geometry validation. All thresholds are empirically validated against 9,039 fences. Rich feature extraction.

---

### 1.6 `src/geometry/ai_fence_guard.py` — AI Fence Guard

**Capabilities:**
- `AIFenceGuard.inspect_and_guard()` — evaluates AI-generated candidate polygons through QA, area, topology, POI proximity checks
- `_trigger_fallback()` — degrades to Route-A fallback or REJECTED_UNRECOVERABLE
- `FenceGuardDecision` — status (PASSED/HEALED/DEGRADED_FALLBACK/REJECTED_UNRECOVERABLE), method used, reasons

**Key classes:**
- `AIFenceGuard` — defensive quality gate
- `FenceGuardDecision` — result dataclass

**Design patterns:** Fail-Closed, Graceful degradation, Defensive gate, Dogfooding (uses GeometryQAEngine internally)

**Spec categories covered:** `Fail-Closed` (gate behavior), `Geometry QA` (dogfooding)

**Classification: KEEP** — Critical defensive component. The fail-closed + fallback chain is the main Fail-Closed enforcement mechanism for AI-generated geometries.

---

### 1.7 `src/agents/entity_resolution_agent.py` — Agent 1

**Capabilities:**
- `EntityResolutionAgent.resolve()` — parses unstructured community names/addresses into typed components
- Extracts phase, subarea, courtyard from name/address
- Classifies entity category (RESIDENTIAL_COMMUNITY, RESIDENTIAL_COURTYARD, RESIDENTIAL_DORMITORY, MIXED_COMMERCIAL_RESIDENTIAL)
- Determines scale level (COURTYARD_LEVEL, COMMUNITY_LEVEL, LARGE_ESTATE)
- Builds canonical name from components + aliases

**Key classes:**
- `EntityResolutionAgent` — regex-based entity parser
- `ResolvedEntityContext` — structured semantic output

**Design patterns:** Semantic parsing, Pattern matching, Heuristic classification

**Spec categories covered:** `BoundaryReasoningAgent` (upstream input — provides entity context/scale for boundary reasoning)

**Classification: REFACTOR** — The resolution logic is functional but has overlap with the `entity_resolution/` module's `component_matcher.py` and `pair_features.py`. The `parse_chinese_community_semantics` in `pair_features.py` does similar entity classification. This agent duplicates some of that logic with simpler regexes. Should be refactored to reuse the component matcher infrastructure.

---

### 1.8 `src/agents/boundary_reasoning_agent.py` — Agent 2

**Capabilities:**
- `BoundaryReasoningAgent.reason_constraints()` — infers spatial search bounding box, area expectations, zoom level
- Uses statistical area priors from 9,039 operational fences (3 scale levels)
- Computes: target/min/max area, search radius, bounding box, zoom level
- Supports `prior_area_m2` override

**Key classes:**
- `BoundaryReasoningAgent`
- `BoundaryConstraints` — all spatial search parameters

**Design patterns:** Statistical prior model, Semantic-to-spatial mapping, Degree-to-meter conversion

**Spec categories covered:** `BoundaryReasoningAgent` (primary)

**Classification: KEEP** — Well-designed, empirically grounded (9,039 fences). The area priors and scale levels are the core of the boundary reasoning spec category.

---

### 1.9 `src/agents/geometry_generation_agent.py` — Agent 3

**Capabilities:**
- `GeometryGenerationAgent.generate()` — delegates to `CandidateFusionEngine`, returns top-scored hypothesis
- Wraps `CandidateFusionEngine` with a thin orchestration layer

**Key classes:**
- `GeometryGenerationAgent`
- `GeometryGenerationResult` — chosen hypothesis, all hypotheses, confidence, method

**Design patterns:** Facade pattern (wraps CandidateFusionEngine), Delegation

**Spec categories covered:** `CandidateFusion` (delegates to)

**Classification: KEEP** — Thin facade, but correctly separates concerns. The real complexity is in `candidate_fusion.py`.

---

### 1.10 `src/agents/geometry_qa_agent.py` — Agent 4

**Capabilities:**
- `GeometryQAAgent.audit()` — runs AIFenceGuard.inspect_and_guard() on the generated geometry
- Maps FenceGuardDecision status to ValidationStatus (VERIFIED_VALID, REPAIRED_AUTO, REJECTED)
- Creates `SpatialEntity`, `GeometryObservation`, `QualityFinding` with `EvidencePacket` and `DecisionImpact`
- Determines `is_decision_ready` flag

**Key classes:**
- `GeometryQAAgent`
- `QAAuditResult` — final audited output

**Design patterns:** Final quality gate, Fail-Closed, Finding construction with evidence

**Spec categories covered:** `SpatialEntity`, `GeometryObservation`, `QualityFinding`, `DecisionImpact`, `Fail-Closed`, `Geometry QA`

**Classification: KEEP** — Correctly bridges the AI generation pipeline to the v2 world model types. Properly constructs `QualityFinding` with `EvidencePacket` and `DecisionImpact`.

---

### 1.11 `src/agents/orchestrator.py` — Orchestrator

**Capabilities:**
- `SpatialIntelligencePlatform` — 4-agent sequential pipeline
- `generate_single_fence()` — full pipeline for one entity
- `batch_generate_and_govern()` — batch processing → `TrustedSpatialState`

**Key classes:**
- `SpatialIntelligencePlatform`
- `SpatialGenerationPipelineResult` — full trace

**Design patterns:** Pipeline orchestration, Sequential agent chain, Aggregate compilation

**Spec categories covered:** `SpatialEntity` (produces), `Fail-Closed` (via QA agent), `Geometry QA` (orchestrates)

**Classification: KEEP** — Clean orchestrator. The `batch_generate_and_govern()` correctly compiles into `TrustedSpatialState`.

---

### 1.12 `src/adapters/decision_adapters.py` — Decision Adapters

**Capabilities:**
- `TerritoryPlanningAdapter.compile(state)` — with Fail-Closed gates: critical finding check, geometric validity, area outlier (>2km² blocks)
- `VisitSchedulingAdapter.compile(state)` — with Fail-Closed gates: decision readiness, zero-coordinate rejection
- `CoverageAnalysisAdapter.compile(state)` — with deduplication gate: excludes SAME_ENTITY/POSSIBLE_MERGE_ERROR overlaps
- All adapters produce type-safe dataclass payloads

**Key classes:**
- `TerritoryPlanningAdapter` — consumer: "market-partition"
- `VisitSchedulingAdapter` — consumer: "visit-scheduling-optimizer"
- `CoverageAnalysisAdapter` — consumer: "coverage-analysis"
- `TerritoryPlanningRecord`, `VisitSchedulingRecord`, `CoverageCellRecord`

**Design patterns:** Fail-Closed gates, Consumer-aware gating, Type-safe payloads, Quarantine logging

**Spec categories covered:** `DecisionAdapter` (primary), `Fail-Closed` (primary — the enforcement layer)

**Classification: KEEP** — The primary implementation of the `DecisionAdapter` and `Fail-Closed` spec categories. Multiple consumer-aware gates with quarantine logging.

---

### 1.13 `src/entity_resolution/candidate_retrieval.py` — Candidate Retrieval

**Capabilities:**
- `CandidateRetrievalEngine.retrieve_candidate_pairs()` — spatial STRtree indexing + lexical blocking
- Groups by city, filters geometries, uses STRtree for spatial proximity
- Falls back to point buffering when geometry is absent
- Lexical blocking: name prefix matching (first 3 chars) within city

**Key classes:**
- `CandidateRetrievalEngine` — static method

**Design patterns:** Spatial indexing (STRtree), Blocking (lexical + spatial), City-level partitioning

**Spec categories covered:** `SpatialRelation` (upstream — produces candidate pairs for scoring)

**Classification: KEEP** — Standard entity resolution blocking technique. STRtree + lexical blocking is appropriate for recall.

---

### 1.14 `src/entity_resolution/embedding.py` — Embedding Service

**Capabilities:**
- `EmbeddingService` — singleton BGE embedding service (BAAI/bge-small-zh-v1.5 via fastembed/ONNX)
- `embed_records()` — L2-normalized vectors for name|address composite
- `cosine()` — single pair cosine similarity
- `cosine_bulk()` — vectorized batch cosine similarity

**Key classes:**
- `EmbeddingService` — class-level singleton

**Design patterns:** Singleton, Lazy loading, Cached vectors, ONNX inference

**Spec categories covered:** `SpatialRelation` (upstream — provides BGE similarity signal)

**Classification: KEEP** — Standard BGE bi-encoder implementation. The singleton caching is appropriate for batch processing.

---

### 1.15 `src/entity_resolution/component_matcher.py` — Component Matcher

**Capabilities:**
- `extract_components(name)` — decomposes Chinese community name into typed attributes (BASE, COURT, BUILDING, HOUSE, PHASE, SUBAREA, LANE, BLOCK, YARD, COMM_NUM)
- `component_similarity(a, b)` — per-attribute comparison with exact-match for discriminators
- `sibling_relation_for(conflict)` — maps discriminator conflict to sibling relation type
- `EntityComponents` — typed attribute vector
- `ComponentSimilarity` — per-attribute similarity with conflicts/matches
- Chinese numeral parsing (`_chinese_to_int`) with compound handling
- Token normalization (`_normalize_token`) — 甲2→A2, 十三→13, etc.

**Key classes:**
- `EntityComponents` — typed attribute representation
- `ComponentSimilarity` — per-attribute similarity
- `DiscriminatorType` — enum of 9 discriminator types

**Design patterns:** Attribute-level matching (DeepMatcher/Magellan), Closed schema of typed attributes, Exact-match for numeric/ordinal discriminators, Embedding-blindness-proof by construction

**Spec categories covered:** `ZeroSilentMerge` (primary — the core implementation)

**Classification: KEEP** — The root-cause fix for embedding-blindness to numeric suffixes. Implements the attribute-level matching paradigm from the entity resolution literature. The closed schema of 9 discriminator types is well-designed.

---

### 1.16 `src/entity_resolution/pair_features.py` — Pair Feature Extractor

**Capabilities:**
- `parse_chinese_community_semantics(record)` — full semantic analysis: entity type classification (6 residential/commercial/non-residential types), token extraction (court_no, house_no, phase, subarea), base name cleaning
- `PairFeatureExtractor.extract_features()` — 20+ features: semantic match flags, number conflicts, hierarchy flags, component-aware attribute similarity, spatial metrics (distance, IoU, intersection-over-min), district match

**Key classes:**
- `PairFeatureExtractor` — static method `extract_features()`
- `parse_chinese_community_semantics()` — standalone function

**Design patterns:** Feature engineering, Rule-based entity type classification, Component-aware matching (delegates to component_matcher)

**Spec categories covered:** `SpatialRelation` (upstream — provides features for scoring), `ZeroSilentMerge` (delegates to component_matcher)

**Classification: KEEP** — Rich feature extraction. The `parse_chinese_community_semantics` is a separate function from `EntityResolutionAgent.resolve()` — this is a duplication concern (see below).

**Note:** `parse_chinese_community_semantics()` in this file and `EntityResolutionAgent.resolve()` in `entity_resolution_agent.py` both parse entity names and classify entity types. They use different logic and produce overlapping but not identical results. This is a duplication risk.

---

### 1.17 `src/entity_resolution/pair_scorer.py` — Pair Scorer

**Capabilities:**
- `PairScorer.score_pair()` — hybrid scoring: component gate (hard) + BGE (residual)
- 7 decision rules: spatial separation (>2000m), structural gate (component conflict → sibling), hierarchical (whole-to-phase), true duplicate, spatial collision, same-name-different-district, general proximity
- Returns `EntityRelation` with type, probability, confidence, explain codes

**Key classes:**
- `PairScorer` — static method `score_pair()`

**Design patterns:** Hybrid scoring (component gate + BGE residual), Rule cascade with priority, Explainable decisions, Strict no-merge for conflicts

**Spec categories covered:** `SpatialRelation` (primary — produces typed relations), `ZeroSilentMerge` (primary — the structural gate is the enforcement)

**Classification: KEEP** — The core decision engine for entity resolution. The rule cascade is well-designed with clear priorities. The structural gate (Rule 1) is the `ZeroSilentMerge` enforcement.

---

### 1.18 `src/entity_resolution/cross_encoder_reranker.py` — Cross-Encoder Reranker

**Capabilities:**
- `CrossEncoderReranker` — wrapper around BAAI/bge-reranker-v2-m3
- `rerank_pairs()` — symmetric average of both directions
- FP16 on GPU/MPS, INT8 on CPU
- `release()` — frees model from memory
- `build_rerank_text()` — compact description for cross-encoder

**Key classes:**
- `CrossEncoderReranker`
- `RerankResult`

**Design patterns:** Bi-encoder recall + cross-encoder rerank (Ditto paradigm), Symmetric scoring, Memory isolation (separate process)

**Spec categories covered:** `SpatialRelation` (supports — re-scores RELATED_ENTITY pairs)

**Classification: KEEP** — Well-implemented cross-encoder wrapper. The design constraint (only operates on soft decision region, never overrides hard gates) is correct.

---

### 1.19 `src/entity_resolution/graph_resolver.py` — Graph Resolver

**Capabilities:**
- `GraphResolver.resolve_clusters()` — BFS connected components on EXACT_DUPLICATE + SAME_ENTITY_ALT_BOUNDARY relations
- Administrative consistency check (same city required for merge)
- Transitivity conflict detection (CITY_CONFLICT)

**Key classes:**
- `GraphResolver` — static method

**Design patterns:** Connected components (BFS), Transitivity validation, Administrative isolation

**Spec categories covered:** `SpatialEntity` (upstream — produces clusters for CanonicalBuilder)

**Classification: KEEP** — Simple, correct BFS graph resolution. The city-consistency check prevents cross-city false merges.

---

### 1.20 `src/entity_resolution/canonical_builder.py` — Canonical Builder

**Capabilities:**
- `CanonicalBuilder.build_canonical_entities()` — builds `CanonicalEntity` + `GeometryVersion` from clusters
- Selects best record by name length, best geometry by QA score
- Parses semantic attributes via `parse_chinese_community_semantics`

**Key classes:**
- `CanonicalBuilder` — static method

**Design patterns:** Builder pattern, Best-record selection, Multi-version geometry

**Spec categories covered:** `SpatialEntity` (v1 variant — produces CanonicalEntity, not v2 SpatialEntity)

**Classification: KEEP** — Produces the v1 `CanonicalEntity` model. Note: the v2 pipeline (agents/) produces `SpatialEntity` instead. This is the v1 batch pipeline's output builder.

---

### 1.21 `src/generation/candidate_fusion.py` — Candidate Fusion Engine

**Capabilities:**
- `CandidateFusionEngine.generate_candidates()` — generates 3 hypotheses: AREA_CALIBRATED_BUFFER, ROAD_ENCLOSED_BLOCK, BUILDING_CONCAVE_HULL
- `_build_hypothesis()` — computes area, compactness, spatial reasoning score (4 weighted factors: point containment, area alignment, shape compactness, method prior)
- Supports real road network / building footprints or simulated fallbacks

**Key classes:**
- `CandidateFusionEngine`
- `PolygonHypothesis` — hypothesis with sub-scores

**Design patterns:** Multi-hypothesis generation, Spatial reasoning scoring, Weighted fusion

**Spec categories covered:** `CandidateFusion` (primary)

**Classification: KEEP** — The core implementation of `CandidateFusion`. The 3-hypothesis generation + weighted scoring model is the centerpiece.

**Note:** The `CandidateFusionEngine` imports from `src.agents.entity_resolution_agent` and `src.agents.boundary_reasoning_agent`, creating a dependency from `generation/` upwards to `agents/`. This is a circular-package smell but not a cycle.

---

### 1.22 `src/ingestion/parser.py` — Excel Ingestion Parser

**Capabilities:**
- `ExcelIngestionParser.parse_file()` — reads Excel with specific column mapping
- Maps: 小区编码, 小区名称, 小区地址, 省份, 城市, 区, 街道, 经度, 纬度, 坐标面[内置], 面积[内置]
- Creates immutable `SourceRecord` objects

**Key classes:**
- `ExcelIngestionParser` — static method

**Design patterns:** Adapter pattern (external table → SourceRecord), Column mapping

**Classification: KEEP** — Simple, functional Excel parser. The column mapping is specific to the source data format.

---

### 1.23 `src/ingestion/profiler.py` — Dataset Profiler

**Capabilities:**
- `DatasetProfiler.profile()` — comprehensive health report:
  - Field completeness (name, address, point, geometry, admin null rates)
  - Geographic distribution (city, province counts)
  - Duplicate analysis (same name in city, same point, identical WKT)
  - Point-polygon offset statistics (mean, median, std for lng/lat)
  - Geometry validity (invalid, zero-area, vertex counts, area stats)
  - CRS detection (systematic offset detection)

**Key classes:**
- `DatasetProfiler` — static method

**Design patterns:** Data quality assessment, Statistical profiling, CRS heuristic detection

**Classification: KEEP** — Comprehensive data profiler. The systematic offset detection (checking ~0.006 lng offset) is aligned with the coordinate intelligence layer.

---

### 1.24 `src/pipelines/batch_pipeline.py` — Batch Pipeline

**Capabilities:**
- `BatchPipeline.run()` — end-to-end entity resolution pipeline:
  - Step 0: Ingestion + M0 Profiler
  - Step 1-2: Coordinate Intelligence + Geometry QA + Semantic Parsing
  - BGE dense embedding
  - Step 3: Candidate Retrieval (STRtree + lexical)
  - Step 4: Semantic Pair Scoring + Relation Classification
  - Step 4.5: Cross-Encoder Rerank (optional, separate process)
  - Step 5: Graph Resolver + Canonical Builder
  - Step 6: Export (canonical_entities.csv, entity_relations.csv, qa_issues_report.csv)

**Key classes:**
- `BatchPipeline` — orchestrates the full pipeline

**Design patterns:** Pipeline orchestration, Sequential stages, DataFrame export, Out-of-process rerank (memory isolation)

**Spec categories covered:** `SpatialEntity` (produces v1 CanonicalEntity), `SpatialRelation` (produces EntityRelation), `Coordinate Alignment`, `Geometry QA`

**Classification: KEEP** — Mature, well-engineered batch pipeline. The out-of-process rerank design is a pragmatic memory-management decision.

**Note:** This pipeline uses the v1 domain model (`CanonicalEntity`, `EntityRelation` from `models.py`), not the v2 model (`SpatialEntity`, `SpatialRelation` from `world_model.py`). The v2 pipeline is the `agents/` layer.

---

### 1.25 `src/pipelines/dataset_extractor.py` — Silver Dataset Extractor

**Capabilities:**
- `SilverDatasetExtractor.extract()` — filters high-quality (QA >= 0.80, area 1000-500000m², no narrow strip) fences for training
- Converts to GCJ-02 for Amap tile alignment
- Outputs: JSON (with GeoJSON) + CSV

**Key classes:**
- `SilverDatasetExtractor`

**Design patterns:** Weak supervision, Quality filtering, Training data extraction

**Classification: EXPERIMENTAL** — This is a training data extraction tool for downstream AI fence generation. It is not part of the core spatial MDM pipeline. Its purpose is to build a silver training dataset for the AI generation models (which are themselves experimental).

---

### 1.26 `src/cli.py` — CLI

**Capabilities:**
- `diagnose` — run full spatial world model diagnosis on Excel/GeoJSON
- `generate` — 4-agent generation pipeline for a single entity
- `inspect` — launch interactive case inspector

**Key classes:**
- `main()`, `diagnose_cmd()`, `generate_cmd()`, `inspect_cmd()`

**Classification: KEEP** — Functional CLI entrypoint. The `diagnose` command supports both Excel and GeoJSON input.

---

## 2. Classification Summary

| File | Classification | Primary Spec Categories |
|------|-------------|----------------------|
| `src/domain/models.py` | **KEEP** | SpatialEntity (v1), Coordinate Alignment |
| `src/domain/world_model.py` | **KEEP** | SpatialEntity, GeometryObservation, SpatialRelation, ValidationStatus, QualityFinding, DecisionImpact, ReviewDisposition, Fail-Closed |
| `src/coordinate/assessment.py` | **KEEP** | Coordinate Alignment |
| `src/coordinate/transforms.py` | **KEEP** | Coordinate Alignment |
| `src/geometry/validation.py` | **KEEP** | Geometry QA |
| `src/geometry/ai_fence_guard.py` | **KEEP** | Fail-Closed, Geometry QA |
| `src/agents/entity_resolution_agent.py` | **REFACTOR** | BoundaryReasoningAgent (upstream) |
| `src/agents/boundary_reasoning_agent.py` | **KEEP** | BoundaryReasoningAgent |
| `src/agents/geometry_generation_agent.py` | **KEEP** | CandidateFusion |
| `src/agents/geometry_qa_agent.py` | **KEEP** | SpatialEntity, GeometryObservation, QualityFinding, DecisionImpact, Fail-Closed, Geometry QA |
| `src/agents/orchestrator.py` | **KEEP** | SpatialEntity, Fail-Closed, Geometry QA |
| `src/adapters/decision_adapters.py` | **KEEP** | DecisionAdapter, Fail-Closed |
| `src/entity_resolution/candidate_retrieval.py` | **KEEP** | SpatialRelation (upstream) |
| `src/entity_resolution/embedding.py` | **KEEP** | SpatialRelation (upstream) |
| `src/entity_resolution/component_matcher.py` | **KEEP** | ZeroSilentMerge |
| `src/entity_resolution/pair_features.py` | **KEEP** | SpatialRelation, ZeroSilentMerge |
| `src/entity_resolution/pair_scorer.py` | **KEEP** | SpatialRelation, ZeroSilentMerge |
| `src/entity_resolution/cross_encoder_reranker.py` | **KEEP** | SpatialRelation |
| `src/entity_resolution/graph_resolver.py` | **KEEP** | SpatialEntity (upstream) |
| `src/entity_resolution/canonical_builder.py` | **KEEP** | SpatialEntity (v1) |
| `src/generation/candidate_fusion.py` | **KEEP** | CandidateFusion |
| `src/ingestion/parser.py` | **KEEP** | — |
| `src/ingestion/profiler.py` | **KEEP** | Coordinate Alignment |
| `src/pipelines/batch_pipeline.py` | **KEEP** | SpatialEntity (v1), SpatialRelation, Coordinate Alignment, Geometry QA |
| `src/pipelines/dataset_extractor.py` | **EXPERIMENTAL** | — |
| `src/cli.py` | **KEEP** | — |

**Totals: KEEP = 24, REFACTOR = 1, EXPERIMENTAL = 1**

---

## 3. REFACTOR Candidates

### `src/agents/entity_resolution_agent.py`

**Issue:** Overlap with `src/entity_resolution/pair_features.py::parse_chinese_community_semantics()` and `src/entity_resolution/component_matcher.py::extract_components()`.

**Details:**
- `EntityResolutionAgent.resolve()` does its own entity type classification (deterministic rules) and component extraction (regex)
- `parse_chinese_community_semantics()` in `pair_features.py` does similar entity classification with different rules (more sophisticated — checks building type, property type, non-residential patterns)
- `extract_components()` in `component_matcher.py` does more thorough token extraction with a closed schema of 9 discriminator types

**Recommendation:** Refactor `EntityResolutionAgent.resolve()` to reuse `extract_components()` from `component_matcher.py` and `parse_chinese_community_semantics()` from `pair_features.py`, eliminating the duplicated logic. The `EntityResolutionAgent` should be a thin orchestration layer, not a re-implementation.

---

## 4. EXPERIMENTAL Candidates

### `src/pipelines/dataset_extractor.py`

**Rationale:** This is a training data extraction tool for AI fence generation. The AI fence generation models are themselves experimental. The file is clearly documented as a "Weak-Supervision Silver Dataset Extractor" — its purpose is to bootstrap training data for ML models, not to produce operational spatial MDM outputs. It is not part of the core pipeline and can be removed or modified freely without affecting the main system.

---

## 5. Dependency Graph

```
src/cli.py
  └── src/pipelines/batch_pipeline.py
  │     ├── src/domain/models.py
  │     ├── src/ingestion/parser.py
  │     ├── src/ingestion/profiler.py
  │     ├── src/coordinate/assessment.py
  │     │     ├── src/domain/models.py
  │     │     └── src/coordinate/transforms.py
  │     ├── src/geometry/validation.py
  │     │     └── src/domain/models.py
  │     ├── src/entity_resolution/candidate_retrieval.py
  │     │     └── src/domain/models.py
  │     ├── src/entity_resolution/embedding.py
  │     ├── src/entity_resolution/pair_features.py
  │     │     ├── src/domain/models.py
  │     │     └── src/entity_resolution/component_matcher.py
  │     ├── src/entity_resolution/pair_scorer.py
  │     │     └── src/domain/models.py
  │     ├── src/entity_resolution/graph_resolver.py
  │     │     └── src/domain/models.py
  │     └── src/entity_resolution/canonical_builder.py
  │           ├── src/domain/models.py
  │           └── src/entity_resolution/pair_features.py
  │
  └── src/agents/ (via generate_cmd)
        ├── src/agents/orchestrator.py
        │     ├── src/agents/entity_resolution_agent.py
        │     │     └── src/domain/world_model.py
        │     ├── src/agents/boundary_reasoning_agent.py
        │     │     └── src/agents/entity_resolution_agent.py
        │     ├── src/agents/geometry_generation_agent.py
        │     │     ├── src/agents/entity_resolution_agent.py
        │     │     ├── src/agents/boundary_reasoning_agent.py
        │     │     └── src/generation/candidate_fusion.py
        │     │           ├── src/agents/entity_resolution_agent.py  ← cross-package dependency
        │     │           └── src/agents/boundary_reasoning_agent.py  ← cross-package dependency
        │     └── src/agents/geometry_qa_agent.py
        │           ├── src/agents/entity_resolution_agent.py
        │           ├── src/agents/boundary_reasoning_agent.py
        │           ├── src/agents/geometry_generation_agent.py
        │           ├── src/geometry/ai_fence_guard.py
        │           │     ├── src/geometry/validation.py
        │           │     │     └── src/domain/models.py
        │           │     └── src/domain/models.py
        │           └── src/domain/world_model.py
        │
        └── src/adapters/decision_adapters.py
              └── src/domain/world_model.py

src/pipelines/dataset_extractor.py
  ├── src/ingestion/parser.py
  ├── src/coordinate/assessment.py
  ├── src/coordinate/transforms.py
  └── src/geometry/validation.py
```

**Key observations:**
1. **Dual domain model:** `domain/models.py` (v1) and `domain/world_model.py` (v2) are separate root-level models. The `BatchPipeline` uses v1, the `agents/` layer uses v2.
2. **Cross-package dependency:** `src/generation/candidate_fusion.py` imports from `src.agents.entity_resolution_agent` and `src.agents.boundary_reasoning_agent`, creating a dependency from `generation/` package to `agents/` package. This is architecturally inverted — `agents/` should depend on `generation/`, not the reverse.
3. **Duplicate entity parsing:** `EntityResolutionAgent.resolve()` and `parse_chinese_community_semantics()` in `pair_features.py` both parse entity names with different logic.
4. **Clean layering:** `domain/` → `coordinate/` → `geometry/` → `entity_resolution/` → `pipelines/` is well-structured. The `agents/` layer is a separate v2 pipeline.

---

## 6. Spec Category Coverage Matrix

| Spec Category | Primary File(s) | Status |
|--------------|----------------|--------|
| Coordinate Alignment | `coordinate/assessment.py`, `coordinate/transforms.py` | ✅ Fully implemented |
| Geometry QA | `geometry/validation.py`, `geometry/ai_fence_guard.py`, `agents/geometry_qa_agent.py` | ✅ Fully implemented |
| QualityFinding | `domain/world_model.py` (dataclass), `agents/geometry_qa_agent.py` (construction) | ✅ Fully implemented |
| DecisionImpact | `domain/world_model.py` (dataclass), `agents/geometry_qa_agent.py` (construction) | ✅ Fully implemented |
| ReviewDisposition | `domain/world_model.py` (dataclass) | 🟡 Defined but not yet populated by any existing code |
| Fail-Closed | `geometry/ai_fence_guard.py`, `agents/geometry_qa_agent.py`, `adapters/decision_adapters.py`, `domain/world_model.py` | ✅ Fully implemented |
| ZeroSilentMerge | `entity_resolution/component_matcher.py`, `entity_resolution/pair_scorer.py` | ✅ Fully implemented |
| DecisionAdapter | `adapters/decision_adapters.py` | ✅ Fully implemented |
| SpatialEntity | `domain/world_model.py` (v2), `domain/models.py` (v1: CanonicalEntity) | ✅ Implemented (v2 in world_model, v1 in models) |
| GeometryObservation | `domain/world_model.py` | ✅ Fully implemented |
| SpatialRelation | `domain/world_model.py` (v2), `entity_resolution/pair_scorer.py` (produces v1 EntityRelation) | ✅ Implemented |
| ValidationStatus | `domain/world_model.py` | ✅ Fully implemented |
| BoundaryReasoningAgent | `agents/boundary_reasoning_agent.py` | ✅ Fully implemented |
| CandidateFusion | `generation/candidate_fusion.py`, `agents/geometry_generation_agent.py` | ✅ Fully implemented |

**Note:** `ReviewDisposition` is defined in `world_model.py` but no existing code currently creates `ReviewDisposition` instances. This is a governance step that requires human-in-the-loop integration — it's expected to be populated by external review processes, not automated pipeline code.