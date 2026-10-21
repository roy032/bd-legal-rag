"""Minimal span tracing: which stage took the time, per request.

Every finished trace is one structured log line — "retrieval 40 ms, rerank 220 ms,
model 3.1 s" — with no dependency. Set BDRAG_OTEL_ENDPOINT (an OTLP/HTTP traces
URL such as http://localhost:4318/v1/traces) and install the `otel` extra, and the
same spans are also exported to OpenTelemetry, so Jaeger or Grafana Tempo show
retrieval against model time per request. Without the endpoint nothing changes.
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("trace")


@dataclass
class Trace:
    request_id: str
    spans: list[dict] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    # Wall-clock start, for exporters that place spans on a timeline. Kept out of
    # the log line, which only needs durations.
    started_ns: int = field(default_factory=time.time_ns)
    offsets_ns: list[int] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, **attrs):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.offsets_ns.append(int((start - self.started) * 1e9))
            self.spans.append({"name": name, "ms": round((time.perf_counter() - start) * 1000, 1),
                               **attrs})

    def finish(self, **attrs) -> dict:
        payload = {"request_id": self.request_id,
                   "total_ms": round((time.perf_counter() - self.started) * 1000, 1),
                   "spans": self.spans, **attrs}
        log.info(json.dumps(payload, ensure_ascii=False))
        if _exporter is not None:
            try:
                _exporter.export(self, payload)
            except Exception:                 # tracing must never break a response
                log.warning("OpenTelemetry export failed", exc_info=True)
        return payload


def _attr(value: Any) -> Any:
    """OpenTelemetry attributes are str, bool, int or float."""
    return value if isinstance(value, (str, bool, int, float)) else str(value)


class OTelExporter:
    """Turns a finished Trace into one root span with a child per stage."""

    def __init__(self, tracer) -> None:
        self.tracer = tracer

    @classmethod
    def from_endpoint(cls, endpoint: str, service_name: str = "bd-legal-rag") -> OTelExporter:
        # Optional dependency: pip install -e ".[otel]"
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        return cls(provider.get_tracer("bdrag"))

    def export(self, trace: Trace, payload: dict) -> None:
        from opentelemetry import trace as otel_trace

        end_ns = trace.started_ns + int(payload["total_ms"] * 1e6)
        root_attrs = {"request_id": trace.request_id,
                      **{f"bdrag.{k}": _attr(v) for k, v in payload.items()
                         if k not in ("request_id", "total_ms", "spans")}}
        root = self.tracer.start_span(f"bdrag {payload.get('endpoint', 'request')}",
                                      start_time=trace.started_ns, attributes=root_attrs)
        ctx = otel_trace.set_span_in_context(root)
        for span, offset in zip(trace.spans, trace.offsets_ns, strict=False):
            start = trace.started_ns + offset
            child = self.tracer.start_span(
                span["name"], context=ctx, start_time=start,
                attributes={f"bdrag.{k}": _attr(v) for k, v in span.items() if k != "name"})
            child.end(end_time=start + int(span["ms"] * 1e6))
        root.end(end_time=end_ns)


_exporter: OTelExporter | None = None


def configure_otel(endpoint: str | None = None, exporter: OTelExporter | None = None) -> bool:
    """Turn the OpenTelemetry export on (or off with no endpoint). True when on."""
    global _exporter
    if exporter is not None:
        _exporter = exporter
        return True
    endpoint = (endpoint if endpoint is not None
                else os.environ.get("BDRAG_OTEL_ENDPOINT", "")).strip()
    if not endpoint:
        _exporter = None
        return False
    try:
        _exporter = OTelExporter.from_endpoint(
            endpoint, os.environ.get("OTEL_SERVICE_NAME", "bd-legal-rag"))
    except ImportError:
        log.warning("BDRAG_OTEL_ENDPOINT is set but OpenTelemetry is not installed; "
                    "pip install -e '.[otel]'. Traces stay in the logs only.")
        _exporter = None
        return False
    return True
