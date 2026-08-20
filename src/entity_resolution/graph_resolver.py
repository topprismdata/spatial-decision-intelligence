"""
Module M4 (Layer 2): Graph Resolver - Clusters SourceRecords into Canonical Entities.
"""

from typing import List, Dict, Set, Tuple, Any
from src.domain.models import SourceRecord, EntityRelation, RelationType


class GraphResolver:
    """Solves connected components and validates transitivity/administrative constraints."""

    @staticmethod
    def resolve_clusters(
        records: List[SourceRecord],
        relations: List[EntityRelation]
    ) -> Tuple[List[List[str]], List[Dict[str, Any]]]:
        """
        Returns:
            clusters: List of SourceRecord ID lists (each representing a Canonical Entity)
            conflicts: List of detected transitivity or cluster conflicts
        """
        adj: Dict[str, Set[str]] = {r.source_record_id: set() for r in records}
        record_map = {r.source_record_id: r for r in records}

        # Add edges for EXACT_DUPLICATE and SAME_ENTITY_ALT_BOUNDARY
        for rel in relations:
            if rel.relation_type in [RelationType.EXACT_DUPLICATE, RelationType.SAME_ENTITY_ALT_BOUNDARY]:
                # Verify administrative consistency before merging
                rec_a = record_map[rel.subject_id]
                rec_b = record_map[rel.object_id]
                if rec_a.city_raw == rec_b.city_raw:
                    adj[rel.subject_id].add(rel.object_id)
                    adj[rel.object_id].add(rel.subject_id)

        # Connected components
        visited: Set[str] = set()
        clusters: List[List[str]] = []
        conflicts: List[Dict[str, Any]] = []

        for r_id in adj:
            if r_id not in visited:
                cluster = []
                queue = [r_id]
                visited.add(r_id)

                while queue:
                    curr = queue.pop(0)
                    cluster.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)

                # Transitivity & sanity checks on cluster
                if len(cluster) > 1:
                    # Check if all members belong to the same city
                    cities = {record_map[cid].city_raw for cid in cluster}
                    if len(cities) > 1:
                        conflicts.append({
                            "type": "CITY_CONFLICT",
                            "cluster": cluster,
                            "cities": list(cities)
                        })

                clusters.append(sorted(cluster))

        return clusters, conflicts
