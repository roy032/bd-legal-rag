"""bdrag review: a balanced sample, a sheet a reviewer can fill, a score and a launch bar."""
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bdrag_tools import review  # noqa: E402

LANGS, TYPES = ("bn", "en"), ("single", "multi", "paraphrase")


def answers(n: int = 40) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({"id": f"q{i}", "repeat": 0, "question": f"question {i} <b>", "answer": f"answer {i} [1]",
                     "refused": i % 10 == 9,
                     "sources": [] if i % 10 == 9 else
                     [{"n": 1, "citation": f"Act, section {i}", "url": "http://bdlaws.minlaw.gov.bd/x",
                       "text": "law text"}]})
    # a --repeats run repeats ids; the reviewer grades the first only
    rows.append({**rows[0], "repeat": 1, "answer": "second run"})
    return rows


def meta(n: int = 40) -> dict:
    return {f"q{i}": {"id": f"q{i}", "language": LANGS[i % 2], "type": TYPES[i % 3],
                      "reference_answer": f"reference {i}"} for i in range(n)}


def graded(rows: list[dict], accurate="y", safe="y") -> list[dict]:
    return [{**r, "law": "y", "sections": "y", "accurate": accurate, "safe": safe, "clear": "p",
             "should_answer": "", "notes": ""} if r["refused"] == "no" else
            {**r, "should_answer": "n"} for r in rows]


class Sample(unittest.TestCase):
    def test_balanced_across_language_and_type(self):
        rows = review.load_answers_from(answers())
        self.assertEqual(len(rows), 40)
        picked = review.balanced_sample(rows, meta(), 12, seed=1)
        self.assertEqual(len(picked), 12)
        groups = {(meta()[r["id"]]["language"], meta()[r["id"]]["type"]) for r in picked}
        self.assertEqual(len(groups), 6)          # every group, 2 each
        self.assertEqual(picked, review.balanced_sample(rows, meta(), 12, seed=1))
        self.assertEqual(len(review.balanced_sample(rows, meta(), 100)), 40)


class SheetAndScore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        (self.dir / "a.json").write_text(json.dumps(answers()), encoding="utf-8")
        with open(self.dir / "eval.jsonl", "w", encoding="utf-8") as f:
            f.writelines(json.dumps(m) + "\n" for m in meta().values())

    def tearDown(self):
        self._tmp.cleanup()

    def sheet(self) -> list[dict]:
        with redirect_stdout(io.StringIO()):
            code = review.main(["sheet", str(self.dir / "a.json"), "--eval", str(self.dir / "eval.jsonl"),
                                "--n", "40", "--out", str(self.dir / "out")])
        self.assertEqual(code, 0)
        with open(self.dir / "out" / "grades.csv", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def write(self, rows: list[dict]) -> str:
        path = self.dir / "graded.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=review.COLUMNS)
            w.writeheader()
            w.writerows(rows)
        return str(path)

    def score(self, rows: list[dict], *extra: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = review.main(["score", self.write(rows), *extra])
        return code, out.getvalue()

    def test_sheet_has_every_column_and_escapes_the_page(self):
        rows = self.sheet()
        self.assertEqual(list(rows[0]), review.COLUMNS)
        self.assertEqual(sum(r["refused"] == "yes" for r in rows), 4)
        page = (self.dir / "out" / "review.html").read_text(encoding="utf-8")
        self.assertIn("question 0 &lt;b&gt;", page)
        self.assertNotIn("question 0 <b>", page.split("<script>")[0])
        self.assertIn("reference 0", page)
        self.assertIn('name="q0|accurate"', page)
        self.assertNotIn('name="q9|accurate"', page)   # declined: only should_answer
        self.assertIn('name="q9|should_answer"', page)
        self.assertNotIn("{{", page)

    def test_launch_bar_met(self):
        code, text = self.score(graded(self.sheet()))
        self.assertEqual(code, 0, text)
        self.assertIn("Launch bar **met**", text)
        self.assertIn("100%", text)

    def test_one_unsafe_answer_fails_the_bar(self):
        rows = graded(self.sheet())
        rows[0].update(safe="no", notes="wrong deadline: 30 days, not 60")
        code, text = self.score(rows)
        self.assertEqual(code, 1)
        self.assertIn("Graded unsafe", text)
        self.assertIn("wrong deadline", text)

    def test_bangla_values_partly_and_blank_cells(self):
        rows = graded(self.sheet(), accurate="আংশিক", safe="হ্যাঁ")
        rows[1]["accurate"] = ""
        report = review.score(review.read_grades(self.write(rows)))
        self.assertEqual(report["overall"]["accurate"]["partly"], 35)
        self.assertEqual(report["graded"], 35)
        self.assertFalse(report["launch_bar_met"])
        self.assertEqual(len(report["not_fully_accurate"]), 35)

    def test_unknown_value_is_an_error_not_a_guess(self):
        rows = graded(self.sheet())
        rows[0]["accurate"] = "maybe"
        code, _ = self.score(rows)
        self.assertEqual(code, 2)

    def test_judge_labels_for_calibration(self):
        rows = graded(self.sheet())
        rows[0]["accurate"] = "n"
        labels = self.dir / "labels.jsonl"
        self.score(rows, "--judge-labels", str(labels))
        got = [json.loads(line) for line in labels.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(got), 36)
        self.assertIn({"id": rows[0]["id"], "human_faithful": 1, "human_correct": 0}, got)

    def test_wilson_interval(self):
        lo, hi = review.wilson(45, 50)
        self.assertAlmostEqual(lo, 0.786, places=2)
        self.assertAlmostEqual(hi, 0.957, places=2)


if __name__ == "__main__":
    unittest.main()
