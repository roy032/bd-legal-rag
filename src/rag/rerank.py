"""Reranking: retrieve wide and cheap, then re-score narrow and expensive.

A bi-encoder (the embedder) turns query and document into vectors separately,
so it never compares their words directly — fast, but blunt. A cross-encoder
reads (query, document) together and scores the pair. It cannot index a corpus
(you would run it over every chunk for every query), so the pattern is:

    dense/hybrid retrieval -> 30-50 candidates -> cross-encoder -> top 5

In most RAG systems this is the single biggest accuracy gain available, and it
is also the biggest latency cost. Measure both; report both.
"""
from __future__ import annotations

from typing import Protocol

from .lexical import tokenize
from .store import Hit


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", batch_size: int = 16,
                 max_length: int = 512, device: str | None = None) -> None:
        from sentence_transformers import CrossEncoder  # lazy: heavy

        self.name = model_name
        self.model = CrossEncoder(model_name, max_length=max_length, device=device)
        self.batch_size = batch_size

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        if not hits:
            return []
        scores = self.model.predict([(query, h.text) for h in hits],
                                    batch_size=self.batch_size, show_progress_bar=False)
        ranked = sorted(zip(hits, scores, strict=False), key=lambda p: -float(p[1]))[:k]
        return [Hit(h.chunk_id, float(s), h.text, h.body, h.metadata) for h, s in ranked]


class LexicalOverlapReranker:
    """No-dependency stand-in: scores by weighted token overlap with the query.

    Useful for tests and for a demo without downloads — and as the honest
    baseline row that tells you how much the real cross-encoder is worth.
    """

    name = "lexical-overlap"

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        q = set(tokenize(query, stem=True))
        if not q:
            return hits[:k]
        scored = []
        for h in hits:
            toks = tokenize(h.text, stem=True)
            if not toks:
                scored.append((h, 0.0))
                continue
            overlap = sum(t in q for t in toks)
            # coverage of the query matters more than raw count of matches
            coverage = len(q & set(toks)) / len(q)
            scored.append((h, coverage + 0.1 * overlap / len(toks)))
        ranked = sorted(scored, key=lambda p: -p[1])[:k]
        return [Hit(h.chunk_id, float(s), h.text, h.body, h.metadata) for h, s in ranked]


def get_reranker(kind: str, model: str = "BAAI/bge-reranker-v2-m3", **kw):
    if kind in ("none", None, ""):
        return None
    if kind == "lexical":
        return LexicalOverlapReranker()
    return CrossEncoderReranker(model_name=model, **kw)
