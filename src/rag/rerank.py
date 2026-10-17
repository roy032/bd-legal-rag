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

from collections import OrderedDict
from pathlib import Path
from typing import Protocol

from .lexical import tokenize
from .store import Hit

PRECISIONS = ("auto", "fp32", "bf16", "int8")


def cpu_has_bf16() -> bool:
    """True when the CPU runs bfloat16 matmuls natively (AVX512-BF16 or AMX).

    On such a CPU bf16 is about 3x faster than fp32 with the same ranking; on any
    other CPU it is emulated and slower than fp32, so "auto" must not pick it.
    """
    try:
        flags = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
    except OSError:                      # Windows, macOS: no cpuinfo to read
        return False
    return "avx512_bf16" in flags or "amx_bf16" in flags


class Reranker(Protocol):
    name: str

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]: ...


def resolve_precision(precision: str, device: str | None = None) -> str:
    if precision not in PRECISIONS:
        raise ValueError(f"rerank precision must be one of {PRECISIONS}, not {precision!r}")
    if precision != "auto":
        return precision
    if device and device != "cpu":
        return "fp32"                    # a GPU is fast enough as it is
    return "bf16" if cpu_has_bf16() else "fp32"


class CrossEncoderReranker:
    """bge-reranker-v2-m3 by default, with three things that make it usable on a CPU.

    precision : "bf16" (native on AVX512-BF16/AMX CPUs: ~3x faster, same ranking),
                "int8" (dynamic quantisation of the linear layers: ~2x faster on any
                CPU, ranking changes slightly: measure it), "fp32", or "auto".
    batching  : pairs are scored shortest first, so a batch pads to similar lengths.
    cache     : scores are kept per (query, chunk), so a repeated question or a
                follow-up that retrieves the same excerpts costs nothing.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", batch_size: int = 8,
                 max_length: int = 512, device: str | None = None, precision: str = "auto",
                 cache_size: int = 4096) -> None:
        from sentence_transformers import CrossEncoder  # lazy: heavy

        self.precision = resolve_precision(precision, device)
        kwargs: dict = {}
        if self.precision == "bf16":
            import torch

            kwargs["model_kwargs"] = {"torch_dtype": torch.bfloat16}
        self.model = CrossEncoder(model_name, max_length=max_length, device=device, **kwargs)
        if self.precision == "int8":
            import torch

            torch.ao.quantization.quantize_dynamic(self.model, {torch.nn.Linear},
                                                   dtype=torch.qint8, inplace=True)
        self.name = f"{model_name} ({self.precision})"
        self.batch_size = batch_size
        self._cache: OrderedDict[tuple[str, str], float] = OrderedDict()
        self._cache_size = cache_size

    def score(self, query: str, hits: list[Hit]) -> list[float]:
        scores: dict[int, float] = {}
        todo: list[int] = []
        for i, h in enumerate(hits):
            key = (query, h.chunk_id)
            if key in self._cache:
                self._cache.move_to_end(key)
                scores[i] = self._cache[key]
            else:
                todo.append(i)
        if todo:
            todo.sort(key=lambda i: len(hits[i].text))
            fresh = self.model.predict([(query, hits[i].text) for i in todo],
                                       batch_size=self.batch_size, show_progress_bar=False)
            for i, s in zip(todo, fresh, strict=True):
                scores[i] = float(s)
                self._cache[(query, hits[i].chunk_id)] = float(s)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return [scores[i] for i in range(len(hits))]

    def rerank(self, query: str, hits: list[Hit], k: int) -> list[Hit]:
        if not hits:
            return []
        scores = self.score(query, hits)
        ranked = sorted(zip(hits, scores, strict=True), key=lambda p: -p[1])[:k]
        return [Hit(h.chunk_id, s, h.text, h.body, h.metadata) for h, s in ranked]


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
    kw = {k: v for k, v in kw.items() if v is not None}
    return CrossEncoderReranker(model_name=model, **kw)
