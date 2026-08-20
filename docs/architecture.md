# Architecture

The engine is layered as a **decision-system component**, not a batch algorithm. Each layer has one responsibility; the layers below never make business decisions, and the layers above never touch raw geometry.

```
        Decision Agent / Human Reviewer
        (final authority; zero auto-merge by design)
                    |
        Diagnosis Reasoning Layer
        (typed-component gates, evidence chaining,
         per-finding explanations)
                    |
            Dual Goal Engine
        (Goal A: geometry/coordinate QA
         Goal B: overlap + entity resolution)
             |              |
      Spatial Model    Business Rules
      (CRS handling,    (naming conventions,
       topology, MIC,    entity-type taxonomy,
       IoU)              review thresholds)
             |
      GIS / Data Sources
      (points + WKT polygons, xlsx exports, maps)
```

## Layer responsibilities

### GIS / Data Sources
Raw reality: an xlsx export where each record carries a representative point, an optional polygon boundary (WKT), an entity name, and an entity type. No assumptions about coordinate system, topology validity, or naming consistency.

### Spatial Model
The mathematics the engine is allowed to trust:

- **Coordinate handling** — detect GCJ-02 vs WGS84 per record via systematic-offset statistics (d_lng ≈ 0.0077° mean); align everything to WGS84; rebuild missing representative points from polygon centroids. Records that cannot be confidently aligned are quarantined (MIXED_CRS), never silently corrected.
- **Topology** — self-intersecting / invalid polygons are healed once with `make_valid` and the healing is *recorded* (539 in the reference run), because a healed-but-unreported topology is a hidden data-quality finding in itself.
- **Shape diagnostics** — the dual-indicator narrow-strip rule: maximum inscribed circle (MIC) diameter measures "how narrow at the widest passage"; area/perimeter mean width (2A/P) measures "how narrow on average". Neither alone suffices: 2A/P converges to true width only on ribbon-like shapes and underestimates compact ones (a circle's 2A/P equals its radius), while MIC ignores average degradation. Narrow strip = MIC < 50 m AND bounding-rect length > 100 m; jagged boundary = mean width < 30% of MIC diameter.
- **Overlap** — IoU and intersection-over-min as the overlap criteria.

### Business Rules
Domain knowledge that is data, not code-as-magic:

- **Naming conventions** — Chinese residential names decompose into typed components: BASE / COURT(院) / PHASE(期) / SUBAREA(区/区片). The decomposition drives both the hard gates and the sibling-relation taxonomy (SIBLING_COURTYARD, SIBLING_PHASE, SIBLING_SUBAREA, PHASE_TO_WHOLE, …).
- **Entity-type taxonomy** — RESIDENTIAL_COMMUNITY, RESIDENTIAL_COURTYARD, RESIDENTIAL_DORMITORY, MIXED_COMMERCIAL_RESIDENTIAL, NON_RESIDENTIAL_*.
- **Review thresholds** — narrow-strip cutoffs, oversize limit (1.5 km²), aspect-ratio limit, similarity thresholds. All configurable; tuned for the reference inventory.

### Diagnosis Reasoning Layer
Where findings get their evidence:

- **Typed-component hard gates** — numeric discriminants (phase numbers, block numbers) are matched exactly and never enter embeddings. "XX小区(一期)" vs "XX小区(二期)" differ by one token but are different fences; "XX小區" vs "XX小区" differ by script variant and are the same fence. Attribute-level matching (Ditto / DeepMatcher / Magellan lineage) instead of whole-string pooling.
- **Evidence chaining** — every relation pair carries IoU, intersection-over-min, distance, and embedding similarity; every QA flag carries its measured indicator values. A reviewer never sees a bare score — always the underlying evidence.
- **Rerank** — bge-reranker-v2-m3 cross-encoder refines soft pairs; downgrades and alias confirmations are logged per pair.

### Dual Goal Engine
Orchestration (M0 → M4) that enforces the two goals jointly and maintains the intersection finding (fences both broken AND duplicated = highest priority).

### Decision Agent / Human Reviewer
**The zero-auto-merge principle.** The engine's output vocabulary has no "merge" verb — only "propose for review". Rationale: a wrong merge destroys ground truth irrecoverably (two real fences become one, and the error is invisible in every downstream view), while a missed merge is recoverable by a later review round. Under that asymmetry, automatic merging is never worth the risk. This is a product principle, not a temporary limitation.

## Pipeline stages

```
M0  Dataset health check          schema, nulls, type distribution
M1  Coordinate alignment          GCJ-02/WGS84 detection, correction, point rebuild
M2  Geometry QA                   topology healing + per-fence diagnostics + scoring
M3  Entity resolution             STRtree recall → BGE → component gates → rerank
M4  Deliverables                  QA report, relation pairs, interactive map
```

## Module map

| Module | Layer | Responsibility |
|:---|:---|:---|
| `src/ingestion/` | Data Sources | xlsx parsing, record normalization |
| `src/coordinate/` | Spatial Model | GCJ-02 ↔ WGS84 detection & transform |
| `src/geometry/` | Spatial Model | topology healing, MIC / mean-width diagnostics, QA scoring |
| `src/entity_resolution/` | Diagnosis Reasoning | STRtree recall, BGE bi-encoder, component gates, rerank |
| `src/pipelines/` | Dual Goal Engine | stage orchestration M0 → M4 |
| `run.py` | Dual Goal Engine | full pipeline entry point |
| `generate_fence_dual_goals.py` | Deliverables | dual-goal HTML report with map overlay |
| `generate_inspector.py` | Deliverables | interactive per-category case inspector |
| `rerank_stage.py` | Diagnosis Reasoning | full-set cross-encoder rerank |

## Extension points for new scenarios

A new diagnostic scenario (distributor territories, store coverage, …) plugs in by replacing two things and keeping four:

- **Replace**: the Spatial Model's scenario-specific diagnostics, and the Business Rules' taxonomy/thresholds.
- **Keep**: the reasoning layer (gates + evidence chaining), the zero-auto-merge decision boundary, the dual-goal orchestration pattern, and the deliverable generators' review-queue format.
