# Examples

## Geofence Integrity — Reference Dataset

| Fence type | Count | Example |
|:---|---:|:---|
| Residential community | 1,200+ | Typical 10–50 building compound with perimeter wall |
| Residential courtyard (dormitory) | 200+ | Smaller enclosed unit, often 1–5 buildings |
| Mixed commercial-residential | 100+ | Ground-floor retail with upper-floor housing |
| Non-residential | 50+ | Office parks, schools, government compounds |

## Degradation modes captured

| Mode | Description | Example |
|:---|:---|:---|
| Missing boundary | Point only, no polygon | A community known by name but never surveyed |
| Narrow strip | MIC < 50 m, length > 100 m | Roadside sliver from a digitizing error |
| Self-intersection | Bowtie polygon | Boundary crosses itself at entrance |
| GCJ-02 offset | Point-to-polygon shift ≈ 300–700 m | Point recorded in WGS-84, polygon in GCJ-02 |
| Overlap | Two fences on same ground | Duplicate record from different data entry |
| Phase mismatch | "Phase 1" vs "Phase 2" merged | Numeric discriminant not respected |
