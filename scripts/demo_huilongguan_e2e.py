"""回龙观端到端演示 v4: 4-gate pipeline + gazetteer + coverage gate 全流程.

输入: Geofabrik landuse=residential (回龙观子集)
输出: outputs/huilongguan_demo/huilongguan_validated.geojson (带 FinalDisposition)
"""
import warnings
warnings.filterwarnings("ignore")
import time, json, os
import geopandas as gpd
import pandas as pd

from src.domain.contracts import (
    OntologyType, BoundaryHypothesis, Evidence, EvidenceType, HypothesisStatus,
)
from src.entity_resolution.amap_gazetteer import gazetteer_from_batch_outputs
from src.validation.external_coverage_gate import ExternalCoverageGate, PolygonContext
from src.validation.pipeline import ValidationPipeline

t0 = time.time()

res = gpd.read_file("data/beijing_shp/gis_osm_landuse_a_free_1.shp")
HLG = res[(res["fclass"] == "residential")].reset_index(drop=True)
HLG = HLG[(HLG.geometry.centroid.x > 116.29) & (HLG.geometry.centroid.x < 116.39) &
          (HLG.geometry.centroid.y > 40.05) & (HLG.geometry.centroid.y < 40.10)]
print(f"回龙观 residential 面片: {len(HLG)}")

gaz = gazetteer_from_batch_outputs()
base = pd.read_csv("outputs/beijing_batch/amap_name_matches.csv")
hits = {(round(float(r["poi_lng"]), 2), round(float(r["poi_lat"]), 2))
        for _, r in base.iterrows() if pd.notna(r["poi_lng"])}


class PointPOIProvider:
    def __init__(self, pts):
        self._pts = pts

    def has_residential_poi(self, lng, lat, radius_m=200.0):
        return any(abs(lng - x) < 0.01 and abs(lat - y) < 0.01 for x, y in self._pts)


pipe = ValidationPipeline(
    coverage_gate=ExternalCoverageGate(poi_provider=PointPOIProvider(hits)))

results = []
for idx, (_, row) in enumerate(HLG.iterrows()):
    g = row.geometry
    name = row.get("name") or ""
    pt = g.centroid
    evid = [Evidence(source="OSM_landuse", evidence_type=EvidenceType.GEOMETRY,
                     content=f"landuse=residential area={g.area * 111320 * 111320:.0f}m2",
                     confidence=0.8)]
    if name:
        evid.append(Evidence(source="OSM_name_tag", evidence_type=EvidenceType.NAME,
                             content=name, confidence=0.9))
    hyp = BoundaryHypothesis(entity_id=name or f"hlg_{idx}", geometry=g.wkt,
                             generator="ExistingOpenBoundaryProvider",
                             evidence=tuple(evid), status=HypothesisStatus.PROPOSED)
    ctx = PolygonContext(osm_name=name, centroid_lng=pt.x, centroid_lat=pt.y)
    _, disposition, consumers = pipe.run(
        OntologyType.RESIDENTIAL_COMPOUND, hyp, polygon_context=ctx)
    chain = gaz.chains_for(name)[:1]
    results.append({
        "name": name or None,
        "disposition": disposition.value,
        "district": chain[0].district if chain else "",
        "area_m2": round(g.area * 111320 * 111320),
        "lat": round(pt.y, 5), "lng": round(pt.x, 5),
        "ready": sum(1 for v in consumers.values() if v.value == "READY"),
        "wkt": g.wkt,
    })

import collections
print(f"裁决分布: {dict(collections.Counter(r['disposition'] for r in results))} "
      f"({time.time() - t0:.1f}s)")
keep_disp = ("TRUSTED", "PROVISIONAL", "UNRESOLVED")
keep = [r for r in results if r["disposition"] in keep_disp]
print(f"可信+待定: {len(keep)}/{len(results)}, REJECTED 农地误标 {sum(1 for r in results if r['disposition']=='REJECTED')}")

os.makedirs("outputs/huilongguan_demo", exist_ok=True)
with open("outputs/huilongguan_demo/validation_results.json", "w") as f:
    json.dump([{k: v for k, v in r.items() if k != "wkt"} for r in results],
              f, ensure_ascii=False, indent=1)

import shapely.wkt as sw
feats = []
for r in results:
    geom = sw.loads(r.pop("wkt"))
    feats.append({"type": "Feature", "geometry": geom.__geo_interface__, "properties": r})
with open("outputs/huilongguan_demo/huilongguan_validated.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
print(f"saved {len(feats)} features -> huilongguan_validated.geojson")

for r in results[:6]:
    print(f"  {str(r['name'])[:16]:18s} {r['disposition']:12s} "
          f"{r['district'] or '-':4s} {r['area_m2']:>9,}m² ready={r['ready']}")
