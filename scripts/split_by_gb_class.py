"""Split a GeoJSON into per-GB50137-class files.

Usage: python3 scripts/split_by_gb_class.py <in.geojson> <out_dir>

Class is parsed from the feature label prefix "[CODE] ...". Features without
a recognizable code go to "_uncategorized". Writes <out_dir>/<CODE>.geojson
and prints per-class counts.
"""

import json
import os
import re
import sys

CODE_RE = re.compile(r"^\s*\[([A-Z]{1,3}\d?)]")

# GB50137 code -> Chinese name (for the per-file title property)
CLASS_NAMES = {
    "R": "居住用地", "B1": "商业服务业设施用地", "B2": "商务用地",
    "M": "工业用地", "S": "道路与交通设施用地", "A3": "教育科研用地",
    "A4": "体育用地", "A5": "医疗卫生与社会福利用地", "G": "绿地与广场用地",
    "AGR": "农林用地", "U": "公用设施用地",
}


def main() -> None:
    src, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    fc = json.load(open(src, encoding="utf-8"))
    groups: dict = {}
    for f in fc["features"]:
        label = f.get("properties", {}).get("label", "")
        m = CODE_RE.match(label)
        code = m.group(1) if m else "_uncategorized"
        props = dict(f.get("properties", {}))
        props["gb_class"] = code
        props["gb_class_name"] = CLASS_NAMES.get(code, "")
        groups.setdefault(code, []).append(
            {"type": "Feature", "properties": props, "geometry": f["geometry"]})

    for code, feats in sorted(groups.items()):
        out = {"type": "FeatureCollection",
               "name": f"GB50137 {code} {CLASS_NAMES.get(code, '未分类')}",
               "features": feats}
        path = os.path.join(out_dir, f"{code}.geojson")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        print(f"{code:15s} {len(feats):6d}  -> {path}")


if __name__ == "__main__":
    main()
