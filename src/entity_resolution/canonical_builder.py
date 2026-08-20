"""
Module M5: Semantic-Aware Canonical Entity Builder.
Attaches accurate entity types, semantic attributes, and versioned geometries.
"""

from typing import List, Dict, Tuple, Any
from src.domain.models import SourceRecord, CanonicalEntity, GeometryVersion, GeometrySourceType, QAResult, EntityType
from src.entity_resolution.pair_features import parse_chinese_community_semantics


class CanonicalBuilder:
    """Builds CanonicalEntity and GeometryVersion records with accurate semantics."""

    @staticmethod
    def build_canonical_entities(
        clusters: List[List[str]],
        records_map: Dict[str, SourceRecord],
        norm_wkts: Dict[str, str],
        qa_results_map: Dict[str, QAResult]
    ) -> Tuple[List[CanonicalEntity], List[GeometryVersion]]:
        canonical_entities: List[CanonicalEntity] = []
        geometry_versions: List[GeometryVersion] = []

        for idx, cluster_ids in enumerate(clusters):
            canon_id = f"COMM_{idx+1:06d}"
            cluster_recs = [records_map[cid] for cid in cluster_ids]

            # 1. Consensus / Best Canonical Name
            best_rec = max(cluster_recs, key=lambda r: len(r.name_raw.strip()))
            canon_name = best_rec.name_raw.strip()

            # Parse semantic attributes and entity type
            sem = parse_chinese_community_semantics(best_rec)

            # Administrative fields
            province = best_rec.province_raw
            city = best_rec.city_raw
            district = best_rec.district_raw
            street = best_rec.street_raw

            # 2. Build Geometry Versions for all members in cluster
            best_geo_ver_id = None
            best_geo_score = -1.0

            for rec in cluster_recs:
                wkt_val = norm_wkts.get(rec.source_record_id)
                qa_res = qa_results_map.get(rec.source_record_id)
                qa_score = qa_res.score if qa_res else 0.5

                if wkt_val:
                    geo_ver_id = f"GEO_{canon_id}_{rec.source_record_id}"
                    geo_ver = GeometryVersion(
                        geometry_version_id=geo_ver_id,
                        canonical_entity_id=canon_id,
                        geometry_wkt=wkt_val,
                        geometry_source=GeometrySourceType.SOURCE_NORMALIZED,
                        source_record_id=rec.source_record_id,
                        coordinate_reference="WGS84",
                        geometry_status="ACTIVE",
                        geometry_confidence=qa_score,
                        created_by="SYSTEM"
                    )
                    geometry_versions.append(geo_ver)

                    if qa_score > best_geo_score:
                        best_geo_score = qa_score
                        best_geo_ver_id = geo_ver_id

            # 3. Construct CanonicalEntity
            canon_entity = CanonicalEntity(
                canonical_entity_id=canon_id,
                canonical_name=canon_name,
                province=province,
                city=city,
                district=district,
                street=street,
                entity_type=sem["entity_type"],
                entity_status="ACTIVE",
                canonical_geometry_version_id=best_geo_ver_id,
                identity_confidence=0.98 if len(cluster_ids) > 1 else 0.92,
                member_source_record_ids=cluster_ids,
                semantic_attributes=sem,
                metadata={
                    "member_count": len(cluster_ids),
                    "best_geometry_score": best_geo_score,
                    "is_non_residential": sem["entity_type"] in [EntityType.NON_RESIDENTIAL_COMMERCIAL, EntityType.NON_RESIDENTIAL_FACILITY]
                }
            )
            canonical_entities.append(canon_entity)

        return canonical_entities, geometry_versions
