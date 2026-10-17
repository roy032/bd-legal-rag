#!/usr/bin/env python
"""How much do you trust the LLM judge? Measure it.

Faithfulness and correctness in Phase 3 come from a model. If you have never
checked that model against your own judgement, the number is decoration. This
script samples answers, asks you to grade them yourself, then reports agreement
and Cohen's kappa against the judge.

  python scripts/eval_e2e.py --label run1 --judge-provider groq   # run1.answers.json
  python scripts/calibrate_judge.py results/run1.answers.json --sample 20   # grade here
  python scripts/calibrate_judge.py results/run1.answers.json --report      # agreement

Or grade in a spreadsheet: --export writes a CSV with the question, the answer and
the cited excerpts; fill the human_faithful and human_correct columns with 1 or 0
(blank = skip) and read it back with --import.

  python scripts/calibrate_judge.py results/run1.answers.json --export grade.csv --sample 40
  python scripts/calibrate_judge.py results/run1.answers.json --import grade.csv --report

Kappa below ~0.4 means the judge is measuring something other than what you
mean by "faithful"; fix the judge prompt before trusting any faithfulness number.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

COLUMNS = ["id", "question", "answer", "cited_excerpts", "human_faithful", "human_correct"]


def kappa(a: list[int], b: list[int]) -> float:
    """Cohen's kappa: agreement above what chance would give."""
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b, strict=False)) / n
    labels = set(a) | set(b)
    expected = sum((a.count(lbl) / n) * (b.count(lbl) / n) for lbl in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def excerpts(row: dict, max_chars: int = 700) -> str:
    return "\n\n".join(f"[{s.get('n')}] {s.get('citation')}\n{(s.get('text') or '')[:max_chars]}"
                       for s in row.get("sources", []))


def judge_verdicts(row: dict) -> dict:
    """The judge's 0/1 verdicts for one answer; correctness counts as 1 at 0.5 or above."""
    judged = row.get("judge") or {}
    out = {}
    if judged.get("faithfulness") is not None:
        out["faithful"] = int(float(judged["faithfulness"]) >= 0.5)
    if judged.get("correctness") is not None:
        out["correct"] = int(float(judged["correctness"]) >= 0.5)
    return out


def read_csv_labels(path: Path) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            row: dict = {"id": r["id"]}
            for col in ("human_faithful", "human_correct"):
                v = (r.get(col) or "").strip().lower()
                if v in ("1", "0", "y", "n", "yes", "no"):
                    row[col] = int(v in ("1", "y", "yes"))
            if len(row) > 1:
                labels[row["id"]] = row
    return labels


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answers", help="an eval_e2e .answers.json file")
    ap.add_argument("--labels", default="data/eval/judge_labels.jsonl")
    ap.add_argument("--sample", type=int, help="grade N answers now (or export N with --export)")
    ap.add_argument("--export", help="write a CSV to grade in a spreadsheet instead")
    ap.add_argument("--import", dest="import_csv", help="read labels from a graded CSV")
    ap.add_argument("--report", action="store_true", help="compare your labels with the judge")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = json.loads(Path(args.answers).read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in rows}
    labels_path = Path(args.labels)
    labels = {}
    if labels_path.exists():
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                labels[row["id"]] = row

    if args.import_csv:
        labels.update(read_csv_labels(Path(args.import_csv)))

    if args.export:
        todo = [r for r in rows if r["id"] not in labels and not r.get("refused")]
        random.Random(args.seed).shuffle(todo)
        with open(args.export, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            for row in todo[: args.sample or 40]:
                w.writerow({"id": row["id"], "question": row["question"], "answer": row["answer"],
                            "cited_excerpts": excerpts(row), "human_faithful": "",
                            "human_correct": ""})
        print(f"wrote {min(len(todo), args.sample or 40)} answers to {args.export}: fill "
              "human_faithful (every claim backed by the excerpts?) and human_correct "
              "(right answer to the question?) with 1 or 0")
        return

    if args.sample:
        todo = [r for r in rows if r["id"] not in labels]
        random.Random(args.seed).shuffle(todo)
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        with open(labels_path, "a", encoding="utf-8") as f:
            for row in todo[: args.sample]:
                print("\n" + "=" * 78)
                print(f"Q: {row['question']}\n")
                print(f"A: {row['answer'][:1200]}\n")
                print(f"cited excerpts:\n{excerpts(row) or '(none)'}\n")
                verdict = input("faithful to the cited text? [y/n/skip] ").strip().lower()
                if verdict.startswith("s"):
                    continue
                correct = input("correct answer to the question? [y/n/skip] ").strip().lower()
                label = {"id": row["id"], "human_faithful": int(verdict.startswith("y"))}
                if correct[:1] in ("y", "n"):
                    label["human_correct"] = int(correct.startswith("y"))
                f.write(json.dumps(label, ensure_ascii=False) + "\n")
        print(f"\nsaved to {labels_path}")
        return

    if not args.report:
        ap.error("pass --sample N to grade, or --report to compare")

    if not any(judge_verdicts(r) for r in rows):
        sys.exit("this answers file has no judge verdicts: re-run eval_e2e with a judge "
                 "(answers files written before the verdicts were saved cannot be compared)")
    reported = False
    for key, name in (("faithful", "faithfulness"), ("correct", "correctness")):
        pairs = [(i, labels[i][f"human_{key}"], judge_verdicts(by_id[i])[key]) for i in labels
                 if i in by_id and f"human_{key}" in labels[i] and key in judge_verdicts(by_id[i])]
        if not pairs:
            continue
        reported = True
        human = [h for _, h, _ in pairs]
        judge = [j for _, _, j in pairs]
        agree = sum(h == j for h, j in zip(human, judge, strict=True)) / len(human)
        print(f"\n{name}: {len(human)} graded answers")
        print(f"  raw agreement: {agree:.2f}")
        print(f"  Cohen's kappa: {kappa(human, judge):.2f}")
        disagreements = [i for i, h, j in pairs if h != j]
        if disagreements:
            print(f"  disagreements: {disagreements[:10]}")
    if not reported:
        sys.exit("no overlap between your labels and this answers file")
    print("\nkappa < 0.4: the judge is not measuring what you mean — rewrite its prompt "
          "or use a stronger judge (e.g. --judge-provider groq).")


if __name__ == "__main__":
    main()
