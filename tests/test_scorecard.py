"""The published accuracy scorecard: numbers in only from result files, pages never stale."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from bdrag_tools import scorecard as tool  # noqa: E402
from evalkit import scorecard as sc  # noqa: E402

try:
    from starlette.testclient import TestClient

    from service.app import ServiceConfig, create_app
    from test_service import fake_components
    HAVE_STARLETTE = True
except ImportError:                       # pragma: no cover
    HAVE_STARLETTE = False


def stat(mean, n=86):
    return {"mean": mean, "lo": mean - 0.05, "hi": min(1.0, mean + 0.05), "n": n}


E2E = {"label": "x", "timestamp": "2026-11-02T10:00:00+00:00",
       "config": {"k": 5, "answer_llm": "ollama", "answer_model": "gemma4:e4b", "judge_llm": "none",
                  "mode": "dense", "topics": True, "rerank": "none", "eval": "data/eval/eval.jsonl"},
       "dataset": {"n": 96, "answerable": 86},
       "overall": {"recall@5": stat(0.93), "mrr": stat(0.8)},
       "by_language": {"bn": {"recall@5": stat(0.9, 37)}, "en": {"recall@5": stat(0.95, 44)}},
       "generation": {"refusal_correct": stat(0.9, 96), "citation_validity": stat(1.0, 96),
                      "citation_precision": stat(0.7), "citation_support": stat(0.8),
                      "gold_cited": stat(0.75), "correctness": {"mean": float("nan"), "lo": 0,
                                                                "hi": 0, "n": 0}}}


class TestFromResult(unittest.TestCase):
    def test_answers_block_names_the_model_and_skips_unmeasured_rows(self):
        b = sc.from_result("answers", E2E, "results/published/x.json")
        self.assertEqual(b["date"], "2026-11-02")
        self.assertIn("answers by gemma4:e4b", b["setup"])
        self.assertIn("topic table", b["setup"])
        self.assertNotIn("judged", b["setup"])
        self.assertEqual(b["metrics"]["citation_support"]["value"], 0.8)
        self.assertNotIn("correctness", b["metrics"])       # --no-judge: no number, no row

    def test_retrieval_block_has_both_languages(self):
        b = sc.from_result("retrieval", E2E, "r.json")
        self.assertEqual(set(b["metrics"]), {"recall@5", "mrr", "recall@5 bn", "recall@5 en"})

    def test_wrong_file_for_the_kind_is_refused(self):
        with self.assertRaises(ValueError):
            sc.from_result("answers", {**E2E, "generation": None}, "r.json")
        with self.assertRaises(ValueError):
            sc.from_result("lawyer", E2E, "r.json")
        with self.assertRaises(ValueError):           # static-only file is not a model run
            sc.from_result("redteam_llm", {"summary": {"n": 1, "passed": 1, "by_attack": {}},
                                           "results": [{"answer": None}]}, "r.json")

    def test_lawyer_block_carries_the_launch_bar(self):
        report = {"graded": 40, "overall": {
            "accurate": {"n": 40, "yes_rate": 0.9, "ci95": [0.77, 0.96]},
            "safe": {"n": 40, "yes_rate": 1.0, "ci95": [0.91, 1.0]}},
            "unsafe": [], "checks": {"no answer graded unsafe": True}, "launch_bar_met": True}
        b = sc.from_result("lawyer", report, "l.json", setup="graded by an advocate")
        self.assertTrue(b["launch_bar_met"])
        self.assertEqual(b["metrics"]["accurate"]["value"], 0.9)
        self.assertNotIn("clear", b["metrics"])
        card = {**sc.load(), "blocks": {**sc.load()["blocks"], "lawyer": b}}
        self.assertIn("Launch bar **met**", sc.markdown(card))
        self.assertIn("| Fully accurate, graded by a lawyer | 90% (77%–96%) |", sc.readme_block(card))


class TestPublished(unittest.TestCase):
    def test_committed_pages_match_the_scorecard(self):
        self.assertEqual(tool.check(sc.load()), [])

    def test_every_block_is_shown_measured_or_pending(self):
        card = sc.load()
        text = sc.markdown(card)
        for kind, (heading, *_rest) in sc.KINDS.items():
            self.assertIn(f"## {heading}", text)
            if card["blocks"][kind] is None:
                self.assertIn("not measured yet", sc.readme_block(card))

    def test_published_sources_are_in_git(self):
        for kind, b in sc.load()["blocks"].items():
            if b:
                self.assertTrue((ROOT / b["source"]).exists(), f"{kind}: {b['source']}")

    def test_add_copies_an_ignored_result_and_rerenders(self):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp, "card.json")
            card.write_text(json.dumps(sc.load()), encoding="utf-8")
            (Path(tmp) / "results").mkdir()
            src = Path(tmp, "results", "e2e.json")          # results/*.json is git-ignored
            src.write_text(json.dumps(E2E), encoding="utf-8")
            old = (sc.MARKDOWN, sc.README, sc.ROOT)
            readme = Path(tmp, "README.md")
            readme.write_text(f"x\n{sc.START}\n{sc.END}\ny\n", encoding="utf-8")
            (Path(tmp) / "docs").mkdir()
            sc.MARKDOWN, sc.README, sc.ROOT = Path(tmp, "docs", "ACCURACY.md"), readme, Path(tmp)
            try:
                self.assertEqual(tool.main(["--card", str(card), "add", "answers", str(src),
                                            "--short", "gemma4:e4b, laptop CPU"]), 0)
            finally:
                sc.MARKDOWN, sc.README, sc.ROOT = old
            block = json.loads(card.read_text(encoding="utf-8"))["blocks"]["answers"]
            self.assertTrue(block["source"].startswith("results/published/answers-"))
            self.assertTrue(Path(tmp, block["source"]).exists())
            text = readme.read_text(encoding="utf-8")
            self.assertIn("gemma4:e4b, laptop CPU", text)
            self.assertTrue(text.startswith("x\n") and text.endswith("\ny\n"))


@unittest.skipUnless(HAVE_STARLETTE, "starlette not installed")
class TestAccuracyPage(unittest.TestCase):
    def setUp(self):
        pipeline, llm, stream = fake_components()
        self.c = TestClient(create_app(ServiceConfig(rate_per_min=6000, burst=100),
                                       pipeline=pipeline, llm=llm, stream_llm=stream))

    def test_page_is_served_in_both_languages_with_the_gaps(self):
        r = self.c.get("/accuracy")
        self.assertEqual(r.status_code, 200)
        self.assertIn("How accurate is it?", r.text)
        self.assertIn("এটি কতটা নির্ভুল?", r.text)
        self.assertIn("Not measured yet", r.text)
        self.assertIn("52/52", r.text)
        self.assertIn('href="/accuracy"', self.c.get("/").text)
        self.assertIn("Allow: /accuracy", self.c.get("/robots.txt").text)

    def test_numbers_are_served_as_json(self):
        r = self.c.get("/static/scorecard.json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("blocks", r.json())

    def test_notes_are_escaped(self):
        card = sc.load()
        card["caveats"] = ["<script>alert(1)</script> and `code`"]
        page = sc.html_page(card)
        self.assertNotIn("<script>alert", page)
        self.assertIn("<code>code</code>", page)


if __name__ == "__main__":
    unittest.main()
