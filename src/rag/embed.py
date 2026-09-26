"""Embedding models behind one interface.

Two implementations:
  SentenceTransformerEmbedder - the real one (default: BAAI/bge-m3, multilingual,
      handles Bangla and English in one vector space).
  HashingEmbedder            - a dependency-free character n-gram hasher. No model
      download, deterministic, runs anywhere. Use it for tests, and as the
      "lexical baseline" row of your Phase 3 ablation table.

Query/passage prefixes matter: e5 models are trained with "query: " / "passage: "
prefixes and lose accuracy without them; bge-m3 needs none. Getting this wrong is
a classic silent RAG bug.
"""
from __future__ import annotations

import hashlib
import re
from typing import Protocol

import numpy as np

PREFIXES = {
    "e5": ("query: ", "passage: "),
    "bge-m3": ("", ""),
    "default": ("", ""),
}


def _prefixes(model_name: str) -> tuple[str, str]:
    low = model_name.lower()
    if "e5" in low:
        return PREFIXES["e5"]
    return PREFIXES["default"]


class Embedder(Protocol):
    name: str
    dim: int

    def encode_passages(self, texts: list[str]) -> np.ndarray: ...
    def encode_queries(self, texts: list[str]) -> np.ndarray: ...


def l2_normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.clip(norms, 1e-12, None)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str | None = None,
                 batch_size: int = 8, max_seq_length: int | None = 1024) -> None:
        from sentence_transformers import SentenceTransformer  # lazy: heavy import

        self.name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        if max_seq_length:
            self.model.max_seq_length = max_seq_length
        self.batch_size = batch_size
        self.dim = self.model.get_sentence_embedding_dimension()
        self.q_prefix, self.p_prefix = _prefixes(model_name)

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        vecs = self.model.encode(
            [prefix + t for t in texts],
            batch_size=self.batch_size,
            normalize_embeddings=True,   # so cosine similarity == dot product
            show_progress_bar=len(texts) > 64,
            convert_to_numpy=True,
        )
        return vecs.astype(np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, self.p_prefix)

    def encode_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, self.q_prefix)


_TOKEN = re.compile(r"[\wঀ-৿]+", re.UNICODE)


class HashingEmbedder:
    """Character-trigram hashing. Lexical, not semantic — that is the point:
    it shows you how much of your score comes from real semantics."""

    def __init__(self, dim: int = 512, ngram: int = 3) -> None:
        self.name = f"hashing-{dim}"
        self.dim = dim
        self.ngram = ngram

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for token in _TOKEN.findall(text.lower()):
            padded = f" {token} "
            grams = [padded[i:i + self.ngram] for i in range(max(len(padded) - self.ngram + 1, 1))]
            for g in grams:
                h = int.from_bytes(hashlib.md5(g.encode()).digest()[:4], "little")
                v[h % self.dim] += 1.0
        return v

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return l2_normalize(np.vstack([self._vector(t) for t in texts]))

    encode_queries = encode_passages


def get_embedder(kind: str = "st", model: str = "BAAI/bge-m3", index_dir=None, **kw) -> Embedder:
    """kind: 'st' | 'hashing' | 'auto'. 'auto' reads index.json in `index_dir` and
    builds the embedder the index was built with — querying a bge-m3 index with
    the hashing embedder (or the reverse) is a dimension error at best and
    silently meaningless scores at worst."""
    if kind == "auto":
        kind, model, kw = _from_index(index_dir, model, kw)
    if kind == "hashing":
        return HashingEmbedder(**kw)
    return SentenceTransformerEmbedder(model_name=model, **kw)


def embedder_for(mode: str, kind: str = "auto", model: str = "BAAI/bge-m3", index_dir=None) -> Embedder | None:
    """The query embedder a retrieval mode needs: none for pure BM25, so a
    BM25-only index works without downloading or loading an embedding model."""
    return None if mode == "bm25" else get_embedder(kind, model=model, index_dir=index_dir)


def _from_index(index_dir, model: str, kw: dict) -> tuple[str, str, dict]:
    import json
    from pathlib import Path

    info_path = Path(index_dir or "data/index") / "index.json"
    if not info_path.exists():
        return "st", model, kw
    name = json.loads(info_path.read_text(encoding="utf-8")).get("embedder", "")
    if name.startswith("hashing-"):
        return "hashing", model, {"dim": int(name.split("-", 1)[1])}
    return "st", name or model, kw
