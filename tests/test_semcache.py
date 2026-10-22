"""Paraphrase cache (service/semcache.py): the gates, the cache, the service wiring
and the tuning command. Everything runs on the hashing embedder; the bge-m3
threshold itself is measured with `bdrag semcache` (docs/reports)."""
import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rag.embed import CachedQueryEmbedder, HashingEmbedder  # noqa: E402
from service.semcache import (  # noqa: E402
    TUNED,
    Probe,
    SemanticCache,
    negations,
    numbers,
    overlap,
    resolve_threshold,
    script,
    signature,
)
from test_service import HAVE_STARLETTE, fake_components  # noqa: E402

if HAVE_STARLETTE:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app


def unit(*xs):
    v = np.asarray(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def probe(q, vec, scope="s", evidence=frozenset({(1, 1)}), topics=()):
    return Probe(q, vec, signature(q, scope, topics), frozenset(evidence))


class TestGates(unittest.TestCase):
    def test_script(self):
        self.assertEqual(script("What is the punishment for murder?"), "latin")
        self.assertEqual(script("চুরির শাস্তি কী?"), "bn")
        self.assertEqual(script("chorir shasti ki"), "latin")
        self.assertEqual(script("Labour Act অনুযায়ী maternity leave কত দিন?"), "mixed")

    def test_numbers_fold_bangla_digits(self):
        self.assertEqual(numbers("ধারা ৩০২"), numbers("section 302"))
        self.assertNotEqual(numbers("section 302"), numbers("section 304"))
        self.assertEqual(numbers("no digits"), frozenset())

    def test_negations(self):
        self.assertEqual(negations("Can the landlord evict me?"), 0)
        self.assertEqual(negations("Can the landlord evict me without notice?"), 1)
        self.assertEqual(negations("I can't pay"), 1)
        self.assertEqual(negations("ভাড়াটিয়া ভাড়া না দিলে কি উচ্ছেদ করা যায়?"), 1)
        self.assertEqual(negations("মালিক বেতন দেয়নি"), 1)
        self.assertEqual(negations("ভাড়াটিয়া নিয়মিত ভাড়া দিলে কি উচ্ছেদ করা যায়?"), 0)

    def test_signature_separates_what_changes_the_answer(self):
        base = signature("What is the punishment for murder?", "s")
        self.assertEqual(base, signature("what is the penalty for murder", "s"))
        self.assertNotEqual(base, signature("What is the punishment for murder?", "other"))
        self.assertNotEqual(base, signature("হত্যার শাস্তি কী?", "s"))
        self.assertNotEqual(base, signature("Is murder not punished?", "s"))
        self.assertNotEqual(base, signature("What is the punishment for murder?", "s", ["dowry"]))

    def test_overlap(self):
        self.assertEqual(overlap(frozenset(), frozenset()), 1.0)
        self.assertAlmostEqual(overlap(frozenset({1, 2, 3, 4, 5}), frozenset({1, 2, 3, 4, 6})), 4 / 6)

    def test_resolve_threshold(self):
        self.assertEqual(resolve_threshold("auto", "BAAI/bge-m3"), TUNED["BAAI/bge-m3"])
        self.assertIsNone(resolve_threshold("auto", "hashing-256"))
        self.assertIsNone(resolve_threshold("off", "BAAI/bge-m3"))
        self.assertEqual(resolve_threshold("0.9", "hashing-256"), 0.9)
        with self.assertRaises(ValueError):
            resolve_threshold("1.5", None)


class TestSemanticCache(unittest.TestCase):
    def test_match_needs_threshold_signature_and_evidence(self):
        c = SemanticCache(threshold=0.95)
        c.add("k1", probe("What is the punishment for murder?", unit(1, 0)))
        self.assertEqual(c.lookup(probe("what is the penalty for murder", unit(1, 0.1))).key, "k1")
        self.assertIsNone(c.lookup(probe("what is the penalty for murder", unit(1, 1))))
        self.assertIsNone(c.lookup(probe("What is the punishment for murder?", unit(1, 0),
                                         scope="other")))
        self.assertIsNone(c.lookup(probe("What is the punishment for murder?", unit(1, 0),
                                         evidence={(9, 9)})))
        self.assertEqual(c.stats()["hits"], 1)

    def test_best_match_wins(self):
        c = SemanticCache(threshold=0.9)
        c.add("far", probe("a", unit(1, 0.3)))
        c.add("near", probe("b", unit(1, 0.05)))
        m = c.lookup(probe("c", unit(1, 0)))
        self.assertEqual((m.key, m.question), ("near", "b"))

    def test_ttl_and_size(self):
        c = SemanticCache(threshold=0.9, ttl_s=0.01)
        c.add("k", probe("a", unit(1, 0)))
        time.sleep(0.02)
        self.assertIsNone(c.lookup(probe("a", unit(1, 0))))
        self.assertEqual(c.stats()["size"], 0)
        c = SemanticCache(threshold=0.9, max_size=2)
        for i in range(3):
            c.add(f"k{i}", probe("a", unit(1, i)))
        self.assertEqual(c.stats()["size"], 2)


class TestCachedQueryEmbedder(unittest.TestCase):
    def test_encodes_each_text_once_and_keeps_order(self):
        inner = HashingEmbedder(dim=64)
        calls = []
        original = inner.encode_queries
        inner.encode_queries = lambda texts: calls.append(list(texts)) or original(texts)
        emb = CachedQueryEmbedder(inner, size=2)
        first = emb.encode_queries(["a b", "c d", "a b"])
        self.assertEqual(calls, [["a b", "c d"]])
        np.testing.assert_allclose(first[0], first[2])
        np.testing.assert_allclose(emb.encode_queries(["c d"])[0], first[1])
        self.assertEqual(len(calls), 1)
        emb.encode_queries(["e f"])                  # evicts "a b"
        emb.encode_queries(["a b"])
        self.assertEqual(calls[-1], ["a b"])
        self.assertEqual((emb.name, emb.dim), (inner.name, inner.dim))


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestServiceParaphraseCache(unittest.TestCase):
    def client(self, setting="0.8", llm=None):
        pipeline, default_llm, stream = fake_components()
        calls = []

        def counting(system, prompt):
            calls.append(prompt)
            return (llm or default_llm)(system, prompt)
        cfg = ServiceConfig(rate_per_min=6000, burst=100, semantic_cache=setting)
        app = create_app(cfg, pipeline=pipeline, llm=counting, stream_llm=stream)
        return TestClient(app), calls

    def test_paraphrase_is_served_with_the_question_it_answered(self):
        c, calls = self.client()
        first = c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()
        second = c.post("/ask", json={"question": "হত্যার শাস্তি কী"}).json()
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["answer"], first["answer"])
        self.assertEqual(second["cache_match"]["question"], "হত্যার শাস্তি কী?")
        self.assertEqual(len(calls), 1)
        stats = c.get("/stats").json()["semantic_cache"]
        self.assertEqual((stats["hits"], stats["size"]), (1, 1))
        self.assertIn("semantic_cache_hits_total", c.get("/metrics").text)

    def test_streaming_shares_the_paraphrase_cache(self):
        c, _ = self.client()
        c.post("/ask/stream", json={"question": "হত্যার শাস্তি কী?"})
        r = c.post("/ask/stream", json={"question": "হত্যার শাস্তি কী"})
        events = [b for b in r.text.split("\n\n") if b.strip()]
        self.assertEqual(len(events), 1)
        final = json.loads(events[0].split("data: ", 1)[1])
        self.assertEqual(final["cache_match"]["question"], "হত্যার শাস্তি কী?")

    def test_a_different_section_number_is_never_merged(self):
        c, calls = self.client(setting="0.5")
        c.post("/ask", json={"question": "ধারা ৩০২ এর শাস্তি কী?"})
        second = c.post("/ask", json={"question": "ধারা ৩০৪ এর শাস্তি কী?"}).json()
        self.assertFalse(second["cached"])
        self.assertNotIn("cache_match", second)
        self.assertEqual(len(calls), 2)

    def test_refusals_are_not_offered_to_paraphrases(self):
        c, calls = self.client(llm=lambda s, p: "NOT_FOUND")
        self.assertTrue(c.post("/ask", json={"question": "হত্যার শাস্তি কী?"}).json()["refused"])
        self.assertNotIn("cache_match", c.post("/ask", json={"question": "হত্যার শাস্তি কী"}).json())
        self.assertEqual(c.get("/stats").json()["semantic_cache"]["size"], 0)

    def test_off_and_untuned_embedders_disable_it(self):
        for setting in ("off", "auto"):        # auto: no tuned value for the hashing embedder
            c, calls = self.client(setting=setting)
            c.post("/ask", json={"question": "হত্যার শাস্তি কী?"})
            self.assertFalse(c.post("/ask", json={"question": "হত্যার শাস্তি কী"}).json()["cached"])
            self.assertIsNone(c.get("/stats").json()["semantic_cache"])

    def test_bad_setting_fails_at_start(self):
        with self.assertRaises(ValueError):
            create_app(ServiceConfig(semantic_cache="2"), pipeline=fake_components()[0])


class TestTuningCommand(unittest.TestCase):
    def test_reports_and_fails_on_a_false_merge(self):
        from bdrag_tools.semcache import main, recommend

        self.assertAlmostEqual(recommend([0.958], 0.005), 0.965)
        self.assertAlmostEqual(recommend([], 0.005), 0.005)
        with tempfile.TemporaryDirectory() as tmp:
            pairs = Path(tmp) / "pairs.jsonl"
            pairs.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
                {"id": "p", "a": "চুরির শাস্তি কী?", "b": "চুরির শাস্তি কী", "same": True},
                {"id": "n", "a": "চুরির শাস্তি কী?", "b": "চুরির শাস্তি কি?", "same": False},
                {"id": "g", "a": "ধারা ৩০২ কী?", "b": "ধারা ৩০৪ কী?", "same": False},
            ]), encoding="utf-8")
            out = Path(tmp) / "out.json"
            args = ["--pairs", str(pairs), "--eval", "--embedder", "hashing", "--json-out", str(out)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([*args, "--threshold", "0.999"]), 0)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["false_merges"], 0)
            self.assertEqual({r["id"]: r["blocked_by"] for r in report["rows"]}["g"], "numbers")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([*args, "--threshold", "0.1"]), 1)


if __name__ == "__main__":
    unittest.main()
