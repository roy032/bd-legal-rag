#!/usr/bin/env python
"""How much do you trust the LLM judge? Measure it.

Faithfulness and correctness in Phase 3 come from a model. If you have never
checked that model against your own judgement, the number is decoration. This
script samples answers, asks you to grade them yourself, then reports agreement
and Cohen's kappa against the judge.

  python scripts/eval_e2e.py --label run1                 # produces run1.answers.json
  python scripts/calibrate_judge.py results/run1.answers.json --sample 20   # you grade
  python scripts/calibrate_judge.py results/run1.answers.json --report      # agreement

Kappa below ~0.4 means the judge is measuring something other than what you
mean by "faithful"; fix the judge prompt before trusting any faithfulness number.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def kappa(a: list[int], b: list[int]) -> float:
    """Cohen's kappa: agreement above what chance would give."""
    n = len(a)
    if n == 0:
        return float("nan")
    observed = sum(x == y for x, y in zip(a, b, strict=False)) / n
    labels = set(a) | set(b)
    expected = sum((a.count(lbl) / n) * (b.count(lbl) / n) for lbl in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("answers", help="an eval_e2e .answers.json file")
    ap.add_argument("--labels", default="data/eval/judge_labels.jsonl")
    ap.add_argument("--sample", type=int, help="grade N answers now")
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

    if args.sample:
        todo = [r for r in rows if r["id"] not in labels]
        random.Random(args.seed).shuffle(todo)
        labels_path.parent.mkdir(parents=True, exist_ok=True)
        with open(labels_path, "a", encoding="utf-8") as f:
            for row in todo[: args.sample]:
                print("\n" + "=" * 78)
                print(f"Q: {row['question']}\n")
                print(f"A: {row['answer'][:1200]}\n")
                print(f"sources: {[s['citation'] for s in row.get('sources', [])]}")
                verdict = input("faithful to the cited text? [y/n/skip] ").strip().lower()
                if verdict.startswith("s"):
                    continue
                f.write(json.dumps({"id": row["id"], "human_faithful": int(verdict.startswith("y"))},
                                   ensure_ascii=False) + "\n")
        print(f"\nsaved to {labels_path}")
        return

    if not args.report:
        ap.error("pass --sample N to grade, or --report to compare")

    shared = [i for i in labels if i in by_id and "judge" in by_id[i]]
    human, judge = [], []
    for i in shared:
        judged = by_id[i].get("judge", {})
        verdict = judged.get("_faithfulness_reason") is not None
        human.append(int(labels[i]["human_faithful"]))
        judge.append(int(bool(by_id[i].get("faithfulness", verdict))))
    if not shared:
        sys.exit("no overlap between your labels and this answers file "
                 "(did you run eval_e2e with a judge?)")
    agree = sum(h == j for h, j in zip(human, judge, strict=False)) / len(human)
    print(f"{len(human)} graded answers")
    print(f"raw agreement: {agree:.2f}")
    print(f"Cohen's kappa: {kappa(human, judge):.2f}")
    print("\nkappa < 0.4: the judge is not measuring what you mean — rewrite its prompt.")
    disagreements = [i for i, h, j in zip(shared, human, judge, strict=False) if h != j]
    if disagreements:
        print(f"disagreements: {disagreements[:10]}")


if __name__ == "__main__":
    main()
