"""Counters and latency percentiles, with a Prometheus text rendering.

Deliberately dependency-free: a portfolio service that needs a metrics stack
running before it can report a p95 will not get run by anyone.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque


class Metrics:
    def __init__(self, window: int = 512) -> None:
        self.counters: dict[str, float] = defaultdict(float)
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        with self._lock:
            self.counters[self._key(name, labels)] += value

    def observe(self, name: str, seconds: float, **labels) -> None:
        with self._lock:
            self.latencies[self._key(name, labels)].append(seconds)

    @staticmethod
    def _key(name: str, labels: dict) -> str:
        if not labels:
            return name
        inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{inner}}}"

    @staticmethod
    def _pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        return ordered[min(int(len(ordered) * p), len(ordered) - 1)]

    def snapshot(self) -> dict:
        with self._lock:
            out: dict = {"counters": dict(self.counters), "latency_s": {}}
            for key, values in self.latencies.items():
                vals = list(values)
                out["latency_s"][key] = {
                    "n": len(vals),
                    "p50": round(self._pct(vals, 0.5), 4),
                    "p95": round(self._pct(vals, 0.95), 4),
                    "max": round(max(vals), 4) if vals else 0.0,
                }
            return out

    HELP = {
        "requests_total": "HTTP requests handled, by path and status",
        "answers_total": "Answers produced, by mode and outcome",
        "errors_total": "Unhandled errors, by path",
        "cache_hits_total": "Answers served from cache",
        "rate_limited_total": "Requests rejected by the rate limiter",
        "repairs_total": "Answers that needed a corrective re-prompt",
        "guardrail_failures_total": "Answers that failed a guardrail check",
        "search_total": "Retrieval-only requests",
        "llm_cost_usd_total": "Estimated model spend",
        "degraded_total": "Requests served without the model after an LLM failure",
    }

    def prometheus(self) -> str:
        """Exposition format with HELP/TYPE, so a real scraper is happy with it."""
        snap = self.snapshot()
        lines = []
        seen_metrics = set()
        for key, value in sorted(snap["counters"].items()):
            name = key.split("{")[0]
            if name not in seen_metrics:
                seen_metrics.add(name)
                lines.append(f"# HELP {name} {self.HELP.get(name, name.replace('_', ' '))}")
                lines.append(f"# TYPE {name} counter")
            lines.append(f"{key} {value}")
        for key in sorted(snap["latency_s"]):
            name = key.split("{")[0] + "_seconds"
            if name not in seen_metrics:
                seen_metrics.add(name)
                lines.append(f"# HELP {name} Latency in seconds")
                lines.append(f"# TYPE {name} summary")
        for key, stats in sorted(snap["latency_s"].items()):
            base, _, labels = key.partition("{")
            suffix = ("{" + labels) if labels else ""
            for stat in ("p50", "p95", "max"):
                sep = "," if labels else ""
                inner = f'{{quantile="{stat}"{sep}{labels}' if labels else f'{{quantile="{stat}"}}'
                lines.append(f"{base}_seconds{inner if labels else inner} {stats[stat]}")
            lines.append(f"{base}_count{suffix} {stats['n']}")
        return "\n".join(lines) + "\n"
