# Methodology

The dual-goal diagnosis methodology, and the literature it stands on. Full treatment with citations lives in [`outputs/PROJECT_OVERVIEW.md`](../outputs/PROJECT_OVERVIEW.md); this document summarizes the reasoning chain.

## The two goals

| | Goal | Failure mode if ignored |
|:---|:---|:---|
| **Goal A** | Every fence is trustworthy (geometry + coordinates) | Territory/coverage/visit decisions computed on warped or offset space |
| **Goal B** | No piece of ground is counted twice | Duplicated effort, double-counted demand, phantom conflicts |

The goals are checked **jointly** — the intersection (broken AND duplicated) is the highest-priority finding class, because a duplicate whose geometry is also broken is the easiest to miss and the costliest to carry.

## Goal A: geometry & coordinate diagnostics

| Diagnostic | Method | Why this method |
|:---|:---|:---|
| Topology validity | `make_valid` healing, recorded per fence | Hidden healing = hidden data-quality finding |
| Compactness | Polsby-Popper score 4πA/P² | Standard scale-free compactness measure |
| Sliver / fragment | area below threshold | Classic sliver-polygon detection (ArcGIS lineage) |
| Oversize | area above 1.5 km² | 5.74 km² outlier vs 30,000 m² norm in reference data |
| **Narrow strip** | **MIC diameter < 50 m AND bounding-rect length > 100 m** | See below |
| **Jagged boundary** | **mean width < 30% × MIC diameter** | Average degradation the widest-passage test cannot see |
| Elongated block | aspect ratio > 10 (non-narrow, advisory only) | Scale-free elongation is not absolute narrowness |

### Why the dual-indicator narrow-strip rule

A single width measure cannot answer "is this fence really a narrow strip":

- **2A/P mean width** (area over half-perimeter) converges to the true width only on ribbon-like shapes. On compact shapes it underestimates — a circle's 2A/P equals its radius, not its diameter. So a small 2A/P alone cannot distinguish "genuinely narrow" from "merely small".
- **MIC diameter** (diameter of the maximum inscribed circle; JTS/PostGIS expose exactly this as the narrowness measure) captures the widest passage but says nothing about average degradation — a wide blob with one wide corridor passes.

Pairing them yields three verdicts: narrow strip (MIC small AND long), jagged boundary (mean width far below MIC), elongated but solid (advisory). This rule replaced two earlier iterations (aspect-ratio-only, then mean-width-only) after both produced visible false positives on real data.

### Coordinate quality

- Per-record CRS detection via systematic-offset statistics (GCJ-02's d_lng ≈ 0.0077° mean), per the documented non-linear national-datum offset (100–700 m magnitude).
- WGS84↔GCJ-02 transforms applied where detection is confident; unresolvable MIXED_CRS records are quarantined.
- Missing representative points rebuilt from polygon centroids (505 in the reference run).

## Goal B: overlap & duplicate detection

```
STRtree spatial recall (300 m buffer → IoU>0 recall guaranteed)
        ↓
BGE bi-encoder similarity (bge-large-zh)
        ↓
Typed-component hard gates (exact match on numeric discriminants)
        ↓
Cross-encoder rerank (bge-reranker-v2-m3, sampled in reference run)
        ↓
Ranked review queue — human decides, zero auto-merge
```

Design decisions and their grounds:

1. **Buffered spatial index recall** — R-tree/STRtree with a buffer guarantees every geometric-overlap pair enters the candidate set; name-only duplicates without overlap are explicitly out of scope.
2. **Numbers never enter embeddings** — phase/block numbers are exact-match discriminants (attribute-level matching practice: Ditto, DeepMatcher, Magellan). Embedding "三期" vs "二期" is gambling; exact match is certain.
3. **Bi-encoder then cross-encoder** — recall-then-rerank is the standard retrieval asymmetry: cheap bi-encoder over all candidates, expensive cross-encoder over survivors.
4. **Zero auto-merge** — a wrong merge irreversibly destroys ground truth; a missed merge is recoverable later. Under that asymmetry, merge authority stays with humans. (Product principle; see [architecture](architecture.md).)

## Evidence from the reference run

9,039 fences: 8,332 coordinate alignments, 539 topology healings, 505 point rebuilds, 786 Goal-A flags (52 hard), 248 overlap pairs (IoU > 0), 4,935 near-name pairs queued, 12 collision alerts, **0 automatic merges**. Wall time 199 s + 19 min sampled rerank.

## Citation audit

Every methodological step is cited to primary literature in [`outputs/PROJECT_OVERVIEW.md`](../outputs/PROJECT_OVERVIEW.md). That document passed a three-round audit (entity-resolution literature; GIS geometry-quality literature; pipeline step-to-literature mapping). Three initially mis-attributed references were corrected during the audit and the corrections are logged in place — the audit trail is deliberately kept public.

Representative citations: Polsby & Pepper (1991) · JTS/PostGIS maximum-inscribed-circle narrowness · Mestetskiy (VISAPP 2015) medial-axis width · Stojmenović & Žunić (JMIV 2008) elongation · Li et al. Ditto (PVLDB 2021) · Mudgal et al. DeepMatcher (SIGMOD 2018) · Konda et al. Magellan (VLDB 2016) · Xiao et al. C-Pack/BGE (SIGIR 2024) · Chen et al. BGE M3-Embedding (ACL 2024) · Guttman R-trees (SIGMOD 1984) · Leutenegger STR packing (ICDE 1997) · Jaccard (1912) · Nogueira & Cho BERT reranking (2019) · Douglas & Peucker (1973) · Christen Data Matching (Springer 2012) · GCJ-02 offset characterization (IJGI 2019).
