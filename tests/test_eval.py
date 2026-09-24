"""Phase 3 tests — metrics are code too, and wrong metrics are worse than none."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evalkit.dataset import EvalItem, load_eval, section_key, slice_stats, validate  # noqa: E402
from evalkit.judge import _parse_json, deterministic_scores  # noqa: E402
from evalkit.metrics import (  # noqa: E402
    aggregate,
    hit_at_k,
    mrr,
    ndcg_at_k,
    paired_bootstrap,
    precision_at_k,
    recall_at_k,
)
from evalkit.runner import by_slice, run_retrieval, summarize  # noqa: E402
from rag.answer import Answer  # noqa: E402
from rag.embed import HashingEmbedder  # noqa: E402
from rag.retrieve import Retriever  # noqa: E402
from rag.store import Hit, NumpyStore  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_rag import CORPUS  # noqa: E402  (reuse the tiny corpus)


class TestMetrics(unittest.TestCase):
    def test_ranks_ignore_duplicate_sections(self):
        # two chunks of section 1:2, then the gold section
        retrieved = ["1:2", "1:2", "1:9"]
        self.assertEqual(mrr(retrieved, {"1:9"}), 0.5)      # gold is 2nd unique section
        self.assertEqual(hit_at_k(retrieved, {"1:9"}, 1), 0.0)
        self.assertEqual(hit_at_k(retrieved, {"1:9"}, 2), 1.0)

    def test_recall_and_precision_multi_gold(self):
        retrieved = ["a", "b", "c", "d"]
        gold = {"b", "d", "z"}
        self.assertAlmostEqual(recall_at_k(retrieved, gold, 4), 2 / 3)
        self.assertAlmostEqual(recall_at_k(retrieved, gold, 2), 1 / 3)
        self.assertAlmostEqual(precision_at_k(retrieved, gold, 4), 2 / 4)

    def test_perfect_and_empty(self):
        self.assertEqual(mrr(["g"], {"g"}), 1.0)
        self.assertEqual(ndcg_at_k(["g", "x"], {"g"}, 2), 1.0)
        self.assertEqual(mrr(["x"], {"g"}), 0.0)
        self.assertEqual(recall_at_k([], {"g"}, 5), 0.0)

    def test_ndcg_rewards_higher_rank(self):
        high = ndcg_at_k(["g", "x", "y"], {"g"}, 3)
        low = ndcg_at_k(["x", "y", "g"], {"g"}, 3)
        self.assertGreater(high, low)

    def test_unanswerable_returns_nan_and_is_skipped(self):
        self.assertTrue(math.isnan(recall_at_k(["a"], set(), 5)))
        agg = aggregate([{"recall@5": 1.0}, {"recall@5": float("nan")}, {"recall@5": 0.0}])
        self.assertEqual(agg["recall@5"]["n"], 2)
        self.assertAlmostEqual(agg["recall@5"]["mean"], 0.5)

    def test_bootstrap_ci_brackets_the_mean(self):
        agg = aggregate([{"m": v} for v in [1, 1, 1, 0, 1, 1, 0, 1, 1, 1]])
        s = agg["m"]
        self.assertLessEqual(s["lo"], s["mean"])
        self.assertLessEqual(s["mean"], s["hi"])

    def test_paired_bootstrap_detects_real_and_noise(self):
        a = [0] * 20
        better = paired_bootstrap(a, [1] * 20)
        self.assertGreater(better["lo"], 0)               # clearly better
        same = paired_bootstrap([0, 1] * 10, [1, 0] * 10)
        self.assertLessEqual(same["lo"], 0)               # within noise
        self.assertGreaterEqual(same["hi"], 0)


class TestDataset(unittest.TestCase):
    def good(self, **kw):
        d = {"id": "q1", "question": "কী?", "language": "bn", "type": "single",
             "gold": ["1:2"], "reference_answer": "উত্তর"}
        d.update(kw)
        return EvalItem(**d)

    def test_valid_set_has_no_problems(self):
        self.assertEqual(validate([self.good()], {"1:2"}), [])

    def test_catches_common_mistakes(self):
        items = [
            self.good(id="a", question=""),                                  # unfilled template
            self.good(id="a"),                                               # duplicate id
            self.good(id="b", gold=[]),                                      # answerable, no gold
            self.good(id="c", type="unanswerable", gold=["1:2"]),            # refusal item with gold
            self.good(id="d", type="multi", gold=["1:2"]),                   # multi with one gold
            self.good(id="e", gold=["9:9"]),                                 # gold not in corpus
            self.good(id="f", reference_answer=""),                          # no reference
            self.good(id="g", language="bangla"),                            # bad language code
        ]
        problems = " | ".join(validate(items, {"1:2"}))
        for expect in ("empty question", "duplicate id", "no gold sections",
                       "must have gold == []", "at least 2 gold", "not in the corpus",
                       "no reference answer", "language must be"):
            self.assertIn(expect, problems)

    def test_duplicate_questions_detected(self):
        items = [self.good(id="a", question="একই প্রশ্ন"), self.good(id="b", question="একই   প্রশ্ন")]
        self.assertTrue(any("duplicate question" in p for p in validate(items)))

    def test_loads_sample_file_and_ignores_extra_keys(self):
        items = load_eval(ROOT / "data/eval/sample_eval.jsonl")
        self.assertGreaterEqual(len(items), 6)
        stats = slice_stats(items)
        self.assertEqual(stats["unanswerable"], 1)
        self.assertEqual(stats["n"], stats["answerable"] + stats["unanswerable"])

    def test_section_key(self):
        self.assertEqual(section_key({"act_id": 1037, "section_id": 40548}), "1037:40548")


class TestJudgeDeterministic(unittest.TestCase):
    def hits(self, keys):
        out = []
        for i, k in enumerate(keys):
            act, sec = k.split(":")
            out.append(Hit(f"c{i}", 0.5, "t", "b",
                           {"act_id": int(act), "section_id": int(sec), "act_title": "A",
                            "language": "bn", "section_number": "১"}))
        return out

    def test_gold_cited_vs_merely_retrieved(self):
        item = EvalItem("q1", "কী?", "bn", "single", ["1:2"], "ref")
        ans = Answer("কী?", "উত্তর [2]", self.hits(["1:9", "1:2"]), cited=[2])
        s = deterministic_scores(item, ans)
        self.assertEqual(s["gold_retrieved"], 1.0)
        self.assertEqual(s["gold_cited"], 1.0)
        self.assertEqual(s["citation_precision"], 1.0)

        ans2 = Answer("কী?", "উত্তর [1]", self.hits(["1:9", "1:2"]), cited=[1])
        s2 = deterministic_scores(item, ans2)
        self.assertEqual(s2["gold_retrieved"], 1.0)   # it was there
        self.assertEqual(s2["gold_cited"], 0.0)       # but the answer used the wrong one
        self.assertEqual(s2["citation_precision"], 0.0)

    def test_refusal_scoring_both_ways(self):
        unans = EvalItem("q2", "VAT?", "en", "unanswerable", [], "")
        refused = Answer("VAT?", "NOT_FOUND: nothing here", self.hits(["1:9"]), refused=True)
        answered = Answer("VAT?", "It is 15% [1]", self.hits(["1:9"]), cited=[1])
        self.assertEqual(deterministic_scores(unans, refused)["refusal_correct"], 1.0)
        self.assertEqual(deterministic_scores(unans, answered)["refusal_correct"], 0.0)

        ansbl = EvalItem("q3", "কী?", "bn", "single", ["1:2"], "ref")
        self.assertEqual(deterministic_scores(ansbl, refused)["refusal_correct"], 0.0)

    def test_invalid_citation_flagged(self):
        item = EvalItem("q4", "কী?", "bn", "single", ["1:2"], "ref")
        ans = Answer("কী?", "দেখুন [7]", self.hits(["1:2"]), cited=[], invalid_citations=[7])
        self.assertEqual(deterministic_scores(item, ans)["citation_validity"], 0.0)

    def test_judge_json_parsing_is_tolerant(self):
        self.assertEqual(_parse_json('noise {"score": 0.5, "reason": "x"} trailing')["score"], 0.5)
        self.assertEqual(_parse_json("not json at all"), {})


class TestRunner(unittest.TestCase):
    def setUp(self):
        emb = HashingEmbedder(dim=256)
        store = NumpyStore(emb.dim, emb.name)
        store.add(emb.encode_passages([c["text"] for c in CORPUS]), CORPUS)
        self.retriever = Retriever(emb, store)
        self.items = [
            EvalItem("q1", "হত্যার শাস্তি কী?", "bn", "single", ["1:302"], "মৃত্যুদণ্ড"),
            EvalItem("q2", "death by negligence", "en", "single", ["2:304"], "imprisonment"),
            EvalItem("q3", "What is the VAT rate?", "en", "unanswerable", [], ""),
        ]

    def test_run_scores_answerable_only(self):
        run = run_retrieval(self.items, self.retriever, k=5)
        self.assertEqual(len(run["records"]), 3)
        self.assertEqual(len(run["per_query"]), 2)     # unanswerable has no retrieval score
        self.assertEqual(run["per_query"][0]["recall@5"], 1.0)

    def test_summary_shape_and_slices(self):
        run = run_retrieval(self.items, self.retriever, k=5)
        s = summarize("test", {"k": 5}, self.items, run)
        self.assertEqual(s["dataset"]["n"], 3)
        self.assertIn("recall@5", s["overall"])
        self.assertEqual(set(s["by_language"]), {"bn", "en"})
        self.assertEqual(by_slice(run["per_query"], "type")["single"]["recall@5"]["n"], 2)


if __name__ == "__main__":
    unittest.main()


class TestReport(unittest.TestCase):
    """The ablation table and the paired verdicts that go in the README."""

    def run_payload(self, label, recall, per_query, config=None):
        return {
            "label": label, "config": config or {"mode": "hybrid", "k": 5, "expand_refs": True},
            "overall": {"recall@5": {"mean": recall, "lo": recall - 0.05, "hi": recall + 0.05,
                                     "n": len(per_query)}},
            "latency_s": {"median": 0.1, "p95": 0.2},
            "per_query": [{"id": f"q{i}", "recall@5": v} for i, v in enumerate(per_query)],
        }

    def test_table_describes_the_pipeline_and_sorts_by_score(self):
        from evalkit.report import describe, markdown_table
        runs = [self.run_payload("base", 0.5, [0, 1, 0, 1]),
                self.run_payload("better", 0.9, [1, 1, 1, 1])]
        table = markdown_table(runs)
        self.assertLess(table.index("better"), table.index("base"))   # best row first
        self.assertIn("hybrid +refs", table)
        self.assertEqual(describe({"mode": "dense", "rerank": "cross", "multi_query": 2}),
                         "dense +mq2 +rerank(cross)")

    def test_paired_report_says_better_worse_or_noise(self):
        from evalkit.report import paired_report
        base = self.run_payload("base", 0.25, [0, 0, 0, 1] * 5)
        better = self.run_payload("better", 1.0, [1] * 20)
        same = self.run_payload("same", 0.25, [0, 0, 0, 1] * 5)
        out = paired_report([base, better, same], "base")
        self.assertIn("better", out)
        self.assertIn("within noise", out)

    def test_paired_report_handles_a_missing_baseline(self):
        from evalkit.report import paired_report
        self.assertIn("no run labelled", paired_report([self.run_payload("a", 0.5, [1, 0])], "zzz"))
