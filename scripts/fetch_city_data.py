"""Download + unpack a Geofabrik 'free shapefile' extract for a new city.

Geofabrik publishes, for every region, a weekly OSM-derived shapefile bundle:
  https://download.geofabrik.de/<continent>/<country>/<region>-latest-free.shp.zip
The `-free.shp.zip` variant contains only AGGREGATED polygon layers
(gis_osm_landuse_a, gis_osm_pois_a, gis_osm_transport_a, ...) — exactly what
city_gb50137.py needs.

IMPORTANT — city vs province granularity: China has city extracts for the
municipalities (beijing, shanghai, tianjin, chongqing) but everything else is
province-level (shaanxi, guangdong, ...). A province extract covers ALL its
cities: pass --bbox later to city_gb50137.py, and verify with
check_city_data.py --stage input before trusting per-city numbers.
(Naming trap: 陕西 = shaanxi (double a); 山西 = shanxi.)

Resume: partial bytes live in <dest>.zip.part with an HTTP Range header, so a
dropped connection is fixed by simply re-running the same command.

Usage:
  python3 scripts/fetch_city_data.py --region shaanxi --dest data/xian_shp
  python3 scripts/fetch_city_data.py --region beijing --dest data/beijing_shp
Then:
  python3 scripts/check_city_data.py --stage input --data-dir data/xian_shp
"""

import argparse
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

_REPO = Path(os.environ.get("SDI_ROOT") or Path(__file__).resolve().parents[1])
BASE = "https://download.geofabrik.de"
REQUIRED_LAYERS = (
    "gis_osm_landuse_a_free_1.shp",
    "gis_osm_pois_a_free_1.shp",
    "gis_osm_transport_a_free_1.shp",
)


def human(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.0f}{unit}"
        nbytes /= 1024
    return f"{nbytes:.1f}TB"


def download(url: str, dest: Path, quiet: bool = False) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "sdi-new-city/1.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
        print(f"RESUME {url} (+{human(have)} already on disk)")
    else:
        print(f"GET {url}")
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        status = r.getcode()
        if have and status != 206:  # server ignored Range -> restart clean
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        with open(part, "ab" if status == 206 else "wb") as f:
            done = have
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if not quiet and total:
                    print(f"\r  {human(done)} / {human(total)} "
                          f"({100 * done / total:.0f}%)", end="", flush=True)
    if not quiet:
        print()
    part.rename(dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--region", required=True,
                    help="Geofabrik region slug (beijing, shaanxi, guangdong, ...). "
                         "Browse https://download.geofabrik.de/asia/china.html if unsure.")
    ap.add_argument("--country", default="china")
    ap.add_argument("--continent", default="asia")
    ap.add_argument("--dest", required=True, help="target dir, e.g. data/xian_shp")
    ap.add_argument("--keep-zip", action="store_true")
    args = ap.parse_args()

    dest = Path(args.dest)
    if not dest.is_absolute():
        dest = _REPO / dest
    url = f"{BASE}/{args.continent}/{args.country}/{args.region}-latest-free.shp.zip"
    zp = dest / f"{args.region}-free.zip"

    if not zp.exists():
        try:
            download(url, zp)
        except Exception as e:
            print(f"FAILED: {e}\nPartial file kept — re-run to resume. "
                  f"Check the region slug at {BASE}/{args.continent}/{args.country}.html")
            sys.exit(2)

    try:
        z = zipfile.ZipFile(zp)
    except zipfile.BadZipFile:
        print("FATAL: downloaded zip is corrupt — delete it and re-run")
        sys.exit(2)
    with z:
        names = z.namelist()
        print(f"zip contains {len(names)} entries")
        missing = [r for r in REQUIRED_LAYERS if r not in names]
        if missing:
            print(f"FATAL: extract lacks required layers: {missing}")
            print(f"       available: {sorted(set(n for n in names if n.endswith('.shp')))}")
            sys.exit(2)
        z.extractall(dest)
    if not args.keep_zip:
        zp.unlink()
    print(f"OK -> {dest}/")
    print(f"next: python3 scripts/check_city_data.py --stage input --data-dir {dest}")


if __name__ == "__main__":
    main()
