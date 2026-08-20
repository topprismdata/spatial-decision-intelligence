"""
Dense Embedding Service for Entity Resolution (BGE via fastembed/ONNX).
Grounded in: BGE (Xiao et al. 2023), Ditto (Li et al., VLDB 2021), DeepBlocker-style dense blocking.
"""

from typing import List, Dict, Tuple
import numpy as np

try:
    from fastembed import TextEmbedding
    _MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    _model = TextEmbedding(_MODEL_NAME)
except Exception as e:
    _model = None
    _MODEL_LOAD_ERROR = str(e)


class EmbeddingService:
    """Singleton BGE embedding service with L2-normalized vectors and cosine similarity."""

    _instance = None
    _vectors: np.ndarray = None
    _ids: List[str] = None
    _id_to_idx: Dict[str, int] = None

    @classmethod
    def get_model(cls):
        if _model is None:
            raise RuntimeError(f"BGE model unavailable: {_MODEL_LOAD_ERROR}")
        return _model

    @classmethod
    def embed_records(cls, records) -> Tuple[np.ndarray, List[str]]:
        """Embeds name|address composite text for all records. Returns (matrix N x D, ids)."""
        if cls._vectors is not None and cls._ids is not None and len(cls._ids) == len(records):
            return cls._vectors, cls._ids

        texts = [f"{r.name_raw} | {r.address_raw}" for r in records]
        model = cls.get_model()
        vecs = np.array(list(model.embed(texts, batch_size=64)))
        # L2 normalize
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        cls._vectors = vecs / norms
        cls._ids = [r.source_record_id for r in records]
        cls._id_to_idx = {rid: i for i, rid in enumerate(cls._ids)}
        return cls._vectors, cls._ids

    @classmethod
    def cosine(cls, id_a: str, id_b: str) -> float:
        """Cosine similarity between two embedded records."""
        if cls._id_to_idx is None:
            raise RuntimeError("Call embed_records first.")
        i, j = cls._id_to_idx[id_a], cls._id_to_idx[id_b]
        return float(cls._vectors[i] @ cls._vectors[j])

    @classmethod
    def cosine_bulk(cls, pairs: List[Tuple[str, str]]) -> np.ndarray:
        """Vectorized cosine similarity for a list of id pairs."""
        if cls._id_to_idx is None:
            raise RuntimeError("Call embed_records first.")
        idx_a = np.array([cls._id_to_idx[a] for a, _ in pairs])
        idx_b = np.array([cls._id_to_idx[b] for _, b in pairs])
        return np.einsum("ij,ij->i", cls._vectors[idx_a], cls._vectors[idx_b])
