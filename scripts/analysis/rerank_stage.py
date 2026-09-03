"""
Standalone Cross-Encoder Rerank Stage (runs OUTSIDE the main pipeline process).

Why a separate process: the reranker weights (~544 MB int8) must never co-reside
in RAM with the bi-encoder ONNX session + the big pandas/shapely dataframes held
by the main pipeline. On a memory-constrained box (>9 GB swap in use) that caused
swap thrash / OOM. Running this as its own OS process -- launched by run.py AFTER
the main pipeline has released all its large objects -- keeps the peak footprint
to just the model + a light CSV/Excel re-read.

What it does:
  * reads outputs/entity_relations.csv
  * re-scores every RELATED_ENTITY ("soft") pair with the cross-encoder
  * downgrades score<0.30 pairs to NOT_SAME_ENTITY (shrinks human-review queue)
  * confirms score>=0.85 alias candidates (raises confidence)
  * NEVER touches SIBLING_* / component-conflict isolation (zero-false-merge gate)
  * writes the updated CSV and merges rerank stats into pipeline_summary.json
"""

from __future__ import annotations

import os as _o; from pathlib import Path as _P
_REPO = _P(_o.environ.get('SDI_ROOT') or _P(__file__).resolve().parents[2])

import os
import sys
import json
import time
import argparse
import logging

# OpenMP conflict fix (torch vs onnxruntime) -- harmless here, defensive.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rerank_stage")

DOWNGRADE_THRESHOLD = 0.30
ALIAS_THRESHOLD = 0.85
TIER1_IOU_THRESHOLD = 0.15

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default=str(_REPO / 'data/client_a_sites.xlsx'))
    ap.add_argument("--output-dir", default=os.path.join(PROJECT_ROOT, "outputs"))
    ap.add_argument("--batch-size", type=int, default=128)
    ap.add_argument("--max-length", type=int, default=48,
                    help="max token length; rerank text is short (name|addr|city ~25 tokens), "
                         "so 48 drastically speeds up attention calculation")
    ap.add_argument("--sample", type=int, default=0,
                    help="if >0, run rerank on a stratified sample of N RELATED_ENTITY "
                         "pairs (representative across bge_sim buckets) instead of the "
                         "full set. Used when available RAM cannot hold the model for a "
                         "full 4935-pair pass; the sampled rates are reported directly.")
    args = ap.parse_args()

    out_dir = args.output_dir
    rel_csv = os.path.join(out_dir, "entity_relations.csv")
    summary_json = os.path.join(out_dir, "pipeline_summary.json")

    import pandas as pd
    from src.ingestion.parser import ExcelIngestionParser
    from src.entity_resolution.cross_encoder_reranker import (
        CrossEncoderReranker, build_rerank_text
    )

    t0 = time.time()
    if not CrossEncoderReranker.available():
        logger.error("[rerank] reranker weights not found; aborting stage.")
        return 2

    # 1) Light re-parse of source records (only text fields needed by rerank).
    logger.info("[rerank] re-parsing source records for rerank text ...")
    records = ExcelIngestionParser.parse_file(args.excel)
    records_map = {r.source_record_id: r for r in records}
    del records
    logger.info(f"[rerank] records_map built ({len(records_map)} ids) "
                f"in {time.time()-t0:.1f}s")

    # 2) Read relations, isolate the soft decision region.
    df = pd.read_csv(rel_csv, dtype=str, keep_default_na=False)
    if "rerank_sampled" not in df.columns:
        df["rerank_sampled"] = ""
    full_soft_count = int((df["relation_type"] == "RELATED_ENTITY").sum())
    soft_mask = df["relation_type"] == "RELATED_ENTITY"
    soft_idx = df.index[soft_mask].tolist()
    logger.info(f"[rerank] {full_soft_count} RELATED_ENTITY soft pairs in total "
                f"(of {len(df)} total relations)")

    sampled_mode = False
    if args.sample and args.sample < len(soft_idx):
        # Stratified sampling across bge_sim deciles for representativeness --
        # the full 4935-pair pass needs ~1 GB free RAM headroom which this box
        # (8 GB swap in use from other apps) cannot guarantee; a representative
        # sample still validates the cross-encoder's behaviour and yields
        # directly-reportable downgrade/confirm rates.
        import numpy as np
        try:
            sims = df.loc[soft_idx, "bge_sim"].astype(float)
        except Exception:
            sims = pd.Series([0.5] * len(soft_idx), index=soft_idx)
        bins = np.linspace(0.0, 1.0, 11)  # 10 deciles
        grp = pd.cut(sims, bins=bins, labels=range(10), include_lowest=True)
        rng = np.random.default_rng(42)
        per = max(1, args.sample // 10)
        sampled = []
        for lab in range(10):
            idx = list(grp.index[grp == lab])
            if not idx:
                continue
            take = min(per, len(idx))
            sampled.extend(list(rng.choice(idx, size=take, replace=False)))
        if len(sampled) < args.sample:
            leftover = [i for i in soft_idx if i not in set(sampled)]
            take = min(args.sample - len(sampled), len(leftover))
            if take > 0:
                sampled.extend(list(rng.choice(leftover, size=take, replace=False)))
        soft_idx = sorted(sampled)
        sampled_mode = True
        logger.info(f"[rerank] SAMPLE mode: {len(soft_idx)} pairs across bge_sim deciles")

    if not soft_idx:
        logger.info("[rerank] nothing to rerank.")
        _merge_summary(summary_json, {
            "rerank_enabled": True, "rerank_sampled_mode": sampled_mode,
            "rerank_full_soft_count": full_soft_count, "rerank_soft_pairs": 0,
            "rerank_downgraded_to_not_same": 0, "rerank_alias_confirmed": 0,
            "rerank_elapsed_seconds": round(time.time() - t0, 2),
        })
        return 0

    # 3) Build (query, passage) text pairs.
    text_pairs = []
    for i in soft_idx:
        sa = records_map.get(df.at[i, "subject_record_id"])
        ob = records_map.get(df.at[i, "object_record_id"])
        text_pairs.append((build_rerank_text(sa), build_rerank_text(ob)))

    # 4) Load the cross-encoder and score.
    logger.info("[rerank] loading cross-encoder (int8) ...")
    t_load = time.time()
    reranker = CrossEncoderReranker(batch_size=args.batch_size, max_length=args.max_length)
    logger.info(f"[rerank] model loaded in {time.time()-t_load:.1f}s")

    ce_scores = reranker.rerank_pairs(text_pairs)
    reranker.release()

    # 5) Apply decisions & Tiered Work-Order Classification.
    downgraded = 0
    alias_confirmed = 0
    for i, sc in zip(soft_idx, ce_scores):
        sc = float(sc)
        df.at[i, "cross_encoder_score"] = f"{sc:.4f}"
        df.at[i, "rerank_sampled"] = "1"
        explain = df.at[i, "explain"]
        conf = float(df.at[i, "relation_confidence"] or 0.0)
        if sc < DOWNGRADE_THRESHOLD:
            df.at[i, "relation_type"] = "NOT_SAME_ENTITY"
            df.at[i, "explain"] = (explain + "; " if explain else "") + "CROSS_ENCODER_UNRELATED"
            df.at[i, "relation_confidence"] = f"{min(conf, sc):.4f}"
            downgraded += 1
        elif sc >= ALIAS_THRESHOLD:
            df.at[i, "explain"] = (explain + "; " if explain else "") + "CROSS_ENCODER_ALIAS_CONFIRMED"
            df.at[i, "relation_confidence"] = f"{max(conf, sc):.4f}"
            alias_confirmed += 1

    # 5.1) Compute 3-Tier Classification for ALL pairs in relations table
    tier_levels = []
    action_recs = []
    for idx, row in df.iterrows():
        rel_type = row.get("relation_type", "")
        try:
            iou_val = float(row.get("iou", 0.0) or 0.0)
        except Exception:
            iou_val = 0.0
        try:
            ce_sc = float(row.get("cross_encoder_score", 0.0) or 0.0)
        except Exception:
            ce_sc = 0.0
        try:
            bge_sc = float(row.get("bge_sim", 0.0) or 0.0)
        except Exception:
            bge_sc = 0.0
        try:
            dist_m = float(row.get("distance_m", 9999.0) or 9999.0)
        except Exception:
            dist_m = 9999.0

        # Tier 1: Critical high-risk overlap or strong alias
        if rel_type == "POSSIBLE_MERGE_ERROR" or iou_val >= TIER1_IOU_THRESHOLD or (ce_sc >= ALIAS_THRESHOLD and dist_m < 1500):
            t_level = "TIER_1_CRITICAL"
            t_rec = "高危待复核: 存在真实空间重叠(IoU>=0.15)或高置信度同名实体(CE>=0.85)，可能存在重复建档或多期重叠"
        # Tier 3: Unrelated / Down-graded / Filtered
        elif rel_type in ("NOT_SAME_ENTITY", "SIBLING_DIFFERENT_NUMBER", "SIBLING_DIFFERENT_COURT", "SIBLING_DIFFERENT_AREA") or ce_sc < DOWNGRADE_THRESHOLD or (bge_sc < 0.60 and iou_val == 0):
            t_level = "TIER_3_FILTERED"
            t_rec = "低风险归档: 交叉编码器判定为非同名或属性冲突，已安全降级归档"
        # Tier 2: Standard soft candidate
        else:
            t_level = "TIER_2_STANDARD"
            t_rec = "常规复核: 邻近同名或软关联实体，需人工确认是否为分期、分段或独立小区"

        tier_levels.append(t_level)
        action_recs.append(t_rec)

    df["tier_level"] = tier_levels
    df["action_recommendation"] = action_recs

    # 6) Write back entity_relations.csv
    df.to_csv(rel_csv, index=False, encoding="utf-8-sig")
    logger.info(f"[rerank] wrote {rel_csv}")

    # 7) Export dedicated tiered work orders
    tier_order_cols = [
        "tier_level", "subject_record_id", "subject_name", "object_record_id",
        "object_name", "subject_city", "relation_type", "iou", "distance_m",
        "bge_sim", "cross_encoder_score", "relation_confidence", "explain", "action_recommendation"
    ]
    avail_cols = [c for c in tier_order_cols if c in df.columns]
    work_orders_df = df[avail_cols].sort_values(
        by=["tier_level", "iou", "cross_encoder_score", "bge_sim"],
        ascending=[True, False, False, False]
    )
    work_orders_csv = os.path.join(out_dir, "work_orders_tiered.csv")
    work_orders_df.to_csv(work_orders_csv, index=False, encoding="utf-8-sig")
    logger.info(f"[rerank] exported {len(work_orders_df)} tiered work orders -> {work_orders_csv}")

    t1_count = int((df["tier_level"] == "TIER_1_CRITICAL").sum())
    t2_count = int((df["tier_level"] == "TIER_2_STANDARD").sum())
    t3_count = int((df["tier_level"] == "TIER_3_FILTERED").sum())

    _merge_summary(summary_json, {
        "rerank_enabled": True,
        "rerank_sampled_mode": sampled_mode,
        "rerank_full_soft_count": full_soft_count,
        "rerank_soft_pairs": len(soft_idx),
        "rerank_downgraded_to_not_same": downgraded,
        "rerank_alias_confirmed": alias_confirmed,
        "tier_1_critical_count": t1_count,
        "tier_2_standard_count": t2_count,
        "tier_3_filtered_count": t3_count,
        "rerank_elapsed_seconds": round(time.time() - t0, 2),
    })

    logger.info(f"[rerank] DONE in {time.time()-t0:.1f}s -> "
                f"{downgraded} downgraded to NOT_SAME, {alias_confirmed} alias-confirmed. "
                f"Tiers: T1(Critical)={t1_count}, T2(Standard)={t2_count}, T3(Filtered)={t3_count}")
    return 0

def _merge_summary(path: str, patch: dict) -> None:
    summary = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                summary = json.load(f)
        except Exception:
            summary = {}
    summary.update(patch)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
