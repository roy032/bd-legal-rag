"""A small TTL + LRU cache.

Two things are worth caching in a RAG service, for different reasons:

  query embeddings - the same question is asked again and again; embedding is
                     pure CPU and the result never changes for a given model.
  whole answers    - saves the expensive LLM call, but MUST be keyed by every
                     setting that changes the answer (index, model, k, mode,
                     guard thresholds). A cache keyed only by the question is
                     how you end up serving yesterday's pipeline.

Answers get a TTL because the corpus and the prompt change; embeddings are
keyed by model name and do not.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, max_size: int = 512, ttl_s: float | None = 3600) -> None:
        self.max_size, self.ttl_s = max_size, ttl_s
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = self.evictions = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            ts, value = entry
            if self.ttl_s is not None and time.time() - ts > self.ttl_s:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)      # least-recently-used at the front
            self.hits += 1
            return value

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)
                self.evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"size": len(self._data), "hits": self.hits, "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 3) if total else 0.0}


def cache_key(question: str, **config) -> str:
    """Question + every setting that can change the answer."""
    payload = json.dumps({"q": " ".join(question.split()).lower(), **config},
                         sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
