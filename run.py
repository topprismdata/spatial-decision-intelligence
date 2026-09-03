"""
Main Entrypoint for executing the Residential Spatial Entity Platform Pipeline.
"""
import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[0])

import os
import sys

# OpenMP runtime conflict fix: torch's bundled libomp clashes with onnxruntime's
# OpenMP, which otherwise paralyzes onnxruntime threading (embedding ~15x slower).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.pipelines.batch_pipeline import BatchPipeline

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Residential Spatial Entity Platform pipeline")
    ap.add_argument("--input", default=None,
                    help="source Excel (sheet1). default: data/client_a_sites.xlsx, "
                         "falling back to data/sample/sample_sites.xlsx (see docs/DATA.md)")
    ap.add_argument("--output", default=os.path.join(PROJECT_ROOT, "outputs"))
    args = ap.parse_args()
    excel_file = args.input or next(
        (p for p in (str(_REPO / 'data/client_a_sites.xlsx'),
                     str(_REPO / 'data/sample/sample_sites.xlsx')) if os.path.exists(p)),
        str(_REPO / 'data/client_a_sites.xlsx'))
    out_dir = args.output
    print(f"Starting Spatial Entity Resolution Pipeline on: {excel_file}")
    # do_rerank=False: the cross-encoder rerank runs in a SEPARATE process
    # (rerank_stage.py) after this one exits, so the 544 MB model never co-resides
    # in RAM with the bi-encoder ONNX session + big dataframes (avoids swap/OOM).
    pipeline = BatchPipeline(excel_path=excel_file, output_dir=out_dir, do_rerank=False)
    stats = pipeline.run()
    print("Execution Summary:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
