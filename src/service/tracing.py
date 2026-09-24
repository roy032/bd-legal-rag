"""Minimal span tracing: which stage took the time, per request.

OpenTelemetry is the right answer in a company with a collector running. Here,
structured span logs give the same answer — "retrieval 40 ms, rerank 220 ms,
model 3.1 s" — with no dependency, and they export cleanly to Langfuse or OTel
later because the shape is the same.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

log = logging.getLogger("trace")


@dataclass
class Trace:
    request_id: str
    spans: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    @contextmanager
    def span(self, name: str, **attrs):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.spans.append({"name": name, "ms": round((time.perf_counter() - start) * 1000, 1),
                               **attrs})

    def finish(self, **attrs) -> dict:
        payload = {"request_id": self.request_id,
                   "total_ms": round((time.perf_counter() - self.started) * 1000, 1),
                   "spans": self.spans, **attrs}
        log.info(json.dumps(payload, ensure_ascii=False))
        return payload
