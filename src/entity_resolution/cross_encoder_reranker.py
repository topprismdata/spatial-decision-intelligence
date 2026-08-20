"""
Cross-Encoder Reranker (Ditto precision stage).

Implements the "bi-encoder recall + cross-encoder rerank" paradigm from the
entity-resolution literature (Ditto, Sudowoodo, DeepMatcher). The bi-encoder
(BGE small-zh, ONNX) does cheap candidate recall; this cross-encoder
(BAAI/bge-reranker-v2-m3, a multilingual reranker with strong Chinese support)
re-scores the *soft* candidate pairs jointly, capturing fine-grained token-level
interaction that a bi-encoder cosine similarity is blind to (e.g. the
same-name-different-number problem is already neutralised by the component gate;
here the cross-encoder resolves residual alias-vs-unrelated ambiguity).

Design constraints (consistent with the platform's zero-false-merge red line):
  * The reranker ONLY operates on the soft decision region (RELATED_ENTITY /
    low-confidence pairs). It can NEVER override a SIBLING_* / component-conflict
    isolation -- those are hard gates owned by component_matcher + pair_scorer.
  * Downgrading a pair to NOT_SAME_ENTITY is safe (conservative: it reduces
    human-review load without ever creating a false merge).
  * Upgrading a pair to a high-confidence alias candidate still routes to human
    review; it only raises the prioritised queue, never an auto-merge.

Inference runs on CPU with torch; loaded as a single isolated stage so it never
co-resides in memory with the bi-encoder ONNX session during the full pipeline.
"""

from __future__ import annotations

import os
import gc
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)


# Default location of the downloaded BAAI/bge-reranker-v2-m3 weights.
DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "models",
    "bge-reranker-v2-m3",
)


@dataclass
class RerankResult:
    """Per-pair cross-encoder score (symmetric average of both directions)."""
    index: int
    score: float  # sigmoid(logit), range (0, 1); higher = more likely "same / relevant"


class CrossEncoderReranker:
    """Thin wrapper around BAAI/bge-reranker-v2-m3 for pair re-scoring."""

    def __init__(
        self,
        model_dir: str = DEFAULT_MODEL_DIR,
        device: str = "cpu",
        max_length: int = 512,
        batch_size: int = 24,
        quantize: bool = True,
    ):
        if not os.path.exists(os.path.join(model_dir, "model.safetensors")) and \
           not os.path.exists(os.path.join(model_dir, "pytorch_model.bin")):
            raise FileNotFoundError(
                f"reranker weights not found in {model_dir}; run model download first"
            )
        self.model_dir = model_dir
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self.quantize = quantize
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._load()

    def _load(self) -> None:
        import torch  # local import so the heavy dep is only pulled at stage time
        from transformers import AutoTokenizer

        self._torch = torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        try:
            torch.backends.quantized.engine = "qnnpack"
        except Exception:
            pass
        int8_path = os.path.join(self.model_dir, "reranker_int8.pt")
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_dir)

        if self.quantize and os.path.exists(int8_path):
            # int8 dynamic-quantized model (~0.6 GB vs 2.27 GB fp32) -- avoids
            # swap thrash on a 16 GB box. Full model object pickle (weights_only
            # must be False because it contains quantized submodules).
            self._model = torch.load(int8_path, map_location="cpu", weights_only=False)
            logger.info("CrossEncoderReranker loaded INT8 from %s", int8_path)
        else:
            from transformers import AutoModelForSequenceClassification
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
            logger.info("CrossEncoderReranker loaded FP32 from %s", self.model_dir)

        self._model.eval()
        self._model.to(self.device)
        torch.set_grad_enabled(False)
        logger.info("CrossEncoderReranker ready (device=%s)", self.device)

    @classmethod
    def available(cls, model_dir: str = DEFAULT_MODEL_DIR) -> bool:
        return os.path.exists(os.path.join(model_dir, "model.safetensors")) or \
               os.path.exists(os.path.join(model_dir, "pytorch_model.bin"))

    def _score_direction(self, text_pairs: List[Tuple[str, str]]) -> np.ndarray:
        """Score (query, passage) pairs in one direction; returns sigmoid probs."""
        enc = self._tokenizer(
            text_pairs,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        input_ids = enc["input_ids"].to(self.device)
        attention_mask = enc["attention_mask"].to(self.device)
        with self._torch.no_grad():
            logits = self._model(input_ids=input_ids, attention_mask=attention_mask).logits
        logits = logits.float().view(-1)
        probs = self._torch.sigmoid(logits).cpu().numpy()
        return probs

    def rerank_pairs(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """Return symmetric-average rerank scores for each (text_a, text_b) pair.

        Symmetry: rerank is non-symmetric by design (query/passage), so we score
        both (a->b) and (b->a) and average -- appropriate for undirected entity
        matching.
        """
        if not pairs:
            return []
        scores: List[float] = []
        n = len(pairs)
        for start in range(0, n, self.batch_size):
            batch = pairs[start : start + self.batch_size]
            fwd = self._score_direction(batch)
            bwd = self._score_direction([(b, a) for (a, b) in batch])
            for sf, sb in zip(fwd, bwd):
                scores.append(float((sf + sb) / 2.0))
        return scores

    def release(self) -> None:
        """Free the model from memory (call after the rerank stage)."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        if self._torch is not None:
            if self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
            self._torch = None
        gc.collect()
        logger.info("CrossEncoderReranker released from memory")


def build_rerank_text(rec) -> str:
    """Build a compact, comparable description string for a source record.

    Field order is deliberately stable and semantically aligned so the
    cross-encoder compares like-with-like (name + discriminators + admin scope).
    """
    parts = []
    name = getattr(rec, "name_raw", None) or getattr(rec, "canonical_name", None) or ""
    if name:
        parts.append(str(name).strip())
    addr = getattr(rec, "address_raw", None) or ""
    if addr:
        parts.append(str(addr).strip())
    city = getattr(rec, "city_raw", None) or getattr(rec, "city", None) or ""
    dist = getattr(rec, "district_raw", None) or getattr(rec, "district", None) or ""
    if city or dist:
        parts.append(f"{city}/{dist}")
    return " | ".join(p for p in parts if p)
