"""bdrag coverage (which acts lack text) and bdrag feedback-to-eval."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bdrag_tools.coverage import classify  # noqa: E402
from bdrag_tools.feedback_to_eval import drafts, known_questions  # noqa: E402

ACT_PAGE = (ROOT / "tests/fixtures/act-1037.html").read_text(encoding="utf-8")
SCANNED = ('<html><body><h3>কোনো আইন, ১৯৭২</h3>'
           '<a href="/upload/act/1972-scan.pdf">PDF</a></body></html>')


class TestCoverage(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(classify(ACT_PAGE, 1037, True, False)[0], "indexed")
        self.assertEqual(classify(None, 5, False, True)[0], "repealed")
        self.assertEqual(classify(None, 5, False, False)[0], "not_downloaded")
        bucket, pdfs = classify(SCANNED, 9, False, False)
        self.assertEqual((bucket, pdfs), ("scanned", ["/upload/act/1972-scan.pdf"]))
        self.assertEqual(classify(ACT_PAGE, 1037, False, False)[0], "not_ingested")


class TestFeedbackToEval(unittest.TestCase):
    def test_only_new_thumbs_down_become_drafts(self):
        rows = [
            {"id": "a1", "rating": "down", "question": "বাড়িওয়ালা ভাড়া দ্বিগুণ করলে?",
             "comment": "missed s.7", "sources": ["748:30648"], "ts": 10},
            {"id": "a2", "rating": "up", "question": "What is bail?", "ts": 10},
            {"id": "a3", "rating": "down", "question": "বাড়িওয়ালা  ভাড়া দ্বিগুণ করলে?", "ts": 11},
            {"id": "a4", "rating": "down", "question": "What is the punishment for murder in Bangladesh?",
             "ts": 12},
        ]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "eval.jsonl").write_text(
                (ROOT / "data/eval/eval.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
            (Path(d) / "drafts.jsonl").write_text(json.dumps({"question": "old"}) + "\n",
                                                  encoding="utf-8")
            seen = known_questions(Path(d))
        out = drafts(rows, seen)
        self.assertEqual([o["id"] for o in out], ["fb-a1"])   # duplicate, upvote, known: skipped
        self.assertEqual((out[0]["language"], out[0]["gold"], out[0]["system_cited"]),
                         ("bn", [], ["748:30648"]))


if __name__ == "__main__":
    unittest.main()
