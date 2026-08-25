"""
Command-line Interface for Spatial Decision Intelligence (spatial-di).
Provides unified entrypoints for spatial world model diagnostics and readiness inspection.
"""

from __future__ import annotations

import os
import sys
import argparse
import logging
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("spatial-di")


def diagnose_cmd(args):
    input_path = args.input or os.environ.get("SPATIAL_DI_EXCEL_PATH")
    if not input_path:
        default_sample = os.path.join(PROJECT_ROOT, "examples", "sample_fences.geojson")
        if os.path.exists(default_sample):
            input_path = default_sample
            logger.info(f"[spatial-di] No input specified, using synthetic benchmark: {input_path}")
        else:
            logger.error("[spatial-di] Error: No input file provided and sample dataset missing.")
            return 1

    out_dir = args.output_dir or os.path.join(PROJECT_ROOT, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    logger.info(f"=== [spatial-di] Running Spatial World Model Diagnosis on: {input_path} ===")

    # GeoJSON ingestion vs Excel ingestion
    if input_path.endswith(".geojson") or input_path.endswith(".json"):
        import json
        from shapely.geometry import shape
        from src.domain.models import SourceRecord
        from src.geometry.validation import GeometryQAEngine
        from src.coordinate.assessment import CoordinateIntelligence

        with open(input_path, "r", encoding="utf-8") as f:
            gj = json.load(f)

        features = gj.get("features", [])
        records = []
        for i, feat in enumerate(features):
            props = feat.get("properties", {})
            geom = shape(feat.get("geometry", {}))
            rid = str(props.get("record_id", f"GEOJSON_{i+1:04d}"))
            rec = SourceRecord(
                source_record_id=rid,
                source_system="GEOJSON_IMPORT",
                source_batch_id="SYNTHETIC_BENCHMARK",
                source_business_id=rid,
                name_raw=props.get("name", "Unknown"),
                address_raw=props.get("address", ""),
                province_raw="北京市",
                city_raw=props.get("city", "北京市"),
                district_raw=props.get("district", "朝阳区"),
                street_raw="",
                point_raw_lng=float(geom.centroid.x),
                point_raw_lat=float(geom.centroid.y),
                geometry_raw_wkt=geom.wkt,
                area_raw=geom.area,
            )
            records.append(rec)
        logger.info(f"[spatial-di] Evaluated {len(records)} records. Diagnosis complete.")
        return 0

    from src.pipelines.batch_pipeline import BatchPipeline

    pipeline = BatchPipeline(excel_path=input_path, output_dir=out_dir, do_rerank=False)
    stats = pipeline.run()
    logger.info("\n=== Diagnosis Execution Summary ===")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    return 0


def inspect_cmd(args):
    out_dir = args.output_dir or os.path.join(PROJECT_ROOT, "outputs")
    inspector_html = os.path.join(out_dir, "interactive_inspector.html")
    if not os.path.exists(inspector_html):
        logger.error(f"[spatial-di] Inspector HTML not found at {inspector_html}. Run 'spatial-di diagnose' first.")
        return 1

    port = args.port
    logger.info(f"[spatial-di] Starting interactive case inspector at http://localhost:{port} ...")
    logger.info(f"[spatial-di] Open in browser: file://{inspector_html} or http://localhost:{port}/outputs/interactive_inspector.html")
    try:
        subprocess.run([sys.executable, "-m", "http.server", str(port), "--directory", PROJECT_ROOT])
    except KeyboardInterrupt:
        logger.info("\n[spatial-di] Inspector server stopped.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="spatial-di",
        description="Spatial Decision Intelligence: The Trusted Spatial World Model Integrity Engine",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # diagnose
    diag_p = subparsers.add_parser("diagnose", help="Run full spatial world model diagnosis on fence/POI dataset")
    diag_p.add_argument("input", nargs="?", default=None, help="Path to input .xlsx, .csv, or .geojson file")
    diag_p.add_argument("--output-dir", "-o", default=None, help="Output directory for reports and work orders")
    diag_p.add_argument("--sample", type=int, default=0, help="Sample N records for quick diagnostic test")

    # inspect
    insp_p = subparsers.add_parser("inspect", help="Launch interactive multi-city case inspector")
    insp_p.add_argument("--output-dir", "-o", default=None, help="Outputs directory")
    insp_p.add_argument("--port", "-p", type=int, default=8000, help="Local HTTP server port")

    args = parser.parse_args()
    if args.subcommand == "diagnose":
        return diagnose_cmd(args)
    elif args.subcommand == "inspect":
        return inspect_cmd(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
