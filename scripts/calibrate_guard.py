#!/usr/bin/env python
"""Pick the abstention threshold from data instead of by feel.

`--min-score` decides when the system refuses before even calling the model.
Set it too low and it answers from noise; too high and it refuses questions it
could answer. The right value depends on the pipeline: cosine scores sit near
0.5, BM25 in the tens, fused RRF scores near 0.03 — a number copied from a blog
post is meaningless here.

This sweeps thresholds over your evaluation set and reports, for each one:

  answer_rate   share of answerable questions it would still attempt
  gold_kept     share of answerable questions that keep a gold section in top-k
  correct_abstain  share of unanswerable questions it would refuse outright
  score         gold_kept and correct_abstain averaged — a starting point, not gospel

No LLM calls: this only looks at retrieval scores.

  python scripts/calibrate_guard.py --mode hybrid --expand-refs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_eval, section_key  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["st", "hashing"], default="st")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--steps", type=int, default=12)
    add_retrieval_args(ap)
    args = ap.parse_args()

    items = load_eval(args.eval)
    embedder = get_embedder(args.embedder, model=args.model)
    pipeline = build_pipeline(args, args.index, embedder)

    rows = []
    for it in items:
        hits = pipeline.search(it.question, k=args.k)
        rows.append({
            "answerable": it.answerable,
            "top": hits[0].score if hits else 0.0,
            "gold_in_top": bool(set(it.gold) & {section_key(h.metadata) for h in hits}),
        })

    tops = sorted(r["top"] for r in rows)
    if not tops:
        sys.exit("no questions")
    lo, hi = tops[0], tops[-1]
    thresholds = [lo + (hi - lo) * i / max(args.steps - 1, 1) for i in range(args.steps)]

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    print(f"{len(answerable)} answerable, {len(unanswerable)} unanswerable · "
          f"top-1 score range {lo:.4f} … {hi:.4f}\n")
    print(f"{'min_score':>10} {'answer_rate':>12} {'gold_kept':>10} {'correct_abstain':>16} {'score':>7}")
    best = None
    for t in thresholds:
        attempted = [r for r in answerable if r["top"] >= t]
        answer_rate = len(attempted) / len(answerable) if answerable else 0.0
        gold_kept = (sum(r["gold_in_top"] for r in attempted) / len(answerable)) if answerable else 0.0
        abstain = (sum(r["top"] < t for r in unanswerable) / len(unanswerable)) if unanswerable else float("nan")
        combined = (gold_kept + (abstain if abstain == abstain else gold_kept)) / 2
        print(f"{t:10.4f} {answer_rate:12.2f} {gold_kept:10.2f} {abstain:16.2f} {combined:7.3f}")
        if best is None or combined > best[1]:
            best = (t, combined)
    print(f"\nbest by this crude score: --min-score {best[0]:.4f}")
    print("Check it against the questions it would newly refuse before you ship it — "
          "refusing a question you could answer is a real cost, not a free safety win.")
    if not unanswerable:
        print("WARNING: no unanswerable questions in this set, so 'correct_abstain' is blind. "
              "Add some — they are how you measure hallucination.")


if __name__ == "__main__":
    main()
