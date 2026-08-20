# Fence Dual-Goal Diagnosis

A geofence data-quality and overlap-detection pipeline that answers two questions about a fence inventory before anyone builds decisions on top of it: **which fences are broken, and which fences describe the same piece of ground twice.**

`WORLD MODEL` · `REAL-DATA VALIDATED` · `ANONYMIZED OPERATIONAL DATA` · `MIT`

> **World-model question:** Before you reason about territories, visits, coverage or catchments on a map of geofences — which fences can you trust, and which two fences are quietly the same place?

Part of **TopPrism Business World Modeling**. This repository turns a raw fence export (points + polygon boundaries, mixed coordinate systems, inconsistent naming) into (1) a per-fence quality verdict with literature-grounded geometry diagnostics, and (2) a ranked list of candidate duplicate / overlapping fence pairs — with **zero automatic merges**.

## Why this exists

A fence inventory looks like a solved problem until you look inside it:

- Some polygons self-intersect; some are slivers a few meters wide but hundreds of meters long; one fence covers 5.74 km² where its neighbours cover 30,000 m².
- Half the rows carry WGS84 coordinates and half carry GCJ-02 (the Chinese encrypted datum) — a systematic ~500 m offset that silently corrupts every spatial join.
- The same residential community appears under near-identical names ("XX小区", "XX小区(一期)", "XX小區") in different rows, with partially overlapping polygons.

Any downstream decision engine — territory design, visit planning, coverage analysis — inherits all three failure modes. This pipeline is the quality gate that runs *before* those engines.

## What this engine does

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

**Goal 1 — find broken fences.** Per-fence verdict combining topology validity, size regimes, and a dual-indicator narrow-strip rule (maximum inscribed circle diameter for "how narrow at the widest point" paired with area/perimeter mean width for "how narrow on average"). Both indicators are needed: 2A/P converges to true width only on ribbon-like shapes and underestimates compact ones, while MIC diameter captures the widest passage.

**Goal 2 — find duplicated fences.** Candidate pairs recalled by spatial index (with buffer, so every geometric overlap is guaranteed recall), then ranked by embedding similarity, filtered by typed-component hard gates (numeric discriminants like phase / block numbers never enter the embedding — they are matched exactly, per attribute-level matching practice), and refined by a cross-encoder reranker.

**Ironclad rule: the pipeline never merges automatically.** Every merge decision is left to a human reviewer; the output is a ranked review queue.

## Evidence

Full run on a real fence inventory (anonymized operational data):

| Metric | Value |
|:---|:---|
| Source fences | 9,039 (Beijing 7,431 + Shijiazhuang 1,608) |
| Coordinate-system conflicts aligned (GCJ-02/WGS84) | 8,332 |
| Invalid topologies healed (`make_valid`) | 539 |
| Missing points reconstructed from polygons | 505 |
| Fences flagged with quality issues (Goal 1) | 786 (52 hard failures, 734 flagged for review) |
| Geometric overlap pairs, IoU > 0 (Goal 2) | 248 |
| Near-name relation pairs queued for review | 4,935 |
| Spatial collision alerts (POSSIBLE_MERGE_ERROR) | 12 |
| **Automatic merges performed** | **0** |
| Pipeline wall time | 199 s (plus 19 min sampled rerank) |

**What the evidence does not support:**

- 786 flagged fences is a *review queue*, not a confirmed error count; the 734 soft-flagged fences each carry a specific, checkable reason.
- The 12 POSSIBLE_MERGE_ERROR alerts include known false positives where an abnormally oversized fence contains many small ones — the alert fires on geometry, and the abnormal fence is itself a Goal-1 finding.
- Cross-encoder rerank was validated on a 600-pair sample of the 4,935 soft pairs (16 GB RAM constraint), not the full set; full-set rerank is a roadmap item.
- Numbers are specific to this inventory (Chinese urban residential fences, GCJ-02-affected); thresholds are configurable and were tuned for this data.

## Architecture

```
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
outputs/PROJECT_OVERVIEW.md  methodology, literature-verified
```

Every methodological step — coordinate offset correction, topology healing, shape compactness / elongation measures, MIC narrowness, spatial indexing, IoU overlap criterion, bi-encoder + cross-encoder retrieval, blocking — is cited to primary literature in [`outputs/PROJECT_OVERVIEW.md`](outputs/PROJECT_OVERVIEW.md), which passed a three-round citation audit (several initially mis-attributed references were corrected; corrections are logged in the document).

## Where it fits at TopPrism

Part of the **Business World Model** layer: fences are the spatial backbone that territories, visit plans and catchment analyses hang from. This repo is the quality gate for that backbone. It complements [`bge-entity-match`](https://github.com/topprismdata/bge-entity-match) (name-only entity resolution): here resolution runs on *geometry + name together*, with spatial overlap as ground truth for recall.

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

## Data, privacy & reproducibility

- The source fence export and all per-fence output data (CSV / JS / HTML with coordinates) are **deliberately excluded** from this repository (see `.gitignore`); only code and aggregate reports are published.
- Aggregate reports contain no absolute coordinates; entity names are not included.
- The pipeline is deterministic given the same source file and model versions.

## Boundaries & limitations

- Rerank stage ran in sampled mode on the reference machine (16 GB RAM, cross-encoder int8 ≈ 544 MB); full-set mode is implemented but memory-bound.
- MIXED_CRS fences that could not be confidently aligned are quarantined, not silently corrected.
- Overlap recall is geometrically complete (buffered spatial index guarantees IoU > 0 pairs are recalled) but *name-based* duplicate detection without geometric overlap is out of scope.
- Chinese-language source data; name parsing rules (BASE/COURT/PHASE/SUBAREA components) are tuned for Chinese residential naming conventions.

## Roadmap

- Full-set cross-encoder rerank on a memory-upgraded machine.
- Distinguish genuine containment collisions from "oversized abnormal fence swallows neighbours" automatically.
- Extend coordinate quarantine with a confidence-scored repair suggestion.
- Second-city (Shijiazhuang) threshold calibration pass.

## TopPrism metadata

```yaml
topprism:
  purpose: world-model
  capability: geofence-quality-diagnosis
  platform_layer: business-world-model
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
