"""Counters and latency percentiles, with a Prometheus text rendering.

Deliberately dependency-free: a portfolio service that needs a metrics stack
running before it can report a p95 will not get run by anyone.

Latencies are exported as Prometheus histograms (cumulative `_bucket{le=...}`,
`_sum`, `_count`), which a dashboard can aggregate across replicas and turn into
any quantile with `histogram_quantile`; the p50/p95 in `/stats` come from a
window of recent samples and are for a human glancing at one process.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque

# Seconds. Spans a cached /search (milliseconds) to a CPU-only answer (minutes).
BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0)


class Metrics:
    def __init__(self, window: int = 512, buckets: tuple[float, ...] = BUCKETS) -> None:
        self.counters: dict[str, float] = defaultdict(float)
        self.gauges: dict[str, float] = {}
        self.latencies: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=window))
        self.buckets = buckets
        # key -> (per-bucket counts incl. +Inf, sum, count); lifetime, not windowed
        self.histograms: dict[str, tuple[list[int], float, int]] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        with self._lock:
            self.counters[self._key(name, labels)] += value

    def observe(self, name: str, seconds: float, **labels) -> None:
        key = self._key(name, labels)
        with self._lock:
            self.latencies[key].append(seconds)
            counts, total, n = self.histograms.get(key) or ([0] * (len(self.buckets) + 1), 0.0, 0)
            idx = next((i for i, b in enumerate(self.buckets) if seconds <= b), len(self.buckets))
            counts[idx] += 1
            self.histograms[key] = (counts, total + seconds, n + 1)

    def set_gauge(self, name: str, value: float, **labels) -> None:
        with self._lock:
            self.gauges[self._key(name, labels)] = value

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
            out: dict = {"counters": dict(self.counters), "gauges": dict(self.gauges),
                         "latency_s": {}}
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
        "shed_total": "Answers refused because too many were already running or waiting",
        "circuit_open_total": "Answers served without the model because its circuit was open",
        "singleflight_shared_total": "Answers shared with an identical question already running",
        "inflight_answers": "Answers running now",
        "queued_answers": "Answers waiting for a slot",
        "circuit_open": "1 while the answering model's circuit breaker is open",
        "ready": "1 once the index and models are loaded",
        "request_seconds": "HTTP request latency",
        "answer_seconds": "Time to a complete answer",
        "ttft_seconds": "Streaming: time to the first answer token",
    }

    def prometheus(self) -> str:
        """Exposition format with HELP/TYPE, so a real scraper is happy with it."""
        with self._lock:
            counters, gauges = dict(self.counters), dict(self.gauges)
            hists = {k: (list(c), t, n) for k, (c, t, n) in self.histograms.items()}
        lines: list[str] = []
        seen: set[str] = set()

        def header(name: str, kind: str) -> None:
            if name not in seen:
                seen.add(name)
                lines.append(f"# HELP {name} {self.HELP.get(name, name.replace('_', ' '))}")
                lines.append(f"# TYPE {name} {kind}")

        for kind, values in (("counter", counters), ("gauge", gauges)):
            for key, value in sorted(values.items()):
                header(key.split("{")[0], kind)
                lines.append(f"{key} {value}")
        for key, (counts, total, n) in sorted(hists.items()):
            base, _, labels = key.partition("{")
            labels = labels.rstrip("}")
            name = f"{base}_seconds"
            header(name, "histogram")
            sep = "," if labels else ""
            running = 0
            for bound, count in zip((*self.buckets, float("inf")), counts, strict=True):
                running += count
                le = "+Inf" if bound == float("inf") else repr(bound)
                lines.append(f'{name}_bucket{{{labels}{sep}le="{le}"}} {running}')
            suffix = f"{{{labels}}}" if labels else ""
            lines.append(f"{name}_sum{suffix} {round(total, 6)}")
            lines.append(f"{name}_count{suffix} {n}")
        return "\n".join(lines) + "\n"
