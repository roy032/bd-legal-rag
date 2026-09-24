"""Maximal Marginal Relevance and in-force boosting.

MMR: a ranked list where results 1-5 are five near-identical chunks wastes the
context window. MMR trades a little relevance for coverage:

    score = λ · relevance(d) - (1-λ) · max similarity(d, already selected)

Boosting: relevance is not the only thing that matters in law. A repealed act can
be the best textual match and still be the wrong answer, and an "[Omitted]"
placeholder matches a section number without saying anything. Both are pushed
down. Amended sections are NOT penalised: bdlaws publishes consolidated text,
so an amended section *is* the current law (the footnote records the change).
"""
from __future__ import annotations

import numpy as np

from .store import Hit


def mmr(hits: list[Hit], vectors: np.ndarray | None, k: int, lambda_: float = 0.7) -> list[Hit]:
    """Re-rank hits for relevance *and* diversity. `vectors` are the hits' embeddings."""
    if vectors is None or len(hits) <= 1:
        return hits[:k]
    selected: list[int] = []
    candidates = list(range(len(hits)))
    sims = vectors @ vectors.T
    relevance = np.array([h.score for h in hits], dtype=float)
    if relevance.max() > relevance.min():
        relevance = (relevance - relevance.min()) / (relevance.max() - relevance.min())
    while candidates and len(selected) < k:
        if not selected:
            best = max(candidates, key=lambda i: relevance[i])
        else:
            best = max(candidates, key=lambda i: lambda_ * relevance[i]
                       - (1 - lambda_) * max(sims[i][j] for j in selected))
        selected.append(best)
        candidates.remove(best)
    return [hits[i] for i in selected]


def boost_in_force(hits: list[Hit], omitted_penalty: float = 0.3,
                   repealed_penalty: float = 0.5) -> list[Hit]:
    """Nudge current law above repealed text and empty placeholders."""
    rescored = []
    for h in hits:
        penalty = 0.0
        if h.metadata.get("omitted"):
            penalty += omitted_penalty
        if h.metadata.get("repealed"):
            penalty += repealed_penalty
        rescored.append(Hit(h.chunk_id, h.score - penalty * abs(h.score or 1.0),
                            h.text, h.body, h.metadata))
    return sorted(rescored, key=lambda h: -h.score)
