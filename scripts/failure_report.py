#!/usr/bin/env python
"""Turn a run's failures into a plan: which stage is losing you the most?

  python scripts/failure_report.py --eval data/eval/eval.jsonl --index data/index \
         --answers results/agent.answers.json        # optional, adds citation/answer stages

Without an answers file it diagnoses retrieval only (candidates vs top-k), which
is free. With one, it also separates "the model was given the right section and
cited something else" from "retrieval never found it" — two problems people
routinely confuse.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_corpus_keys, load_eval, section_key  # noqa: E402
from evalkit.diagnose import diagnose  # noqa: E402
from rag.embed import embedder_for  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--pool", type=int, default=50, help="candidate pool size for the retrieval stage")
    ap.add_argument("--answers", help="an eval_e2e .answers.json file")
    ap.add_argument("--out", help="write the report as JSON")
    add_retrieval_args(ap)
    args = ap.parse_args()

    items = load_eval(args.eval)
    corpus_keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
    embedder = embedder_for(getattr(args, "mode", "dense"), args.embedder, args.model, args.index)
    pipeline = build_pipeline(args, args.index, embedder)

    answers = {}
    if args.answers:
        for row in json.loads(Path(args.answers).read_text(encoding="utf-8")):
            answers[row["id"]] = row

    per_question = {}
    for it in items:
        if not it.answerable:
            continue
        pool = pipeline.search(it.question, k=args.pool)
        top = pool[: args.k]
        row = answers.get(it.id, {})
        per_question[it.id] = {
            "candidates": [section_key(h.metadata) for h in pool],
            "top_k": [section_key(h.metadata) for h in top],
            "cited": [f"{s['chunk_id'].split('-')[0]}:{s['chunk_id'].split('-')[1]}"
                      for s in row.get("sources", [])] if row else None,
            "answer_correct": None if not row else not row.get("refused"),
        }

    report = diagnose(items, per_question, corpus_keys)
    print(json.dumps({k: v for k, v in report.items() if k != "failures"},
                     ensure_ascii=False, indent=2))
    print("\nFailures (read these):")
    for row in report["failures"][:25]:
        print(f"  [{row['stage']:<15}] {row['id']} {row['question'][:70]}")
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
