"""Admission control, circuit breaker, single-flight, JSON logs, and how the
service uses them: probes, body limit, load shedding and failing fast."""
import json
import logging
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from service.logs import JsonFormatter, request_id, safe_request_id  # noqa: E402
from service.resilience import Admission, Busy, CircuitBreaker, SingleFlight  # noqa: E402
from test_rag import CORPUS  # noqa: E402
from test_service import HAVE_STARLETTE, fake_components  # noqa: E402

if HAVE_STARLETTE:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app


class TestAdmission(unittest.TestCase):
    def test_queue_full_is_refused_at_once(self):
        adm = Admission(max_inflight=1, max_queue=1)
        entered, release = threading.Event(), threading.Event()

        def hold():
            with adm.slot():
                entered.set()
                release.wait(5)

        def wait_for_slot():
            with adm.slot():
                pass

        t1 = threading.Thread(target=hold)
        t1.start()
        entered.wait(5)
        t2 = threading.Thread(target=wait_for_slot)      # takes the one queue place
        t2.start()
        for _ in range(100):
            if adm.stats()["waiting"] == 1:
                break
            time.sleep(0.01)
        self.assertTrue(adm.full())
        with self.assertRaises(Busy), adm.slot():
            pass
        release.set()
        t1.join(5)
        t2.join(5)
        self.assertEqual(adm.stats(), {"inflight": 0, "waiting": 0, "max_inflight": 1,
                                       "max_queue": 1, "rejected": 1})
        self.assertFalse(adm.full())

    def test_zero_turns_it_off(self):
        adm = Admission(max_inflight=0)
        with adm.slot(), adm.slot():
            self.assertFalse(adm.full())

    def test_slot_is_released_when_the_work_fails(self):
        adm = Admission(max_inflight=1, max_queue=0)

        def crash():
            with adm.slot():
                raise ValueError("model crashed")

        self.assertRaises(ValueError, crash)
        with adm.slot():                                  # still usable
            self.assertEqual(adm.stats()["inflight"], 1)


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.cb = CircuitBreaker(threshold=2, cooldown_s=10, clock=lambda: self.now)

    def test_opens_after_consecutive_failures_only(self):
        self.cb.failure()
        self.cb.success()                                  # resets the count
        self.cb.failure()
        self.assertEqual(self.cb.allow(), "closed")
        self.cb.failure()
        self.assertEqual(self.cb.state, "open")
        self.assertIsNone(self.cb.allow())
        self.assertGreaterEqual(self.cb.retry_after(), 1.0)

    def test_half_open_allows_one_trial(self):
        self.cb.failure()
        self.cb.failure()
        self.now = 11
        self.assertEqual(self.cb.state, "half_open")
        self.assertEqual(self.cb.allow(), "trial")
        self.assertIsNone(self.cb.allow())                 # only one at a time
        self.cb.success()
        self.assertEqual(self.cb.state, "closed")
        self.assertEqual(self.cb.trips, 1)

    def test_failed_trial_reopens_for_a_full_cooldown(self):
        self.cb.failure()
        self.cb.failure()
        self.now = 11
        self.assertEqual(self.cb.allow(), "trial")
        self.cb.failure()
        self.assertEqual(self.cb.state, "open")
        self.now = 15
        self.assertIsNone(self.cb.allow())
        self.assertEqual(self.cb.trips, 2)

    def test_released_trial_lets_the_next_one_in(self):
        self.cb.failure()
        self.cb.failure()
        self.now = 11
        self.assertEqual(self.cb.allow(), "trial")
        self.cb.release_trial()
        self.assertEqual(self.cb.allow(), "trial")

    def test_disabled(self):
        cb = CircuitBreaker(threshold=0)
        for _ in range(5):
            cb.failure()
        self.assertEqual(cb.allow(), "closed")


class TestSingleFlight(unittest.TestCase):
    def test_concurrent_callers_share_one_run(self):
        sf = SingleFlight()
        calls, started, release = [], threading.Event(), threading.Event()

        def slow():
            calls.append(1)
            started.set()
            release.wait(5)
            return "answer"

        results = []
        leader = threading.Thread(target=lambda: results.append(sf.do("q", slow)))
        leader.start()
        started.wait(5)
        followers = [threading.Thread(target=lambda: results.append(sf.do("q", slow)))
                     for _ in range(3)]
        for t in followers:
            t.start()
        for _ in range(100):
            if sf.shared == 3:
                break
            time.sleep(0.01)
        release.set()
        for t in [leader, *followers]:
            t.join(5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sorted(results), [("answer", False)] + [("answer", True)] * 3)
        self.assertEqual(sf.do("q", lambda: "again"), ("again", False))   # not a cache

    def test_error_reaches_every_waiter(self):
        sf = SingleFlight()
        with self.assertRaises(RuntimeError):
            sf.do("q", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        self.assertEqual(sf.do("q", lambda: 1), (1, False))


class TestLogs(unittest.TestCase):
    def test_request_id_must_be_plain(self):
        self.assertEqual(safe_request_id("abc-123_x.y:z"), "abc-123_x.y:z")
        for bad in ("", None, "a\nfake log line", 'x"y', "a" * 65, "ü"):
            self.assertIsNone(safe_request_id(bad))

    def test_json_lines_carry_the_request_id_and_merge_json_messages(self):
        fmt = JsonFormatter()
        token = request_id.set("rid42")
        try:
            rec = logging.LogRecord("service", logging.INFO, __file__, 1,
                                    json.dumps({"path": "/ask", "status": 200}), None, None)
            out = json.loads(fmt.format(rec))
            plain = json.loads(fmt.format(logging.LogRecord(
                "rag", logging.WARNING, __file__, 1, "slow %s", ("rerank",), None)))
        finally:
            request_id.reset(token)
        self.assertEqual((out["path"], out["status"], out["request_id"]), ("/ask", 200, "rid42"))
        self.assertEqual((plain["msg"], plain["level"], plain["request_id"]),
                         ("slow rerank", "warning", "rid42"))


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceResilience(unittest.TestCase):
    def client(self, llm=None, **cfg_kw):
        pipeline, default_llm, stream = fake_components()
        cfg = ServiceConfig(**{"rate_per_min": 6000, "burst": 100, **cfg_kw})
        app = create_app(cfg, pipeline=pipeline, llm=llm or default_llm, stream_llm=stream,
                         records=CORPUS)
        return TestClient(app)

    def test_probes(self):
        c = self.client()
        self.assertEqual(c.get("/livez").json(), {"status": "alive"})
        ready = c.get("/readyz")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["circuit"], "closed")

    def test_readyz_does_not_load_anything(self):
        app = create_app(ServiceConfig(index="/nonexistent"))
        c = TestClient(app)
        r = c.get("/readyz")
        self.assertEqual((r.status_code, r.json()["status"]), (503, "loading"))
        self.assertFalse(app.state.components["ready"])
        self.assertEqual(c.get("/livez").status_code, 200)

    def test_oversized_body_is_rejected(self):
        r = self.client(max_body_bytes=100).post("/ask", json={"question": "x" * 200})
        self.assertEqual(r.status_code, 413)

    def test_unsafe_request_id_is_replaced(self):
        r = self.client().get("/livez", headers={"x-request-id": "bad id\twith tab"})
        self.assertNotIn("\t", r.headers["x-request-id"])
        self.assertEqual(len(r.headers["x-request-id"]), 12)

    def test_open_circuit_answers_from_retrieval_without_calling_the_model(self):
        from rag.llm import LLMError

        calls = []

        def dead(system, prompt):
            calls.append(1)
            raise LLMError("ollama not running")

        c = self.client(llm=dead, breaker_failures=2, breaker_cooldown_s=60)
        for q in ("হত্যার শাস্তি কী?", "চুরির শাস্তি কী?"):
            self.assertEqual(c.post("/ask", json={"question": q}).status_code, 503)
        made = len(calls)
        r = c.post("/ask", json={"question": "ধারা ৩০২ কী বলে?"})
        self.assertEqual(r.status_code, 503)
        self.assertTrue(r.json()["degraded"])
        self.assertIn("paused", r.json()["error"])
        self.assertTrue(r.json()["sources"])
        self.assertIn("retry-after", r.headers)
        self.assertEqual(len(calls), made)                 # the model was not called
        stream = c.post("/ask/stream", json={"question": "ধারা ৩০২ কী বলে?"})
        self.assertEqual(stream.status_code, 503)
        self.assertEqual(len(calls), made)
        self.assertIn('circuit_open 1', c.get("/metrics").text)

    def test_full_queue_sheds_to_retrieval(self):
        c = self.client(max_inflight=1, max_queue=0)
        adm = c.app.state.admission
        with adm.slot():                                   # someone else's answer is running
            r = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
            s = c.post("/ask/stream", json={"question": "চুরির শাস্তি কী?"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("too many questions", r.json()["error"])
        self.assertEqual(s.status_code, 503)
        self.assertIn("shed_total 2", c.get("/metrics").text)
        self.assertEqual(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).status_code, 200)

    def test_streamed_answer_is_cached_and_replayed(self):
        c = self.client()
        q = {"question": "হত্যার শাস্তি কী?"}
        first = c.post("/ask/stream", json=q).text
        self.assertIn("event: token", first)
        again = c.post("/ask/stream", json=q).text
        self.assertNotIn("event: token", again)
        final = json.loads(again.split("data: ", 1)[1])
        self.assertTrue(final["cached"])
        self.assertTrue(c.post("/ask", json=q).json()["cached"])   # shared with /ask
        self.assertIn("ttft_seconds_count 1", c.get("/metrics").text)

    def test_feedback_is_rate_limited(self):
        c = self.client(rate_per_min=1, burst=1)
        codes = [c.post("/feedback", json={"id": "x", "rating": "up"}).status_code
                 for _ in range(4)]
        self.assertIn(429, codes)

    def test_metrics_token(self):
        c = self.client(metrics_token="s3cret")
        self.assertEqual(c.get("/metrics").status_code, 401)
        ok = c.get("/metrics", headers={"authorization": "Bearer s3cret"})
        self.assertEqual(ok.status_code, 200)

    def test_metrics_are_labelled_by_route_not_raw_path(self):
        c = self.client()
        c.get("/a/abc123")
        c.get("/a/def456")
        c.get("/wp-login.php")
        text = c.get("/metrics").text
        self.assertIn('path="/a/{answer_id}"', text)
        self.assertNotIn("abc123", text)
        self.assertIn('path="unmatched"', text)
        self.assertNotIn("wp-login", text)


class TestLoadTestSLO(unittest.TestCase):
    def test_summary_and_breaches(self):
        from bdrag_tools.loadtest import slo_breaches, summarize

        results = [(0.01 * i, 200) for i in range(1, 20)] + [(2.0, 500)]
        s = summarize(results, elapsed=2.0)
        self.assertEqual((s["requests"], s["ok"], s["error_rate"]), (20, 19, 0.05))
        self.assertEqual(s["p95_ms"], 2000.0)
        self.assertEqual(slo_breaches(s, None, None), [])
        self.assertEqual(len(slo_breaches(s, 500, 0.0)), 2)
        self.assertEqual(slo_breaches(s, 2500, 0.1), [])
        self.assertEqual(slo_breaches(summarize([], 1.0), None, None), ["no requests completed"])


if __name__ == "__main__":
    unittest.main()
