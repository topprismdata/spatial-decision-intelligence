# Spatial Decision Intelligence Engine

**AI-powered spatial decision diagnosis: identify conflicts between business objectives and spatial constraints through explainable diagnostic reasoning.**

`WORLD MODEL` · `FOUNDATION LAYER` · `REAL-DATA VALIDATED` · `ANONYMIZED OPERATIONAL DATA` · `MIT`

> **Decision question:** when a spatial strategy underperforms — coverage gaps, duplicated effort, territories that quietly overlap — is the plan wrong, or is the spatial data the plan runs on broken? Before you can optimize, you have to *diagnose*.

The engine is built around three capabilities:

- ✓ **Spatial constraint analysis** — geometry, coordinates and topology are treated as first-class constraints on business decisions, not as a data-cleaning detail.
- ✓ **Multi-objective conflict diagnosis** — two goals are examined *simultaneously and jointly* (is the data trustworthy **and** is the same ground counted twice), because either failure silently corrupts every decision built on top.
- ✓ **Explainable, actionable output** — every finding carries a specific, human-checkable reason; the engine proposes, humans decide (**zero automatic merges**, ever).

**First application scenario: Geofence Diagnosis** *(this repository was initially published as `fence-dual-goal-diagnosis`; the fence scenario is now scenario #1 of the broader engine)*. A real fence inventory of 9,039 polygons was run end-to-end; see [Evidence](#evidence-real-data-validated-fence-scenario).

---

## Why this exists

Enterprises make spatial decisions under permanent tension:

```
        growth targets
             ↑
   coverage reach ←→ service efficiency
             ↓
        cost discipline
```

Coverage vs cost, service radius vs response time, channel expansion vs distributor conflict — every one of these is a *spatial* trade-off, and every one of them is computed on a map of business geofences.

The tooling landscape leaves a gap:

- **Traditional GIS** answers *where is what* — it displays space, it does not judge the plan.
- **Optimization algorithms** answer *how to optimize* — but only after the objective, constraints and data are trusted; garbage fences in, confident-looking garbage territories out.
- **What enterprises actually need first** is *why the current spatial setup is unreliable* — which fences are broken, which pieces of ground are counted twice, and what to do about each.

That is **diagnosis**, and it is what this engine does.

The fence inventory is where diagnosis starts, because a fence export looks solved until you look inside it:

- Some polygons self-intersect; some are slivers a few metres wide but hundreds of metres long; one fence covers 5.74 km² where its neighbours cover 30,000 m².
- Half the rows carry WGS84 coordinates and half carry GCJ-02 (the Chinese encrypted datum) — a systematic ~500 m offset that silently corrupts every spatial join.
- The same residential community appears under near-identical names ("XX小区", "XX小区(一期)", "XX小區") in different rows, with partially overlapping polygons.

Any downstream decision engine — territory design, visit planning, coverage analysis — inherits all three failure modes. This engine is the diagnostic gate that runs *before* those engines.

## Dual-goal diagnosis framework

```
              Business Goals
         Goal A                Goal B
            \                 /
             \               /
           Conflict Space ---+--- (both goals must hold at once;
                              optimizing one alone hides the other's failure)
                    |
            Diagnosis Engine
                    |
        Root Cause Identification   (per-fence, per-pair, with evidence)
                    |
     Optimization Recommendation    (ranked review queue — human decides)
```

Applied to geofences:

| | Goal | Diagnostic question |
|:---|:---|:---|
| **Goal A** | Trustworthy fence layer | Which fences have broken geometry or corrupted coordinates? |
| **Goal B** | No double-counted ground | Which fences describe the same piece of ground twice? |

The two goals are inseparable: a duplicate fence whose geometry is also broken is the highest-priority finding of all (112 fences in the reference run sat in exactly that intersection).

## What the engine does (scenario #1: geofences)

```
Source export (xlsx: points + WKT polygons)
        ↓
M0  Dataset health check
        ↓
M1  Coordinate alignment   (GCJ-02 → WGS84 detection & correction, point rebuild)
        ↓
M2  Geometry QA            (topology healing, sliver / narrow-strip / oversize /
                            aspect-ratio diagnostics via MIC + mean width)
        ↓
M3  Entity resolution      (STRtree spatial recall → BGE bi-encoder →
                            typed-component hard gates → cross-encoder rerank)
        ↓
M4  Deliverables           (per-fence QA report, relation pairs, interactive map)
```

**Goal A — find broken fences.** Per-fence verdict combining topology validity, size regimes, and a dual-indicator narrow-strip rule (maximum inscribed circle diameter for "how narrow at the widest point" paired with area/perimeter mean width for "how narrow on average"). Both indicators are needed: 2A/P converges to true width only on ribbon-like shapes and underestimates compact ones, while MIC diameter captures the widest passage.

**Goal B — find duplicated ground.** Candidate pairs recalled by spatial index (with buffer, so every geometric overlap is guaranteed recall), then ranked by embedding similarity, filtered by typed-component hard gates (numeric discriminants like phase / block numbers never enter the embedding — they are matched exactly, per attribute-level matching practice), and refined by a cross-encoder reranker.

**Ironclad rule: the engine never merges automatically.** Every merge decision is left to a human reviewer; the output is a ranked, evidence-carrying review queue.

## Architecture

The engine is layered as a decision-system component, not a batch algorithm:

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

Current implementation mapping:

| Layer | Module |
|:---|:---|
| GIS / Data Sources | `src/ingestion/` (xlsx parsing, normalization) |
| Spatial Model | `src/coordinate/` (GCJ-02 ↔ WGS84), `src/geometry/` (topology, MIC / mean-width diagnostics) |
| Diagnosis Reasoning | `src/entity_resolution/` (STRtree recall, BGE bi-encoder, component gates, rerank) |
| Dual Goal Engine / orchestration | `src/pipelines/`, `run.py` |
| Deliverables (agent-facing) | `generate_fence_dual_goals.py`, `generate_inspector.py`, `rerank_stage.py` |

Detailed design: [`docs/architecture.md`](docs/architecture.md).

## Evidence (real-data validated, fence scenario)

Full run on a real fence inventory (anonymized operational data):

| Metric | Value |
|:---|:---|
| Source fences | 9,039 (Beijing 7,431 + Shijiazhuang 1,608) |
| Coordinate-system conflicts aligned (GCJ-02/WGS84) | 8,332 |
| Invalid topologies healed (`make_valid`) | 539 |
| Missing points reconstructed from polygons | 505 |
| Fences flagged with quality issues (Goal A) | 786 (52 hard failures, 734 flagged for review) |
| Geometric overlap pairs, IoU > 0 (Goal B) | 248 |
| Near-name relation pairs queued for review | 4,935 |
| Spatial collision alerts (POSSIBLE_MERGE_ERROR) | 12 |
| **Automatic merges performed** | **0** |
| Pipeline wall time | 199 s (plus 19 min sampled rerank) |

**What the evidence does not support:**

- 786 flagged fences is a *review queue*, not a confirmed error count; the 734 soft-flagged fences each carry a specific, checkable reason.
- The 12 POSSIBLE_MERGE_ERROR alerts include known false positives where an abnormally oversized fence contains many small ones — the alert fires on geometry, and the abnormal fence is itself a Goal-A finding.
- Cross-encoder rerank was validated on a 600-pair sample of the 4,935 soft pairs (16 GB RAM constraint), not the full set; full-set rerank is a roadmap item.
- Numbers are specific to this inventory (Chinese urban residential fences, GCJ-02-affected); thresholds are configurable and were tuned for this data.
- The evidence covers **one scenario (geofences)**. The extension scenarios below are direction, not results.

## Evaluation framework

Diagnosis is not accuracy-only. The engine is evaluated on three dimensions; current status per dimension:

| Dimension | Question | Status (fence scenario) |
|:---|:---|:---|
| **Conflict detection** | Are real problems found — completely? | Real-data validated: 786 issue fences, 248 overlap pairs; geometric recall of IoU > 0 pairs is *guaranteed* by the buffered spatial index |
| **Explanation quality** | Does each finding state a checkable cause? | Every flag carries a specific reason (e.g. "narrow strip: widest passage 7 m, ribbon 340 m long"); qualitative so far |
| **Actionability** | Do recommendations get accepted and work? | Not yet evaluated — the engine stops at a ranked review queue by design; suggestion generation is a roadmap item |

## Demo: before → diagnosis → after

A walkthrough of the reference run (real data, anonymized; interactive version: [`docs/examples.md`](docs/examples.md)):

```
BEFORE (raw export)
  9,039 fences, "looks fine" in any GIS viewer
  ├─ 8,332 rows in the wrong coordinate system (~500 m systematic offset)
  ├─ 539 self-intersecting polygons
  └─ the same community present twice with overlapping polygons

DIAGNOSIS (this engine, 199 s)
  Goal A: 786 fences flagged, each with a reason
     e.g. "narrow strip — widest passage 7 m over a 340 m ribbon"
          "oversized — 5.74 km² vs 30,000 m² neighbourhood norm"
  Goal B: 248 overlap pairs ranked by IoU
     e.g. two named phases of one community, IoU 0.48, same address
  12 collision alerts, 4,935 near-name pairs queued

AFTER (human review actions the queue)
  ├─ coordinates corrected before any spatial join runs on the data
  ├─ oversized/abnormal fences fixed or split at the source
  └─ duplicates confirmed or rejected one by one — 0 silent merges
  Effect: downstream engines (territory, visits, catchment) run on
  a trusted fence layer instead of inheriting three failure modes.
```

## Why not traditional GIS / optimization?

| | GIS | Optimization | **TopPrism Diagnosis** |
|:---|:---:|:---:|:---:|
| Displays space | ✓ | △ | ✓ |
| Detects anomalies | △ | ✓ | ✓ |
| Explains causes | × | × | ✓ |
| Understands business goals | × | △ | ✓ |
| Produces action recommendations | × | △ | ✓ *(roadmap)* |

## Where it fits in the TopPrism capability system

Not an island — the spatial foundation of the decision stack:

```
              TopPrism AI Decision OS
                       |
                Geo Intelligence
                       |
              Spatial Foundation  ← this repo
      ┌──────────┬──────────┬──────────┬──────────┐
 Fence        Route       Store      Territory
 Diagnosis    Optimization Potential  Planning
 (this)       (open-dispatch, (themed-  (visit-scheduling-
              logistics-     street-   optimizer,
              dispatch-      engine)   market-partition)
              clustering)
```

Related world-model repos: [`bge-entity-match`](https://github.com/topprismdata/bge-entity-match) resolves entities by *name*; this engine resolves *geometry + name together*, with spatial overlap as recall ground truth. Together they form the trusted spatial + entity foundation for the decision engines above.

## Extension scenarios (roadmap)

The same diagnose-before-optimize loop generalizes across spatial decisions:

- **Channel geofence diagnosis** — electronic fences for channel management: coverage holes, boundary conflicts between channels.
- **Distributor territory conflict diagnosis** — overlapping exclusive territories, double-served demand.
- **Store coverage diagnosis** — catchment overlaps, whitespace, cannibalization.
- **Delivery network diagnosis** — zone fragmentation, dispatch boundary anomalies.
- **Market whitespace diagnosis** — systematically under-covered areas vs demand signals.

Each scenario reuses the framework (dual goals → conflict space → root cause → recommendation); only the spatial model and business rules change.

## Quick start

```bash
# environment (managed venv assumed)
pip install shapely pandas openpyxl fastembed onnxruntime torch

# place the source export at the expected path (see src/ingestion/parser.py)
export FASTEMBED_CACHE_DIR=~/.cache/fastembed
export OMP_NUM_THREADS=4
export KMP_DUPLICATE_LIB_OK=TRUE   # torch libomp vs onnxruntime conflict

python run.py                      # full pipeline M0 → M3
python generate_fence_dual_goals.py  # dual-goal HTML report with map
python generate_inspector.py         # interactive case inspector
python rerank_stage.py               # full-set rerank (needs ~1 GB free RAM)
```

## Repository layout

```
docs/
  architecture.md              layered architecture & zero-auto-merge principle
  methodology.md               dual-goal methodology, literature-verified
  examples.md                  fence-scenario walkthrough (before/diagnosis/after)
src/
  ingestion/         xlsx parsing, record normalization
  coordinate/        GCJ-02 ↔ WGS84 detection & transform
  geometry/          topology healing, MIC / mean-width diagnostics, QA scoring
  entity_resolution/ STRtree recall, BGE bi-encoder, component gates, rerank
  pipelines/         orchestration (M0 → M4)
run.py                      full pipeline entry point
generate_fence_dual_goals.py  dual-goal report with map overlay (Tencent Maps GL)
generate_inspector.py        interactive per-category case inspector
rerank_stage.py              full-set cross-encoder rerank (memory permitting)
outputs/PROJECT_OVERVIEW.md  full methodology with audited citations
```

Every methodological step — coordinate offset correction, topology healing, shape compactness / elongation measures, MIC narrowness, spatial indexing, IoU overlap criterion, bi-encoder + cross-encoder retrieval, blocking — is cited to primary literature in [`outputs/PROJECT_OVERVIEW.md`](outputs/PROJECT_OVERVIEW.md), which passed a three-round citation audit (several initially mis-attributed references were corrected; corrections are logged in the document).

中文版说明见 [`README_CN.md`](README_CN.md).

## Data, privacy & reproducibility

- The source fence export and all per-fence output data (CSV / JS / HTML with coordinates) are **deliberately excluded** from this repository (see `.gitignore`); only code and aggregate reports are published.
- Aggregate reports contain no absolute coordinates; entity names are not included.
- The pipeline is deterministic given the same source file and model versions.

## Boundaries & limitations

- Rerank stage ran in sampled mode on the reference machine (16 GB RAM, cross-encoder int8 ≈ 544 MB); full-set mode is implemented but memory-bound.
- MIXED_CRS fences that could not be confidently aligned are quarantined, not silently corrected.
- Overlap recall is geometrically complete (buffered spatial index guarantees IoU > 0 pairs are recalled) but *name-based* duplicate detection without geometric overlap is out of scope.
- Chinese-language source data; name parsing rules (BASE/COURT/PHASE/SUBAREA components) are tuned for Chinese residential naming conventions.
- One scenario implemented (geofences); extension scenarios above are roadmap, not results.

## TopPrism metadata

```yaml
topprism:
  purpose: world-model
  capability: spatial-decision-diagnosis
  scenario: geofence-diagnosis        # first of N scenarios
  platform_layer: business-world-model
  stack_position: foundation          # layer zero: trusted spatial ground truth
  maturity: real-data-validated
  evidence:
    type: anonymized-operational-data
    scope: "9,039 geofences (Beijing + Shijiazhuang); 13,026 detected relations; 0 auto-merges"
  product_context:
    - data-standardization
    - geofence-quality
    - outlet-resolution
    - business-world-model
```

## License

Released under the MIT License — see [`LICENSE`](LICENSE).
