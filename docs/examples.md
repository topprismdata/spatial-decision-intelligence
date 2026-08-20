# Examples: the fence scenario walkthrough

A condensed walkthrough of the reference run (9,039 real fences, Beijing + Shijiazhuang; data anonymized, coordinates excluded from this repository).

## Before: the export that "looks fine"

Open the source file in any GIS viewer and it renders as an ordinary map of community fences. The three failure modes are invisible at view-level:

| Hidden failure | Scale in reference data |
|:---|:---|
| Wrong coordinate system (GCJ-02 rows in a WGS84 export) | 8,332 rows, ~500 m systematic offset — every spatial join silently lands in the wrong block |
| Broken / degenerate geometry | 539 self-intersecting polygons; slivers metres wide and hundreds of metres long; one 5.74 km² "fence" among 30,000 m² neighbours |
| Same ground counted twice | one community present as "XX小区", "XX小区(一期)", "XX小區" with overlapping polygons |

## Diagnosis: what the engine reports

**Goal A — 786 fences flagged, each with its measured reason.** Representative cases (names as in public street records, coordinates excluded):

- *Narrow strip*: a hutong fence whose widest passage is **7 m** with a mean width of 2.7 m, stretched over hundreds of metres — flagged `NARROW_STRIP` (MIC diameter < 50 m AND ribbon length > 100 m).
- *Oversized*: 5.74 km² vs the 30,000 m² neighbourhood norm — flagged for source-side correction, and identified as the cause of several false collision alerts (it contains many small legitimate fences).
- *Topology healed*: 539 polygons repaired by `make_valid`, each healing recorded so reviewers know the source was invalid.

**Goal B — 248 overlap pairs ranked by IoU.** Representative pair: two named phases of one residential community, IoU 0.48, same address — queued as a merge *candidate* with all evidence (IoU, intersection-over-min, distance, embedding similarity, rerank verdict) shown side by side on an interactive map overlay.

**Collision alerts — 12 POSSIBLE_MERGE_ERROR.** Including known false positives from the oversized fence above — and the engine says so: the alert fires on geometry, and the abnormal fence is itself a Goal-A finding. Alert ≠ verdict.

**Intersection — 112 fences both broken and duplicated.** Highest priority in the queue.

## After: how the review queue is consumed

The engine stops at the queue; humans act:

1. **Coordinates** — 8,332 rows corrected *before* any downstream spatial join runs on the data; 12 unresolvable MIXED_CRS rows quarantined for source-system follow-up.
2. **Geometry** — oversized/abnormal fences fixed or split at the source; healed topologies fed back to the source system.
3. **Duplicates** — each of the 248 overlap pairs confirmed or rejected individually. **0 silent merges**: a wrong merge destroys ground truth irrecoverably, which is why the engine's vocabulary has no merge verb.

Net effect: territory, visit and catchment engines downstream now run on a trusted fence layer instead of inheriting three failure modes — and every number they produce is traceable back to a fence that has an explicit quality verdict.

## Reproducing the walkthrough

```bash
python run.py                        # M0 → M3, writes QA + relation outputs
python generate_fence_dual_goals.py  # dual-goal HTML report with map overlay
python generate_inspector.py         # per-category case inspector
```

See [README](../README.md#quick-start) for environment setup.
