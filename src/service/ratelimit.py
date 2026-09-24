"""Token-bucket rate limiting, per client.

An LLM-backed endpoint is expensive per request, so an open one is a way to
lose money quickly. A token bucket allows short bursts (people re-ask, click
twice) while capping the sustained rate.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Decision:
    allowed: bool
    retry_after_s: float
    remaining: float


class TokenBucket:
    def __init__(self, rate_per_min: float = 20, burst: int = 5, max_clients: int = 10_000) -> None:
        self.rate_s = rate_per_min / 60.0
        self.burst = burst
        self.max_clients = max_clients
        self._state: dict[str, tuple[float, float]] = {}   # client -> (tokens, last_seen)
        self._lock = threading.Lock()

    def check(self, client: str, now: float | None = None) -> Decision:
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._state.get(client, (float(self.burst), now))
            tokens = min(self.burst, tokens + (now - last) * self.rate_s)
            if tokens >= 1:
                self._state[client] = (tokens - 1, now)
                allowed, retry = True, 0.0
            else:
                self._state[client] = (tokens, now)
                allowed, retry = False, (1 - tokens) / self.rate_s if self.rate_s else 60.0
            if len(self._state) > self.max_clients:        # bound the memory
                for stale, _ in sorted(self._state.items(), key=lambda kv: kv[1][1])[:len(self._state) // 4]:
                    self._state.pop(stale, None)
            return Decision(allowed, round(retry, 2), round(tokens, 2))
