# Spatial Decision Intelligence

**The trusted spatial world model integrity layer and decision readiness gate for enterprise decision engines.**

`TRUSTED WORLD STATE` · `DECISION READINESS` · `4-AGENT ARCHITECTURE` · `EXPLAINABLE DIAGNOSIS` · `HUMAN-GOVERNED` · `MIT`

> **Core Question:** Before optimizing territories, visit plans, store coverage, or delivery networks, the system answers a fundamental prerequisite:  
> **Is the spatial world represented by the data trustworthy enough to make an automated decision?**

Spatial Decision Intelligence transforms inconsistent coordinates, broken geofences, and ambiguous spatial entities into verified, traceable **spatial facts (Trusted Spatial State)** that downstream decision solvers can safely consume without inheriting silent spatial corruption.

The current production-validated scenario is **Geofence Integrity**: 9,039 operational fences run end-to-end; see [Empirical Evidence](#6-empirical-evidence-9039-operational-fences-validated).

---

## 1. Product Positioning & System Architecture

This project adopts a two-tier product hierarchy:

```text
Spatial Decision Intelligence (Platform Vision)
└── Spatial World Model Integrity Engine (Current Core Product: Spatial Integrity Layer)
    └── Geofence Integrity (Scenario #1: Validated Production Scenario)
```

### Position in the TopPrism Decision OS

Under TopPrism's SVDE reference architecture (*Agent is Interface, Protocol is Runtime*), this project operates as the foundational spatial gate preceding semantic compilation and optimization solvers:

```text
Enterprise Spatial Reality
Stores, Fences, Coordinates, Roads, Territories, Operational Exports
                  │
                  ▼
┌─────────────────────────────────────────────────────────┐
│ Spatial World Model Integrity Layer (This Project)      │
│ Pre-Decision Diagnostic Gate                            │
│                                                         │
│ · Coordinate Alignment: WGS-84 / GCJ-02 offset repair   │
│ · Geometric QA: Self-intersection healing, MIC strips   │
│ · Entity Resolution: Spatial overlap + BGE Cross-Encoder│
│ · Readiness Gates: Fail-Closed quarantine, 3-tier queue │
└────────────────────────────┬────────────────────────────┘
                             │ Trusted Spatial State
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Decision Semantic Layer                                 │
│ Compiles business objectives into formal spatial bounds │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│ Decision Compiler & Solvers                             │
│                                                         │
│ · Visit Scheduling (visit-scheduling-optimizer)         │
│ · Territory Partitioning (market-partition)             │
│ · Dispatch Routing (open-dispatch)                      │
│ · Store Potential (themed-street-engine)                │
└────────────────────────────┬────────────────────────────┘
                             ▼
               Execution → Outcome → Decision Memory
```

This means the engine does not answer *"How should geofences be drawn?"*, but rather:  
**"Is the spatial world seen by the decision engine genuine, unified, conflict-free, and ready for automated decision making?"**

---

## 2. Core Architecture: 4-Agent Spatial Intelligence Platform

Community fence generation is not about asking an LLM to hallucinate a polygon—it is an **entity understanding and spatial evidence reasoning process**. The system orchestrates 4 specialized agents:

```text
               [ Input: Community Name + Address + Seed Point ]
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│              Spatial Intelligence Agent Platform (4-Agent Layer)         │
│                                                                          │
│  🏢 Agent 1: Entity Resolution Agent                                     │
│     · Semantic component gates (Base, Court, Phase, Subarea)             │
│     · Entity scale inference (Courtyard ~2k m² vs Community ~30k m²)     │
│                                      │
│                                      ▼
│  🗺️ Agent 2: Boundary Reasoning Agent                                     │
│     · Spatial context: Search bbox, target area prior, adaptive zoom     │
│     · Emits formal BoundaryConstraints packet                            │
│                                      │
│                                      ▼
│  📐 Agent 3: Geometry Generation Agent & Candidate Fusion                │
│     · Multi-hypothesis: [Road Block] + [Building Hull] + [Area Buffer]   │
│     · Spatial Reasoning Scorer: Point, area alignment, compactness       │
│     · Synthesizes optimal physical polygon boundary                      │
│                                      │
│                                      ▼
│  🛡️ Agent 4: Geometry QA Agent                                           │
│     · Health checks: Self-intersection healing, MIC narrow strips        │
│     · Decision Readiness Gate: Auto-degrades to Route A on severe defect │
└─────────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
                      [ Trusted Spatial State ]
                      (Published to territory, visit, and dispatch solvers)
```

---

## 3. What It Is NOT

To establish rigorous engineering and academic boundaries, this engine explicitly is:

1. **NOT a General-Purpose GIS Viewer**: Visualizing points on a map is a diagnostic side-effect, not the core deliverable;
2. **NOT an Automatic-Merging MDM**: Operates under an absolute **zero false-merge policy** (0 silent merges); all entity ambiguities are routed to human review with evidence packets;
3. **NOT a Downstream Territory/Routing Optimizer**: Does not replace solvers like `market-partition` or VRP engines, but acts as their **pre-solver gate (Fail-Closed Gate)**;
4. **NOT Claiming All Spatial Domains Are Solved**: Validated on **Geofence Integrity**; channel disputes, dynamic mobility, and market white-spaces remain on the evolution roadmap.

---

## 4. Decision-Readiness Contract

Before spatial facts can be consumed by downstream solvers, they must satisfy a 6-dimensional readiness contract:

| Contract Dimension | Pre-Decision Question | Current Capability | Fail-Closed Policy |
| :--- | :--- | :---: | :--- |
| **Coordinate Trust** | Are points, polygons, and roads in a unified spatial reference datum? | ✅ Validated | 7-parameter transform; unaligned entities **Quarantined** |
| **Geometric Trust** | Are polygons topologically valid, non-self-intersecting, and non-sliver? | ✅ Validated | `make_valid` healing; degenerate slivers **Blocked** |
| **Entity Trust** | Are similar records identical entities, sibling phases, or distinct? | ✅ Validated | Component gates + Cross-Encoder re-ranking |
| **Relational Trust** | Is there ground double-counting, abnormal overlap, or collision? | ✅ Validated | IoU + semantic re-ranking into 3-tier work orders |
| **Decision Applicability** | Does the output satisfy consumer solver input schemas? | ✅ Validated | Downstream Adapters (Territory / Visit / Coverage) |
| **Temporal Freshness** | Does the data reflect recent ground physical reality? | Roadmap | Planned (Satellite change detection) |

---

## 5. Diagnostic Reasoning: From Finding to Disposition

Diagnostic outputs follow a strict structural pipeline:  
**Finding $\rightarrow$ Evidence $\rightarrow$ Impact $\rightarrow$ Recommended Review $\rightarrow$ Disposition**

```text
Finding
  └─ Example: Geofence SRC_0042 is a degenerate narrow sliver (MIC diameter 7.1m, length 340m)
Evidence
  └─ Rule: MAXIMUM_INSCRIBED_CIRCLE < 50m; Metrics: max_w=7.1m, mean_w=4.2m, length=340m
Impact
  └─ Blocked Solvers: [market-partition, open-dispatch]; Consequence: Distorts territory capacity by 80%
Recommended Review
  └─ Human review needed to determine whether geometry represents roadside retail strip or digitizing error
Disposition
  └─ Reviewer action: [CONFIRM_REPAIR / SPLIT / QUARANTINE] ──► Fed back into Decision Memory
```

---

## 6. Empirical Evidence (9,039 Operational Fences Validated)

Validated across 9,039 operational enterprise geofences (Beijing 7,431 + Shijiazhuang 1,608):

| Diagnostic Claim | Measured Empirical Evidence | Status |
| :--- | :--- | :---: |
| **Systematic CRS Alignment** | 8,332 WGS-84 point vs GCJ-02 polygon offsets corrected; 505 missing points rebuilt from centroid | **Validated** |
| **Topology Knot Healing** | 539 self-intersecting / bowtie polygons 100% healed automatically | **Validated** |
| **Industrial Narrow-Strip Detection** | 838 degenerate slivers identified via Maximum Inscribed Circle (MIC), replacing 70%-false-positive aspect ratio rules | **Validated** |
| **Cross-Encoder Disambiguation** | 4,931 soft candidate pairs re-scored with BGE Cross-Encoder on Apple Silicon MPS (410s total runtime) | **Validated** |
| **Tiered Work-Order Routing** | Tier 1 (Critical Overlap): 1,311 / Tier 2 (Standard Soft): 2,808 / Tier 3 (Filtered): 8,907 | **Validated** |
| **Zero False-Merge Red Line** | Exact 0 automatic merges executed; 100% human-governed | **Validated** |

> **What the Evidence Does NOT Claim (Counter-Evidence Boundaries):**  
> 1. Evidence proves the effectiveness of data diagnosis and readiness gating, **not that downstream territory allocations are automatically optimal**;  
> 2. Weak-supervision AI self-drawing is in dataset preparation (7,630 satellite patches) and exploratory benchmarking; it does not replace operational procurement.

---

## 7. Quick Start

Run on a clean machine without private dependencies:

### 1. Environment Setup

```bash
git clone https://github.com/topprismdata/spatial-decision-intelligence.git
cd spatial-decision-intelligence

python3 -m venv .venv
source .venv/bin/activate

pip install -e .
```

### 2. Run 4-Agent Spatial Reasoning & Fence Generation

```bash
# Execute 4-Agent reasoning pipeline for a community brief
spatial-di generate "万科星河湾二期" \
  --address "朝阳北路88号" \
  --lng 116.452 \
  --lat 39.921 \
  --area 32000 \
  --output-geojson outputs/vanke_demo.geojson
```

### 3. Run Synthetic Benchmark Diagnosis

```bash
# Diagnose bundled 30-fence synthetic benchmark capturing real degradation modes
spatial-di diagnose examples/sample_fences.geojson

# Or diagnose custom Excel / GeoJSON datasets
spatial-di diagnose /path/to/your/fences.xlsx --output-dir outputs/
```

### 4. Launch Multi-City Case Inspector

```bash
# Open interactive case inspector with 3-tier filtering & CSV export
open outputs/interactive_inspector.html
```

---

## 8. License & Project Structure

* **License**: [MIT License](LICENSE)
* **Key Components**:
  * `src/agents/`: 4-Agent Layer (`EntityResolution`, `BoundaryReasoning`, `GeometryGeneration`, `GeometryQA`, `SpatialIntelligencePlatform`);
  * `src/generation/candidate_fusion.py`: Multi-hypothesis candidate generation & spatial reasoning scorer;
  * `src/domain/world_model.py`: Formal Spatial World Model contracts (`SpatialEntity`, `QualityFinding`, `DecisionImpact`, `TrustedSpatialState`);
  * `src/adapters/decision_adapters.py`: Fail-Closed adapters for downstream solvers (`TerritoryPlanning`, `VisitScheduling`, `CoverageAnalysis`);
  * `src/geometry/ai_fence_guard.py`: Quality gate & graceful fallback guard for AI-generated geometries;
  * `src/cli.py`: Unified `spatial-di` command-line tool.
