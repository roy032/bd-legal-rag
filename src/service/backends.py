"""Cache and rate-limit backends.

In-process by default so the service runs with no infrastructure; Redis when
there is more than one replica. Both sit behind the same two interfaces, so
switching is a config change and the tests never need a Redis.

The in-process versions are not "the toy version" — for a single container they
are the right choice: no network hop, no extra failure mode.
"""
from __future__ import annotations

import contextlib
import json
import os
from typing import Any, Protocol

from .cache import TTLCache
from .ratelimit import Decision, TokenBucket


class CacheBackend(Protocol):
    def get(self, key: str) -> Any | None: ...
    def put(self, key: str, value: Any) -> None: ...
    def stats(self) -> dict: ...


class LimiterBackend(Protocol):
    def check(self, client: str) -> Decision: ...


class RedisCache:
    def __init__(self, url: str, ttl_s: float = 1800, prefix: str = "bdrag:answer:") -> None:
        import redis  # pip install redis

        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.ttl_s, self.prefix = int(ttl_s), prefix
        self.hits = self.misses = 0

    def get(self, key: str) -> Any | None:
        try:
            raw = self.client.get(self.prefix + key)
        except Exception:
            return None                      # a cache outage must never fail a request
        if raw is None:
            self.misses += 1
            return None
        self.hits += 1
        return json.loads(raw)

    def put(self, key: str, value: Any) -> None:
        with contextlib.suppress(Exception):   # a cache write must never fail a request
            self.client.setex(self.prefix + key, self.ttl_s, json.dumps(value, ensure_ascii=False))

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"backend": "redis", "hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0}


class RedisLimiter:
    """Fixed-window counter in Redis — shared across replicas."""

    def __init__(self, url: str, rate_per_min: float = 20, burst: int = 5,
                 prefix: str = "bdrag:rl:") -> None:
        import redis

        self.client = redis.Redis.from_url(url, decode_responses=True)
        self.limit = max(int(rate_per_min), 1)
        self.burst = burst
        self.prefix = prefix
        self._fallback = TokenBucket(rate_per_min, burst)

    def check(self, client: str) -> Decision:
        try:
            key = f"{self.prefix}{client}"
            count = self.client.incr(key)
            if count == 1:
                self.client.expire(key, 60)
            allowed = count <= self.limit + self.burst
            return Decision(allowed, 0.0 if allowed else 60.0,
                            max(self.limit + self.burst - count, 0))
        except Exception:
            return self._fallback.check(client)   # Redis down: limit locally, keep serving


def make_cache(ttl_s: float, size: int, redis_url: str | None = None) -> CacheBackend:
    url = redis_url or os.environ.get("REDIS_URL")
    if url:
        try:
            return RedisCache(url, ttl_s=ttl_s)
        except Exception:
            pass                                   # fall back rather than fail to start
    return TTLCache(max_size=size, ttl_s=ttl_s)


def make_limiter(rate_per_min: float, burst: int, redis_url: str | None = None) -> LimiterBackend:
    url = redis_url or os.environ.get("REDIS_URL")
    if url:
        try:
            return RedisLimiter(url, rate_per_min=rate_per_min, burst=burst)
        except Exception:
            pass
    return TokenBucket(rate_per_min=rate_per_min, burst=burst)
