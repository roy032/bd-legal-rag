"""Request spans: the log line, and the optional OpenTelemetry export."""
import json
import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from service import tracing  # noqa: E402
from service.tracing import OTelExporter, Trace, configure_otel  # noqa: E402

try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    HAVE_OTEL = True
except ImportError:          # the otel extra is optional
    HAVE_OTEL = False


class TestTrace(unittest.TestCase):
    def tearDown(self):
        configure_otel("")

    def test_log_line_is_unchanged_without_an_endpoint(self):
        self.assertFalse(configure_otel(""))
        t = Trace("r1")
        with t.span("retrieve", k=5):
            pass
        with self.assertLogs("trace", logging.INFO) as logs:
            payload = t.finish(endpoint="search")
        line = json.loads(logs.records[0].getMessage())
        self.assertEqual(line["spans"][0]["name"], "retrieve")
        self.assertNotIn("started_ns", line)
        self.assertEqual(payload["endpoint"], "search")

    def test_a_failing_exporter_never_breaks_the_request(self):
        class Broken:
            def export(self, trace, payload):
                raise RuntimeError("collector down")
        configure_otel(exporter=Broken())  # type: ignore[arg-type]
        with self.assertLogs("trace", logging.INFO):
            Trace("r2").finish(endpoint="ask")

    def test_missing_dependency_is_a_warning(self):
        real = OTelExporter.from_endpoint

        def missing(*a, **kw):
            raise ImportError("no otel")
        OTelExporter.from_endpoint = missing  # type: ignore[method-assign]
        try:
            with self.assertLogs("trace", logging.WARNING):
                self.assertFalse(configure_otel("http://localhost:4318/v1/traces"))
            self.assertIsNone(tracing._exporter)
        finally:
            OTelExporter.from_endpoint = real  # type: ignore[method-assign]


@unittest.skipUnless(HAVE_OTEL, "opentelemetry not installed")
class TestOTelExport(unittest.TestCase):
    def tearDown(self):
        configure_otel("")

    def test_root_span_with_a_child_per_stage(self):
        memory = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(memory))
        configure_otel(exporter=OTelExporter(provider.get_tracer("test")))

        t = Trace("abc")
        with t.span("retrieve", k=5):
            pass
        with t.span("answer", agent=False, model=None):
            pass
        with self.assertLogs("trace", logging.INFO):
            t.finish(endpoint="ask", refused=False)

        spans = {s.name: s for s in memory.get_finished_spans()}
        self.assertEqual(set(spans), {"bdrag ask", "retrieve", "answer"})
        root = spans["bdrag ask"]
        self.assertEqual(root.attributes["request_id"], "abc")
        self.assertIs(root.attributes["bdrag.refused"], False)
        for child in ("retrieve", "answer"):
            self.assertEqual(spans[child].parent.span_id, root.context.span_id)
            self.assertGreaterEqual(spans[child].start_time, root.start_time)
            self.assertLessEqual(spans[child].end_time, root.end_time + 1_000_000)
        self.assertEqual(spans["retrieve"].attributes["bdrag.k"], 5)
        self.assertEqual(spans["answer"].attributes["bdrag.model"], "None")

    def test_endpoint_builds_an_otlp_exporter(self):
        self.assertTrue(configure_otel("http://127.0.0.1:9/v1/traces"))
        self.assertIsInstance(tracing._exporter, OTelExporter)


if __name__ == "__main__":
    unittest.main()
