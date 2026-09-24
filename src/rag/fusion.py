"""Reciprocal Rank Fusion — how to merge two result lists whose scores mean
completely different things.

A cosine similarity of 0.82 and a BM25 score of 14.3 are not comparable, and
normalising them ("min-max the scores") is fragile: one outlier rescales the
whole list. RRF throws the scores away and keeps only the ranks:

    RRF(d) = Σ_lists  weight_i / (rrf_k + rank_i(d))

rrf_k (60 by default, from the original paper) flattens the difference between
rank 1 and rank 2, so a document both lists like beats one that only one list
loves. Weights let you lean dense or lexical; measure them, don't guess.
"""
from __future__ import annotations

from .store import Hit


def reciprocal_rank_fusion(lists: list[list[Hit]], weights: list[float] | None = None,
                           rrf_k: int = 60, k: int = 10) -> list[Hit]:
    weights = weights or [1.0] * len(lists)
    if len(weights) != len(lists):
        raise ValueError("one weight per result list")
    fused: dict[str, float] = {}
    best: dict[str, Hit] = {}
    for hits, w in zip(lists, weights, strict=False):
        for rank, hit in enumerate(hits, start=1):
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + w / (rrf_k + rank)
            best.setdefault(hit.chunk_id, hit)
    ordered = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
    out = []
    for chunk_id, score in ordered:
        h = best[chunk_id]
        out.append(Hit(h.chunk_id, float(score), h.text, h.body, h.metadata))
    return out
