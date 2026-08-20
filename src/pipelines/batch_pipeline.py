"""
End-to-End Batch Pipeline with Deep Semantic Disambiguation and Non-Residential Entity Classification.
"""

import os
import json
import time
import pandas as pd
from typing import Dict, Any, List
from shapely import wkt

from src.domain.models import (
    SourceRecord,
    CoordinateAssessment,
    QAResult,
    EntityRelation,
    CanonicalEntity,
    GeometryVersion,
    RelationType,
    EntityType
)
from src.ingestion.parser import ExcelIngestionParser
from src.ingestion.profiler import DatasetProfiler
from src.coordinate.assessment import CoordinateIntelligence
from src.geometry.validation import GeometryQAEngine
from src.entity_resolution.candidate_retrieval import CandidateRetrievalEngine
from src.entity_resolution.embedding import EmbeddingService
from src.entity_resolution.pair_features import PairFeatureExtractor, parse_chinese_community_semantics
from src.entity_resolution.pair_scorer import PairScorer
from src.entity_resolution.graph_resolver import GraphResolver
from src.entity_resolution.canonical_builder import CanonicalBuilder


class BatchPipeline:
    """Orchestrates semantic-aware spatial entity resolution and governance."""

    def __init__(self, excel_path: str, output_dir: str = "outputs", do_rerank: bool = False):
        self.excel_path = excel_path
        self.output_dir = output_dir
        # Inline rerank is OFF by default: the 544 MB cross-encoder is executed in
        # a *separate* OS process (see run.py -> rerank_stage.py) so it never
        # co-resides in RAM with the bi-encoder ONNX session + big dataframes on a
        # memory-constrained box (avoids swap thrash / OOM).
        self.do_rerank = do_rerank
        os.makedirs(output_dir, exist_ok=True)

    def run(self) -> Dict[str, Any]:
        start_time = time.time()
        print(f"=== [Step 0] Ingestion & M0 Profiler ===")
        records = ExcelIngestionParser.parse_file(self.excel_path)
        print(f"Loaded {len(records)} immutable SourceRecords.")

        health_report = DatasetProfiler.profile(records)
        with open(os.path.join(self.output_dir, "dataset_health_report.json"), "w", encoding="utf-8") as f:
            json.dump(health_report, f, indent=2, ensure_ascii=False)

        print(f"=== [Step 1 & 2] M1 Coordinate Intelligence & M2 Geometry QA & Semantic Parsing ===")
        coord_assessments: Dict[str, CoordinateAssessment] = {}
        norm_coords: Dict[str, tuple] = {}
        norm_wkts: Dict[str, str] = {}
        norm_geoms: Dict[str, Any] = {}
        qa_results: Dict[str, QAResult] = {}
        qa_features_map: Dict[str, Dict[str, Any]] = {}
        semantic_map: Dict[str, Dict[str, Any]] = {}

        for r in records:
            # Semantic parsing
            sem = parse_chinese_community_semantics(r)
            semantic_map[r.source_record_id] = sem

            # Coordinate assessment
            coord_eval, n_lng, n_lat, n_wkt = CoordinateIntelligence.assess_and_normalize(r)
            coord_assessments[r.source_record_id] = coord_eval
            norm_coords[r.source_record_id] = (n_lng, n_lat)

            # Geometry QA
            qa_res, clean_wkt, feats = GeometryQAEngine.validate_and_extract_features(r.source_record_id, n_wkt)
            qa_results[r.source_record_id] = qa_res
            qa_features_map[r.source_record_id] = feats
            norm_wkts[r.source_record_id] = clean_wkt

            if clean_wkt:
                try:
                    norm_geoms[r.source_record_id] = wkt.loads(clean_wkt)
                except Exception:
                    norm_geoms[r.source_record_id] = None

        print(f"Coordinate, Geometry QA & Semantics processed for {len(records)} records.")

        # BGE dense embedding (name|address composite)
        try:
            emb_vecs, emb_ids = EmbeddingService.embed_records(records)
            print(f"BGE embeddings computed: {emb_vecs.shape[0]} records x {emb_vecs.shape[1]} dims.")
            bge_enabled = True
        except Exception as e:
            print(f"[WARN] BGE embedding unavailable, falling back to lexical-only: {e}")
            bge_enabled = False

        # Summary of Entity Types
        type_counts = pd.Series([s["entity_type"].value for s in semantic_map.values()]).value_counts().to_dict()
        print(f"Entity Type Distribution: {type_counts}")

        print(f"=== [Step 3] M3 Candidate Retrieval ===")
        candidate_pairs = CandidateRetrievalEngine.retrieve_candidate_pairs(
            records=records,
            norm_geoms=norm_geoms,
            norm_coords=norm_coords,
            buffer_degrees=0.003
        )
        print(f"Retrieved {len(candidate_pairs)} candidate pairs for semantic evaluation.")

        # Vectorized BGE cosine for all candidate pairs
        if bge_enabled:
            pair_ids = [(a.source_record_id, b.source_record_id) for a, b in candidate_pairs]
            bge_sims = EmbeddingService.cosine_bulk(pair_ids)
        else:
            bge_sims = [0.0] * len(candidate_pairs)

        print(f"=== [Step 4] M4 Semantic Pair Scoring & Relation Classification ===")
        relations: List[EntityRelation] = []
        for pair_idx, (rec_a, rec_b) in enumerate(candidate_pairs):
            geom_a = norm_geoms.get(rec_a.source_record_id)
            geom_b = norm_geoms.get(rec_b.source_record_id)
            c_a = norm_coords[rec_a.source_record_id]
            c_b = norm_coords[rec_b.source_record_id]
            sem_a = semantic_map[rec_a.source_record_id]
            sem_b = semantic_map[rec_b.source_record_id]

            feats = PairFeatureExtractor.extract_features(rec_a, rec_b, geom_a, geom_b, c_a, c_b, sem_a, sem_b, float(bge_sims[pair_idx]))
            rel = PairScorer.score_pair(rec_a, rec_b, feats)
            if rel.relation_type != RelationType.NOT_SAME_ENTITY:
                relations.append(rel)

        print(f"Identified {len(relations)} meaningful spatial/semantic entity relations.")

        # === [Step 4.5] Cross-Encoder Rerank (Ditto precision stage) ===
        # bi-encoder (BGE, ONNX) did cheap recall; this cross-encoder re-scores the
        # SOFT decision region (RELATED_ENTITY) to (a) downgrade clearly-unrelated
        # pairs to NOT_SAME_ENTITY (shrinks human-review queue, conservative) and
        # (b) confirm high-similarity alias candidates (raises confidence, still
        # routed to human review). It NEVER touches SIBLING_* / component-conflict
        # isolation -- those are hard gates (zero-false-merge red line).
        #
        # NOTE: executed out-of-process by run.py (rerank_stage.py) when do_rerank
        # is False here, to keep the 544 MB model out of this process's RAM.
        rerank_stats = {"enabled": False, "soft_pairs": 0, "downgraded": 0, "alias_confirmed": 0}
        if self.do_rerank:
            records_map = {r.source_record_id: r for r in records}
            try:
                from src.entity_resolution.cross_encoder_reranker import (
                    CrossEncoderReranker, build_rerank_text
                )
                if CrossEncoderReranker.available():
                    soft = [rel for rel in relations if rel.relation_type == RelationType.RELATED_ENTITY]
                    rerank_stats["soft_pairs"] = len(soft)
                    if soft:
                        reranker = CrossEncoderReranker(batch_size=64)
                        text_pairs = [
                            (build_rerank_text(records_map[rel.subject_id]),
                             build_rerank_text(records_map[rel.object_id]))
                            for rel in soft
                        ]
                        ce_scores = reranker.rerank_pairs(text_pairs)
                        for rel, sc in zip(soft, ce_scores):
                            rel.metrics["cross_encoder_score"] = round(float(sc), 4)
                            if sc < 0.30:
                                rel.relation_type = RelationType.NOT_SAME_ENTITY
                                rel.explain_codes.append("CROSS_ENCODER_UNRELATED")
                                rel.relation_confidence = round(min(rel.relation_confidence, float(sc)), 4)
                                rerank_stats["downgraded"] += 1
                            elif sc >= 0.85:
                                rel.explain_codes.append("CROSS_ENCODER_ALIAS_CONFIRMED")
                                rel.relation_confidence = round(max(rel.relation_confidence, float(sc)), 4)
                                rerank_stats["alias_confirmed"] += 1
                        reranker.release()
                        rerank_stats["enabled"] = True
                        print(f"Cross-encoder rerank applied: {len(soft)} soft pairs -> "
                              f"{rerank_stats['downgraded']} downgraded to NOT_SAME, "
                              f"{rerank_stats['alias_confirmed']} alias-confirmed.")
                    else:
                        print("Cross-encoder rerank: no RELATED_ENTITY pairs to rerank.")
                else:
                    print("[WARN] reranker weights unavailable; skipping cross-encoder stage.")
            except Exception as e:
                print(f"[WARN] cross-encoder rerank failed, continuing without it: {e}")

        print(f"=== [Step 5] M4 Graph Resolver & M5 Canonical Entity Builder ===")
        records_map = {r.source_record_id: r for r in records}
        clusters, conflicts = GraphResolver.resolve_clusters(records, relations)
        print(f"Resolved {len(records)} records into {len(clusters)} Canonical Communities (Cluster Conflicts: {len(conflicts)}).")

        canonical_entities, geometry_versions = CanonicalBuilder.build_canonical_entities(
            clusters=clusters,
            records_map=records_map,
            norm_wkts=norm_wkts,
            qa_results_map=qa_results
        )

        print(f"Generated {len(canonical_entities)} CanonicalEntity records and {len(geometry_versions)} GeometryVersion records.")

        print(f"=== [Step 6] Exporting Data Deliverables ===")
        # 1. Canonical Entities Table
        canon_rows = []
        for ce in canonical_entities:
            canon_rows.append({
                "canonical_entity_id": ce.canonical_entity_id,
                "canonical_name": ce.canonical_name,
                "entity_type": ce.entity_type.value,
                "is_non_residential": ce.metadata.get("is_non_residential", False),
                "province": ce.province,
                "city": ce.city,
                "district": ce.district,
                "street": ce.street,
                "base_name": ce.semantic_attributes.get("base_name"),
                "court_no": ce.semantic_attributes.get("court_no"),
                "house_no": ce.semantic_attributes.get("house_no"),
                "phase": ce.semantic_attributes.get("phase"),
                "subarea": ce.semantic_attributes.get("subarea"),
                "member_count": ce.metadata.get("member_count", 1),
                "identity_confidence": ce.identity_confidence,
                "active_geometry_version_id": ce.canonical_geometry_version_id,
                "best_geometry_score": ce.metadata.get("best_geometry_score", 0.0),
                "member_source_record_ids": ",".join(ce.member_source_record_ids)
            })
        df_canon = pd.DataFrame(canon_rows)
        df_canon.to_csv(os.path.join(self.output_dir, "canonical_entities.csv"), index=False, encoding="utf-8-sig")

        # 2. Entity Relations Table
        rel_rows = []
        for rel in relations:
            rec_a = records_map[rel.subject_id]
            rec_b = records_map[rel.object_id]
            rel_rows.append({
                "relation_id": rel.relation_id,
                "subject_record_id": rel.subject_id,
                "subject_name": rec_a.name_raw,
                "subject_type": semantic_map[rel.subject_id]["entity_type"].value,
                "subject_city": rec_a.city_raw,
                "object_record_id": rel.object_id,
                "object_name": rec_b.name_raw,
                "object_type": semantic_map[rel.object_id]["entity_type"].value,
                "object_city": rec_b.city_raw,
                "relation_type": rel.relation_type.value,
                "same_entity_probability": rel.same_entity_probability,
                "relation_confidence": rel.relation_confidence,
                "distance_m": rel.metrics.get("centroid_dist_meters", 0.0),
                "iou": rel.metrics.get("iou", 0.0),
                "bge_sim": rel.metrics.get("bge_sim", 0.0),
                "cross_encoder_score": rel.metrics.get("cross_encoder_score", 0.0),
                "intersection_over_min": rel.metrics.get("intersection_over_min", 0.0),
                "explain": "; ".join(rel.explain_codes),
                "decision_status": rel.decision_status
            })
        df_rel = pd.DataFrame(rel_rows)
        df_rel.to_csv(os.path.join(self.output_dir, "entity_relations.csv"), index=False, encoding="utf-8-sig")

        # 3. QA Issues Table
        qa_rows = []
        for r in records:
            qa = qa_results[r.source_record_id]
            coord = coord_assessments[r.source_record_id]
            feats = qa_features_map[r.source_record_id]
            sem = semantic_map[r.source_record_id]
            if qa.issues or coord.notes or qa.score < 1.0 or sem["entity_type"] != EntityType.RESIDENTIAL_COMMUNITY:
                qa_rows.append({
                    "source_record_id": r.source_record_id,
                    "name": r.name_raw,
                    "entity_type": sem["entity_type"].value,
                    "city": r.city_raw,
                    "district": r.district_raw,
                    "coord_status": coord.coordinate_status.value,
                    "delta_lng": coord.delta_lng,
                    "delta_lat": coord.delta_lat,
                    "geom_qa_score": qa.score,
                    "geom_decision": qa.decision,
                    "area_m2": feats.get("area_m2", 0.0),
                    "compactness": feats.get("compactness", 0.0),
                    "aspect_ratio": feats.get("aspect_ratio", 1.0),
                    "qa_issues": "; ".join(qa.issues),
                    "coord_notes": "; ".join(coord.notes)
                })
        df_qa = pd.DataFrame(qa_rows)
        df_qa.to_csv(os.path.join(self.output_dir, "qa_issues_report.csv"), index=False, encoding="utf-8-sig")

        elapsed = time.time() - start_time
        summary_stats = {
            "elapsed_seconds": round(elapsed, 2),
            "total_source_records": len(records),
            "entity_type_distribution": type_counts,
            "canonical_entities_created": len(canonical_entities),
            "geometry_versions_created": len(geometry_versions),
            "merged_clusters_count": sum(1 for ce in canonical_entities if ce.metadata.get("member_count", 1) > 1),
            "total_relations_detected": len(relations),
            "relation_type_breakdown": pd.Series([r.relation_type.value for r in relations]).value_counts().to_dict(),
            "rerank_enabled": rerank_stats["enabled"],
            "rerank_soft_pairs": rerank_stats["soft_pairs"],
            "rerank_downgraded_to_not_same": rerank_stats["downgraded"],
            "rerank_alias_confirmed": rerank_stats["alias_confirmed"],
            "invalid_topology_healed_count": sum(1 for qa in qa_results.values() if "TOPOLOGY_AUTO_HEALED" in qa.issues),
            "point_reconstructed_from_poly_count": sum(1 for c in coord_assessments.values() if c.coordinate_status.value == "SYSTEMATIC_OFFSET"),
            "crs_conflict_aligned_count": sum(1 for c in coord_assessments.values() if c.coordinate_status.value == "POINT_POLYGON_CRS_CONFLICT")
        }

        with open(os.path.join(self.output_dir, "pipeline_summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary_stats, f, indent=2, ensure_ascii=False)

        print(f"Pipeline finished in {elapsed:.2f}s.")
        return summary_stats
