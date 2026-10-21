"""Phase 7 tests: cache, rate limiting, metrics, and every endpoint.

The app is built with injected components, so these run with no index, no
model download and no API key — the same reason the service takes them as
arguments in the first place.
"""
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.embed import HashingEmbedder  # noqa: E402
from rag.pipeline import RetrievalConfig, SearchPipeline  # noqa: E402
from rag.retrieve import Retriever  # noqa: E402
from rag.store import NumpyStore  # noqa: E402
from service.cache import TTLCache, cache_key  # noqa: E402
from service.metrics import Metrics  # noqa: E402
from service.ratelimit import TokenBucket  # noqa: E402
from test_rag import CORPUS  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


class TestCache(unittest.TestCase):
    def test_hit_miss_and_stats(self):
        c = TTLCache(max_size=2)
        c.put("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("zzz"))
        self.assertEqual(c.stats()["hit_rate"], 0.5)

    def test_lru_evicts_the_oldest(self):
        c = TTLCache(max_size=2)
        c.put("a", 1)
        c.put("b", 2)
        c.get("a")                        # 'a' is now the most recently used
        c.put("c", 3)
        self.assertIsNone(c.get("b"))
        self.assertEqual(c.get("a"), 1)
        self.assertEqual(c.stats()["evictions"], 1)

    def test_ttl_expiry(self):
        c = TTLCache(ttl_s=0.01)
        c.put("a", 1)
        time.sleep(0.02)
        self.assertIsNone(c.get("a"))

    def test_key_covers_every_setting_that_changes_the_answer(self):
        base = cache_key("ধারা ৩০২ কী?", k=5, mode="hybrid")
        self.assertEqual(base, cache_key("  ধারা ৩০২ কী?  ", k=5, mode="hybrid"))  # whitespace
        self.assertNotEqual(base, cache_key("ধারা ৩০২ কী?", k=8, mode="hybrid"))   # k
        self.assertNotEqual(base, cache_key("ধারা ৩০২ কী?", k=5, mode="dense"))    # pipeline


class TestRateLimit(unittest.TestCase):
    def test_burst_then_block(self):
        b = TokenBucket(rate_per_min=60, burst=3)
        self.assertEqual([b.check("ip", now=0).allowed for _ in range(4)],
                         [True, True, True, False])

    def test_refills_over_time(self):
        b = TokenBucket(rate_per_min=60, burst=1)
        self.assertTrue(b.check("ip", now=0).allowed)
        self.assertFalse(b.check("ip", now=0.5).allowed)
        self.assertTrue(b.check("ip", now=1.1).allowed)

    def test_clients_are_independent(self):
        b = TokenBucket(rate_per_min=60, burst=1)
        self.assertTrue(b.check("a", now=0).allowed)
        self.assertTrue(b.check("b", now=0).allowed)

    def test_retry_after_is_reported(self):
        b = TokenBucket(rate_per_min=60, burst=1)
        b.check("ip", now=0)
        self.assertGreater(b.check("ip", now=0).retry_after_s, 0)


class TestMetrics(unittest.TestCase):
    def test_counters_and_percentiles(self):
        m = Metrics()
        m.inc("requests_total", path="/ask")
        m.inc("requests_total", path="/ask")
        for v in (0.1, 0.2, 0.3, 5.0):
            m.observe("answer", v)
        snap = m.snapshot()
        self.assertEqual(snap["counters"]['requests_total{path="/ask"}'], 2)
        self.assertEqual(snap["latency_s"]["answer"]["n"], 4)
        self.assertEqual(snap["latency_s"]["answer"]["max"], 5.0)

    def test_prometheus_text_shape(self):
        m = Metrics()
        m.inc("answers_total", outcome="refused")
        m.observe("answer", 0.4)
        text = m.prometheus()
        self.assertIn('answers_total{outcome="refused"} 1.0', text)
        self.assertIn("# TYPE answer_seconds histogram", text)
        self.assertIn('answer_seconds_bucket{le="0.25"} 0', text)
        self.assertIn('answer_seconds_bucket{le="0.5"} 1', text)
        self.assertIn('answer_seconds_bucket{le="+Inf"} 1', text)
        self.assertIn("answer_seconds_count 1", text)

    def test_histogram_buckets_are_cumulative_and_labelled(self):
        m = Metrics()
        for v in (0.02, 0.3, 7.0, 500.0):
            m.observe("request", v, path="/ask")
        m.set_gauge("inflight_answers", 2)
        text = m.prometheus()
        self.assertIn('request_seconds_bucket{path="/ask",le="0.025"} 1', text)
        self.assertIn('request_seconds_bucket{path="/ask",le="0.5"} 2', text)
        self.assertIn('request_seconds_bucket{path="/ask",le="10.0"} 3', text)
        self.assertIn('request_seconds_bucket{path="/ask",le="+Inf"} 4', text)
        self.assertIn('request_seconds_sum{path="/ask"} 507.32', text)
        self.assertIn("# TYPE inflight_answers gauge", text)
        self.assertIn("inflight_answers 2", text)


def fake_components():
    emb = HashingEmbedder(dim=256)
    store = NumpyStore(emb.dim, emb.name)
    store.add(emb.encode_passages([c["text"] for c in CORPUS]), CORPUS)
    pipeline = SearchPipeline(RetrievalConfig(mode="dense"), dense=Retriever(emb, store))
    llm = lambda system, prompt: "হত্যার শাস্তি মৃত্যুদণ্ড [1]।"          # noqa: E731
    stream = lambda system, prompt: iter(["হত্যার শাস্তি ", "মৃত্যুদণ্ড [1]।"])  # noqa: E731
    return pipeline, llm, stream


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestEndpoints(unittest.TestCase):
    def client(self, **cfg_kw):
        pipeline, llm, stream = fake_components()
        cfg = ServiceConfig(**{"rate_per_min": 6000, "burst": 100, **cfg_kw})
        app = create_app(cfg, pipeline=pipeline, llm=llm, stream_llm=stream, records=CORPUS)
        return TestClient(app)

    def test_health_and_stats(self):
        c = self.client()
        health = c.get("/health").json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["chunks"], len(CORPUS))
        self.assertIn("cache", c.get("/stats").json())

    def test_search_needs_no_llm(self):
        r = self.client().post("/search", json={"question": "হত্যার শাস্তি", "k": 2})
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(body["results"]), 2)
        self.assertIn("citation", body["results"][0])

    def test_ask_returns_answer_sources_and_disclaimer(self):
        body = self.client().post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertIn("মৃত্যুদণ্ড", body["answer"])
        self.assertEqual(body["sources"][0]["n"], 1)
        self.assertFalse(body["refused"])
        self.assertIn("not legal advice", body["disclaimer"])

    def test_validation(self):
        c = self.client()
        self.assertEqual(c.post("/ask", json={"question": "  "}).status_code, 400)
        self.assertEqual(c.post("/ask", json={"question": "x" * 501}).status_code, 400)
        self.assertEqual(c.post("/search", json={}).status_code, 400)

    def test_k_is_clamped_to_max(self):
        body = self.client().post("/search", json={"question": "হত্যা", "k": 9999}).json()
        self.assertLessEqual(len(body["results"]), len(CORPUS))

    def test_second_identical_question_is_served_from_cache(self):
        c = self.client()
        first = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        second = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])

    def test_different_k_is_a_different_cache_entry(self):
        c = self.client()
        c.post("/ask", json={"question": "হত্যার শাস্তি কী?", "k": 3})
        self.assertFalse(c.post("/ask", json={"question": "হত্যার শাস্তি কী?", "k": 5}).json()["cached"])

    def test_rate_limit_returns_429_with_retry_after(self):
        c = self.client(rate_per_min=1, burst=1)
        self.assertEqual(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).status_code, 200)
        r = c.post("/ask", json={"question": "ভিন্ন প্রশ্ন?"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("retry-after", r.headers)

    def test_streaming_emits_sources_tokens_and_final(self):
        r = self.client().post("/ask/stream", json={"question": "হত্যার শাস্তি কী?"})
        self.assertEqual(r.status_code, 200)
        events = [block.split("\n")[0].removeprefix("event: ")
                  for block in r.text.split("\n\n") if block.strip()]
        self.assertEqual(events[0], "status")
        self.assertIn("sources", events)
        self.assertIn("token", events)
        self.assertEqual(events[-1], "final")
        final = json.loads([b for b in r.text.split("\n\n") if b.startswith("event: final")][0]
                           .split("data: ")[1])
        self.assertIn("মৃত্যুদণ্ড", final["answer"])

    def test_empty_model_answer_degrades_and_is_not_cached(self):
        """A blank completion (e.g. Ollama out of memory) is a failure, not an answer."""
        pipeline, _, _ = fake_components()
        app = create_app(ServiceConfig(rate_per_min=6000, burst=100), pipeline=pipeline,
                         llm=lambda s, p: "   ", stream_llm=lambda s, p: iter([""]), records=CORPUS)
        c = TestClient(app)
        r = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        self.assertEqual(r.status_code, 503)
        self.assertTrue(r.json()["degraded"])
        self.assertTrue(r.json()["sources"])
        self.assertEqual(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).status_code, 503)

    def test_stream_degrades_to_sources_when_the_model_fails(self):
        from rag.llm import LLMError

        def broken(system, prompt):
            raise LLMError("Ollama error: model requires more system memory")
            yield ""                                      # pragma: no cover - makes it a generator

        pipeline, llm, _ = fake_components()
        app = create_app(ServiceConfig(rate_per_min=6000, burst=100), pipeline=pipeline,
                         llm=llm, stream_llm=broken, records=CORPUS)
        r = TestClient(app).post("/ask/stream", json={"question": "হত্যার শাস্তি কী?"})
        blocks = [b for b in r.text.split("\n\n") if b.strip()]
        self.assertTrue(blocks[-1].startswith("event: final"))
        final = json.loads(blocks[-1].split("data: ", 1)[1])
        self.assertTrue(final["degraded"])
        self.assertIn("memory", final["error"])
        self.assertTrue(final["sources"])

    def test_abstains_when_min_score_is_high(self):
        body = self.client(min_score=0.99, general_fallback=False).post(
            "/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertTrue(body["refused"] and body["abstained"])
        self.assertFalse(body["general_guidance"])

    def test_weak_retrieval_gets_labelled_general_guidance_by_default(self):
        body = self.client(min_score=0.99).post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertTrue(body["general_guidance"] and body["abstained"])
        self.assertFalse(body["refused"])
        self.assertTrue(body["answer"].startswith("সাধারণ নির্দেশনা"))
        self.assertIn("১৬৪৩০", body["answer"])
        self.assertEqual(body["sources"], [])

    def test_agent_mode_reports_its_trace(self):
        pipeline, _, stream = fake_components()
        script = iter(['ACTION: {"tool": "search", "args": {"query": "হত্যা", "k": 1}}',
                       "ANSWER: হত্যার শাস্তি মৃত্যুদণ্ড [1]।"])
        llm = lambda s, p: next(script, "ANSWER: NOT_FOUND: done")   # noqa: E731
        app = create_app(ServiceConfig(rate_per_min=6000, burst=100), pipeline=pipeline,
                         llm=llm, stream_llm=stream, records=CORPUS)
        body = TestClient(app).post("/ask", json={"question": "হত্যার শাস্তি কী?",
                                                  "agent": True}).json()
        self.assertEqual(body["stop_reason"], "answered")
        self.assertTrue(body["trace"])

    def test_metrics_endpoint_counts_requests(self):
        c = self.client()
        c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        text = c.get("/metrics").text
        self.assertIn("requests_total", text)
        self.assertIn("answers_total", text)

    def test_request_id_header_is_echoed(self):
        r = self.client().get("/health", headers={"x-request-id": "abc123"})
        self.assertEqual(r.headers["x-request-id"], "abc123")

    def test_ui_is_served(self):
        r = self.client().get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Bangladesh Law Assistant", r.text)



@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceImprovements(unittest.TestCase):
    """Phase 8 service behaviour: degradation, keys, feedback, permalinks, routing."""

    def client(self, llm=None, **cfg_kw):
        pipeline, default_llm, stream = fake_components()
        cfg = ServiceConfig(**{"rate_per_min": 6000, "burst": 100,
                               "feedback_path": self.tmp + "/feedback.jsonl",
                               "analytics_path": self.tmp + "/queries.jsonl", **cfg_kw})
        app = create_app(cfg, pipeline=pipeline, llm=llm or default_llm, stream_llm=stream,
                         records=CORPUS)
        return TestClient(app)

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_model_failure_degrades_to_retrieval(self):
        from rag.llm import LLMError

        def dead(system, prompt):
            raise LLMError("provider down")

        r = self.client(llm=dead).post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        self.assertEqual(r.status_code, 503)
        body = r.json()
        self.assertTrue(body["degraded"])
        self.assertTrue(body["sources"])            # the useful part still arrives

    def test_offline_stub_degrades_instead_of_returning_fake_answer(self):
        from rag.llm import echo_llm, echo_stream

        pipeline, _, _ = fake_components()
        c = TestClient(create_app(ServiceConfig(rate_per_min=6000, burst=100),
                                  pipeline=pipeline, llm=echo_llm(), stream_llm=echo_stream(),
                                  records=CORPUS))
        r = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        self.assertEqual(r.status_code, 503)
        self.assertTrue(r.json()["degraded"])
        self.assertTrue(r.json()["sources"])

    def test_daily_limit(self):
        c = self.client(daily_limit=2)
        q = {"question": "হত্যার শাস্তি কী?"}
        self.assertEqual([c.post("/ask", json=q).status_code for _ in range(3)], [200, 200, 429])
        self.assertEqual(c.post("/ask/stream", json=q).status_code, 429)

    def test_model_picker(self):
        from unittest import mock

        big = lambda system, prompt: "বড় মডেলের উত্তর [1]।"          # noqa: E731
        c = self.client(models=["ollama:gemma4:e4b", "groq:llama-3.3-70b-versatile"])
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "k"}):
            listed = c.get("/models").json()
        self.assertEqual(listed["default"], "ollama:gemma4:e4b")
        self.assertEqual([m["local"] for m in listed["models"]], [True, False])
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GROQ_API_KEY", None)
            self.assertEqual(len(c.get("/models").json()["models"]), 1)   # no key, not offered

        q = {"question": "হত্যার শাস্তি কী?"}
        self.assertIn("মৃত্যুদণ্ড", c.post("/ask", json=q).json()["answer"])
        with mock.patch("rag.llm.get_llm", return_value=big), \
                mock.patch("rag.llm.get_stream_llm", return_value=lambda s, p: iter(["x"])):
            r = c.post("/ask", json={**q, "model": "groq:llama-3.3-70b-versatile"})
        self.assertIn("বড় মডেলের", r.json()["answer"])                  # not served from cache
        self.assertEqual(c.post("/ask", json={**q, "model": "groq:anything"}).status_code, 400)

    def test_api_key_required_when_configured(self):
        c = self.client(api_keys={"secret": 60}, require_api_key=True)
        self.assertEqual(c.post("/ask", json={"question": "কী?"}).status_code, 401)
        ok = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}, headers={"x-api-key": "secret"})
        self.assertEqual(ok.status_code, 200)

    def test_feedback_is_recorded_against_the_answer(self):
        c = self.client()
        answer_id = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["id"]
        self.assertEqual(c.post("/feedback", json={"id": answer_id, "rating": "up"}).status_code, 200)
        self.assertEqual(c.post("/feedback", json={"id": answer_id, "rating": "maybe"}).status_code, 400)
        rows = [json.loads(line) for line in
                Path(self.tmp, "feedback.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["rating"], "up")
        self.assertEqual(rows[0]["question"], "হত্যার শাস্তি কী?")   # the eval set of tomorrow

    def test_permalink_returns_the_same_answer(self):
        c = self.client()
        first = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        again = c.get(f"/a/{first['id']}").json()
        self.assertEqual(again["answer"], first["answer"])
        self.assertEqual(c.get("/a/deadbeef").status_code, 404)

    def test_shared_link_opened_in_a_browser_gets_the_page(self):
        c = self.client()
        answer_id = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["id"]
        page = c.get(f"/a/{answer_id}", headers={"accept": "text/html,application/xhtml+xml,*/*"})
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        data = c.get(f"/a/{answer_id}", headers={"accept": "application/json"})
        self.assertEqual(data.json()["id"], answer_id)

    def test_ui_assets_are_served(self):
        c = self.client()
        for path in ("/static/app.js", "/static/app.css", "/static/favicon.svg",
                     "/static/fonts/noto-sans-bengali-bengali-400-normal.woff2"):
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_stream_rejects_an_overlong_question(self):
        r = self.client().post("/ask/stream", json={"question": "x" * 501})
        self.assertEqual(r.status_code, 400)

    def test_framing_is_denied_unless_a_site_is_named(self):
        closed = self.client().get("/")
        self.assertEqual(closed.headers["x-frame-options"], "DENY")
        self.assertIn("frame-ancestors 'none'", closed.headers["content-security-policy"])
        space = self.client(frame_ancestors="https://huggingface.co").get("/")
        self.assertNotIn("x-frame-options", space.headers)
        self.assertIn("frame-ancestors 'self' https://huggingface.co",
                      space.headers["content-security-policy"])

    def test_multi_hop_question_is_routed_to_the_agent(self):
        script = iter(['ACTION: {"tool": "search", "args": {"query": "হত্যা", "k": 1}}',
                       "ANSWER: পার্থক্য এই [1]।"])
        c = self.client(llm=lambda s, p: next(script, "ANSWER: NOT_FOUND: done"))
        body = c.post("/ask", json={"question": "৩০২ ও ৩০৪ক এর পার্থক্য কী?"}).json()
        self.assertIsNotNone(body["stop_reason"])       # the agent ran, unasked

    def test_simple_question_is_not_routed_to_the_agent(self):
        body = self.client().post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertIsNone(body["stop_reason"])

    def test_cache_is_invalidated_by_a_new_index(self):
        c = self.client()
        c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        self.assertTrue(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["cached"])
        c.app.state.components["fingerprint"] = "different-index"
        self.assertFalse(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["cached"])

    def test_security_headers_and_cost_reporting(self):
        c = self.client()
        r = c.get("/health")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertIn("content-security-policy", r.headers)
        c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
        cost = c.get("/stats").json()["cost"]
        self.assertIn("projected_monthly_usd_at_200_per_day", cost)

    def test_answer_carries_confidence(self):
        body = self.client().post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        self.assertIn(body["confidence"]["label"], ("high", "medium", "low", "none"))


class TestAgentRouting(unittest.TestCase):
    def test_situations_and_comparisons_go_to_the_agent(self):
        from service.app import wants_agent
        self.assertTrue(wants_agent("My employer fired me without notice. What can I do?"))
        self.assertTrue(wants_agent("আমার স্বামী আমাকে মারধর করে, আমি কী করব?"))
        self.assertTrue(wants_agent("difference between theft and robbery"))
        self.assertFalse(wants_agent("What does section 302 of the Penal Code say?"))


if __name__ == "__main__":
    unittest.main()
