"""Vector stores.

NumpyStore : exact (brute-force) cosine search. For a corpus of this size
             (tens of thousands of chunks) it is fast enough and always
             correct — which makes it the reference you compare an
             approximate index against.
QdrantStore: the production path (HNSW index + server-side filtering).

Both share one interface, so swapping them is a one-line change and you can
measure what approximate search costs you in recall.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import jsonio
from .embed import l2_normalize
from .filters import matches


@dataclass
class Hit:
    chunk_id: str
    score: float
    text: str
    body: str
    metadata: dict

    @property
    def citation(self) -> str:
        m = self.metadata
        if m.get("type") == "act_overview":
            return f"{m['act_title']} (overview)"
        label = "ধারা" if m.get("language") == "bn" else "section"
        return f"{m['act_title']}, {label} {m.get('section_number', '?')}"


class NumpyStore:
    """Exact cosine search, with optional int8 storage.

    Quantisation trades a little accuracy for 4x less memory: vectors are stored
    as int8, the search runs against them, and the top candidates are rescored
    with the float32 vectors when those are kept. Measure the recall cost on
    your own evaluation set before shipping it — `--quantize` exists so the
    trade-off is a number in your ablation table, not an assumption."""

    def __init__(self, dim: int, embedder_name: str = "", quantize: bool = False,
                 rescore_factor: int = 4) -> None:
        self.dim = dim
        self.embedder_name = embedder_name
        self.quantize = quantize
        self.rescore_factor = rescore_factor
        self.vectors = np.zeros((0, dim), dtype=np.float32)
        self.codes: np.ndarray | None = None      # int8 view, when quantised
        self.records: list[dict] = []

    def __len__(self) -> int:
        return len(self.records)

    def add(self, vectors: np.ndarray, records: Iterable[dict]) -> None:
        vectors = l2_normalize(np.asarray(vectors, dtype=np.float32))
        if vectors.shape[1] != self.dim:
            raise ValueError(f"expected dim {self.dim}, got {vectors.shape[1]}")
        self.vectors = np.vstack([self.vectors, vectors])
        if self.quantize:
            # Unit-norm vectors live in [-1, 1], so a fixed 127x scale is safe.
            self.codes = np.round(self.vectors * 127).astype(np.int8)
        self.records.extend(records)
        if len(self.records) != len(self.vectors):
            raise ValueError("vectors and records out of sync")

    def search(self, query_vec: np.ndarray, k: int = 5,
               filters: dict[str, Any] | None = None,
               where: Callable[[dict], bool] | None = None) -> list[Hit]:
        if len(self) == 0:
            return []
        q = l2_normalize(np.asarray(query_vec, dtype=np.float32).reshape(1, -1))[0]
        if self.quantize and self.codes is not None:
            scores = (self.codes.astype(np.float32) @ q) / 127.0   # approximate
        else:
            scores = self.vectors @ q                  # cosine, vectors are normalized

        if filters or where:
            keep = np.array([
                (not filters or matches(r["metadata"], filters)) and (not where or where(r["metadata"]))
                for r in self.records
            ])
            scores = np.where(keep, scores, -np.inf)

        k = min(k, len(self))
        if self.quantize and self.codes is not None and self.vectors.size:
            # Rescore a wider band with the exact vectors: quantisation error only
            # has to preserve the candidate set, not the final order.
            wide = min(k * self.rescore_factor, len(self))
            band = np.argpartition(-scores, wide - 1)[:wide]
            exact = self.vectors[band] @ q
            band = band[np.argsort(-exact)][:k]
            idx = band
            scores = np.where(np.isfinite(scores), scores, scores)
            scores[idx] = exact[np.argsort(-exact)][:k]
        else:
            idx = np.argpartition(-scores, k - 1)[:k]  # O(n) top-k, then sort just those
            idx = idx[np.argsort(-scores[idx])]
        return [
            Hit(
                chunk_id=self.records[i]["chunk_id"],
                score=float(scores[i]),
                text=self.records[i]["text"],
                body=self.records[i]["body"],
                metadata=self.records[i]["metadata"],
            )
            for i in idx if np.isfinite(scores[i])
        ]

    # ---------------- persistence ----------------
    def save(self, path: str | Path, compress: bool = True) -> None:
        """vectors as float16 (half the disk, cosine error ~1e-3 — far below
        the gap between neighbouring ranks), records as gzipped JSONL."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "vectors.npy", self.vectors.astype(np.float16))
        jsonio.write_jsonl(path / "records.jsonl", self.records, compress=compress)
        (path / "index.json").write_text(
            json.dumps({"dim": self.dim, "embedder": self.embedder_name, "count": len(self),
                        "quantized": self.quantize, "vector_dtype": "float16"},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> NumpyStore:
        path = Path(path)
        info = json.loads((path / "index.json").read_text(encoding="utf-8"))
        store = cls(dim=info["dim"], embedder_name=info.get("embedder", ""),
                    quantize=bool(info.get("quantized")))
        store.vectors = l2_normalize(np.load(path / "vectors.npy").astype(np.float32))
        if store.quantize:
            store.codes = np.round(store.vectors * 127).astype(np.int8)
        store.records = jsonio.read_jsonl(path / "records.jsonl")
        if len(store.records) != len(store.vectors):
            raise ValueError(f"{path}: {len(store.vectors)} vectors but {len(store.records)} records")
        return store


class QdrantStore:
    """Production backend. Same interface; needs `pip install qdrant-client`
    and a running Qdrant (`docker run -p 6333:6333 qdrant/qdrant`)."""

    def __init__(self, dim: int, collection: str = "bdlaws", url: str = "http://localhost:6333",
                 embedder_name: str = "", recreate: bool = False) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.dim, self.collection, self.embedder_name = dim, collection, embedder_name
        self.client = QdrantClient(url=url)
        exists = self.client.collection_exists(collection)
        if recreate and exists:
            self.client.delete_collection(collection)
            exists = False
        if not exists:
            self.client.create_collection(
                collection, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
        self._n = 0

    def __len__(self) -> int:
        return self.client.count(self.collection).count

    def add(self, vectors: np.ndarray, records: Iterable[dict], batch: int = 256) -> None:
        from qdrant_client.models import PointStruct

        records = list(records)
        vectors = l2_normalize(np.asarray(vectors, dtype=np.float32))
        points = [
            PointStruct(id=self._n + i, vector=vectors[i].tolist(), payload=r)
            for i, r in enumerate(records)
        ]
        for i in range(0, len(points), batch):
            self.client.upsert(self.collection, points=points[i:i + batch])
        self._n += len(points)

    def search(self, query_vec: np.ndarray, k: int = 5,
               filters: dict[str, Any] | None = None, where=None) -> list[Hit]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        qfilter = None
        if filters:
            must = []
            for key, want in filters.items():
                if callable(want):
                    continue  # not expressible server-side; filter after retrieval
                cond = MatchAny(any=list(want)) if isinstance(want, (list, tuple, set)) else MatchValue(value=want)
                must.append(FieldCondition(key=f"metadata.{key}", match=cond))
            qfilter = Filter(must=must)
        res = self.client.query_points(
            self.collection, query=np.asarray(query_vec, dtype=np.float32).tolist(),
            limit=k, query_filter=qfilter, with_payload=True).points
        return [
            Hit(chunk_id=p.payload["chunk_id"], score=float(p.score), text=p.payload["text"],
                body=p.payload["body"], metadata=p.payload["metadata"])
            for p in res
        ]
