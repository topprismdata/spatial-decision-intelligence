"""
Hybrid Pair Scorer: structured component matching (hard gate) fused with
BGE dense similarity (residual semantic signal).

Architecture (per Ditto / DeepMatcher / Magellan):
  Stage 1 (recall):  BGE bi-encoder identifies candidate pairs        [elsewhere]
  Stage 2 (decision):
    2a. Component gate  — typed-attribute exact-match conflict forces a
                           SIBLING relation (embedding-blindness-proof).
    2b. BGE rerank      — for pairs with NO component conflict, the dense
                           similarity resolves residual aliasing (e.g.
                           和平西苑 vs 和平街西苑) that needs token interaction.
The component gate is evaluated FIRST; BGE only decides when the structure
is silent. This is the principled fix for "embedding insensitive to numeric
suffixes", not a per-case regex patch.
"""

from typing import Dict, Any
from src.domain.models import RelationType, EntityRelation, SourceRecord


class PairScorer:
    """Computes semantic-grounded entity relation types and exact merge boundaries."""

    @staticmethod
    def score_pair(rec_a: SourceRecord, rec_b: SourceRecord, feats: Dict[str, Any]) -> EntityRelation:
        dist = feats["centroid_dist_meters"]
        iou = feats["iou"]
        inter_min = feats["intersection_over_min"]
        name_sim = feats["name_sim"]
        exact_name = feats["exact_name_match"]
        base_exact = feats["base_exact"]
        base_sim = feats["base_sim"]
        has_num_conflict = feats["has_number_or_sub_conflict"]
        is_hierarchical = feats["is_hierarchical_phase"]
        district_match = feats["district_match"]
        bge_sim = feats.get("bge_sim", 0.0)

        sem_a = feats["sem_a"]
        sem_b = feats["sem_b"]

        # Component-aware signals (DeepMatcher attribute matrix)
        comp_conflict_type = feats.get("comp_conflict_type")
        comp_sibling_rel = feats.get("comp_sibling_rel")
        comp_base_sim = feats.get("comp_base_sim", base_sim)

        prob = 0.0
        conf = 0.95
        rel_type = RelationType.NOT_SAME_ENTITY
        explains = []

        # Rule 0: Large spatial separation (> 2000m)
        if dist > 2000:
            rel_type = RelationType.NOT_SAME_ENTITY
            prob = 0.0
            conf = 0.99
            explains.append(f"空间距离过大 ({dist:.0f}m > 2000m)，判定为不同实体。")

        # Rule 1 (STRUCTURAL GATE): a typed-attribute conflict (same discriminator
        # type present in BOTH records with DIFFERENT value) => independent sibling
        # entity. Driven by the component schema, not hand-written per-type rules.
        # Covers 号院/门牌/期/分区/里条/街坊/场/小区号 — embedding-blindness-proof.
        elif comp_conflict_type is not None and comp_sibling_rel is not None and dist <= 1500:
            rel_type = RelationType(comp_sibling_rel)
            prob = 0.0  # STRICTLY NO MERGE
            conf = 0.99
            explains.append(
                f"结构化组件冲突：同基名但[{comp_conflict_type}]类型编号不同，"
                f"属独立相邻实体（兄弟关系），精确隔离，绝不合并。"
            )

        # Rule 2: Hierarchical Whole-to-Phase (e.g. 万科城市花园 vs 万科城市花园二期)
        elif is_hierarchical and dist <= 1000:
            if sem_a["phase"] or sem_a["subarea"]:
                rel_type = RelationType.PHASE_TO_WHOLE
            else:
                rel_type = RelationType.WHOLE_TO_PHASE
            prob = 0.0  # STRICTLY NO MERGE (Hierarchical link only)
            conf = 0.92
            explains.append(f"整区与分期层级从属关系 ({rec_a.name_raw} <-> {rec_b.name_raw})，建立上下级关联，各自为独立实体。")

        # Rule 3: True Duplicate / Multi-Version of SAME ENTITY
        # Structured gate already excluded any numeric/area conflict, so a match
        # here is safe. BGE provides the residual semantic confirmation.
        elif district_match and not has_num_conflict and dist <= 200:
            if exact_name or (base_exact and name_sim >= 0.80 and bge_sim >= 0.88):
                # 门牌信息完备性检查: 单侧有门牌号意味着街道级记录 vs 门牌级记录
                num_a = sem_a["court_no"] or sem_a["house_no"]
                num_b = sem_b["court_no"] or sem_b["house_no"]
                if (num_a is None) != (num_b is None):
                    rel_type = RelationType.RELATED_ENTITY
                    prob = 0.50
                    conf = 0.60
                    explains.append(
                        f"街道级名称与门牌级名称相近 ({rec_a.name_raw} vs {rec_b.name_raw}, 距离={dist:.1f}m)，"
                        f"单侧缺少门牌号无法确证为同一门牌，降级为人工复核，禁止自动合并。"
                    )
                elif iou >= 0.85:
                    rel_type = RelationType.EXACT_DUPLICATE
                    prob = 0.99
                    conf = 0.98
                    explains.append(f"名称与门牌完全一致，围栏高度重合 (IoU={iou:.2f}, 距离={dist:.1f}m)，判定为完全重复。")
                else:
                    rel_type = RelationType.SAME_ENTITY_ALT_BOUNDARY
                    prob = 0.95
                    conf = 0.92
                    explains.append(f"同一实体在不同来源的多边形版本 (距离={dist:.1f}m, IoU={iou:.2f}, BGE={bge_sim:.3f})，归并为主实体并保留多版本。")
            elif bge_sim >= 0.82:
                rel_type = RelationType.RELATED_ENTITY
                prob = 0.70
                conf = 0.75
                explains.append(
                    f"BGE 语义高度相似 ({bge_sim:.3f}) 且空间相近 ({dist:.1f}m)，疑似同一实体的别名/简称"
                    f" ({rec_a.name_raw} vs {rec_b.name_raw})，但因名称结构不同需人工确认后合并。"
                )
            elif name_sim >= 0.70 or bge_sim >= 0.70:
                rel_type = RelationType.RELATED_ENTITY
                prob = 0.50
                conf = 0.75
                explains.append(f"空间相近 ({dist:.1f}m) 且名称相似 (编辑距离={name_sim:.2f}, BGE={bge_sim:.3f})，推入待人工复核。")

        # Rule 4: Possible Spatial Collision / Merge Error (Different communities overlapping)
        elif (iou >= 0.35 or inter_min >= 0.50) and name_sim < 0.45 and not base_exact:
            rel_type = RelationType.POSSIBLE_MERGE_ERROR
            prob = 0.0  # STRICTLY NO MERGE
            conf = 0.92
            explains.append(f"空间碰撞异常：不同小区围栏发生大面积重叠 (IoU={iou:.2f}, 重叠率={inter_min:.2f})，拦截合并并告警。")

        # Rule 5: Same Name in Different Districts (Homonymous far away)
        elif name_sim >= 0.80 and not district_match:
            rel_type = RelationType.NOT_SAME_ENTITY
            prob = 0.0
            conf = 0.99
            explains.append(f"同城同名但处于不同行政区 ({rec_a.district_raw} vs {rec_b.district_raw})，属于不同实体。")

        # Rule 6: General Spatial Proximity (Related) — BGE residual semantic
        elif dist <= 300 and (name_sim >= 0.60 or bge_sim >= 0.68):
            rel_type = RelationType.RELATED_ENTITY
            if bge_sim >= 0.80:
                prob = 0.65
                explains.append(f"临近且 BGE 语义相似 ({bge_sim:.3f})，优先复核别名可能。")
            else:
                prob = 0.30
                explains.append(f"临近相似实体 ({rec_a.name_raw} ~ {rec_b.name_raw})，距离 {dist:.0f}m，BGE={bge_sim:.3f}。")
            conf = 0.70

        else:
            rel_type = RelationType.NOT_SAME_ENTITY
            prob = 0.0
            conf = 0.95
            explains.append("不属于同一实体。")

        return EntityRelation(
            relation_id=f"REL_{rec_a.source_record_id}_{rec_b.source_record_id}",
            subject_id=rec_a.source_record_id,
            object_id=rec_b.source_record_id,
            relation_type=rel_type,
            same_entity_probability=prob,
            relation_confidence=conf,
            directional=True if rel_type in [RelationType.WHOLE_TO_PHASE, RelationType.PHASE_TO_WHOLE] else False,
            explain_codes=explains,
            metrics=feats,
            decision_status="AUTO_DECIDED" if conf >= 0.90 else "REVIEW_REQUIRED"
        )
