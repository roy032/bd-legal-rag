"""calibrate_judge: export a CSV, read the graded copy back, compare with the judge."""
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bdrag_tools import calibrate_judge  # noqa: E402

ROWS = [
    {"id": f"q{i}", "question": f"question {i}", "answer": f"answer {i} [1]", "refused": False,
     "sources": [{"n": 1, "citation": "Act, section 1", "text": "excerpt"}],
     "judge": {"faithfulness": float(i % 2), "correctness": 1.0, "_faithfulness_reason": ""}}
    for i in range(4)]


def run(*argv: str) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["calibrate_judge", *argv]), redirect_stdout(out):
        calibrate_judge.main()
    return out.getvalue()


class TestCalibrateJudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.answers = self.dir / "run.answers.json"
        self.answers.write_text(json.dumps(ROWS), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_then_import_reports_agreement(self):
        sheet = self.dir / "grade.csv"
        labels = str(self.dir / "labels.jsonl")
        run(str(self.answers), "--export", str(sheet), "--sample", "4", "--labels", labels)
        with open(sheet, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 4)
        self.assertIn("excerpt", rows[0]["cited_excerpts"])
        for r in rows:                      # the human agrees with the judge on faithfulness
            r["human_faithful"] = str(int(r["id"][1:]) % 2)
            r["human_correct"] = "1"
        with open(sheet, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=calibrate_judge.COLUMNS)
            w.writeheader()
            w.writerows(rows)
        report = run(str(self.answers), "--import", str(sheet), "--report", "--labels", labels)
        self.assertIn("faithfulness: 4 graded answers", report)
        self.assertIn("raw agreement: 1.00", report)
        self.assertIn("correctness: 4 graded answers", report)

    def test_judge_verdicts_are_not_assumed(self):
        self.assertEqual(calibrate_judge.judge_verdicts({"judge": {"_faithfulness_reason": "x"}}), {})
        self.assertEqual(calibrate_judge.judge_verdicts(ROWS[1]), {"faithful": 1, "correct": 1})


if __name__ == "__main__":
    unittest.main()
