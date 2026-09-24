#!/usr/bin/env python
"""Phase 3a: measure RETRIEVAL. Cheap, deterministic, no LLM needed — run it constantly.

  python scripts/eval_retrieval.py --label baseline-bge-m3
  python scripts/eval_retrieval.py --label k20 -k 20
  python scripts/eval_retrieval.py --label hashing --embedder hashing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_corpus_keys, load_eval, validate  # noqa: E402
from evalkit.runner import print_summary, run_retrieval, save, summarize  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.llm import get_llm  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=10)
    add_retrieval_args(ap)
    ap.add_argument("--provider", help="LLM for --multi-query / --hyde only")
    ap.add_argument("--label", required=True, help="name for this run (becomes results/<label>.json)")
    ap.add_argument("--results", default="results")
    ap.add_argument("--skip-validate", action="store_true")
    args = ap.parse_args()

    items = load_eval(args.eval)
    if not args.skip_validate:
        keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
        problems = validate(items, keys)
        if problems:
            print(f"{len(problems)} problems in {args.eval}:")
            for p in problems[:20]:
                print(f"  - {p}")
            sys.exit("fix the evaluation set first — bad labels make every number meaningless")

    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)
    llm = get_llm(args.provider) if (args.multi_query or args.hyde) else None
    retriever = build_pipeline(args, args.index, embedder, llm=llm)

    run = run_retrieval(items, retriever, k=args.k)
    config = {"k": args.k, "index": args.index, "eval": args.eval,
              **retriever.config.to_dict()}
    summary = summarize(args.label, config, items, run)
    print_summary(summary)
    path = save(summary, run, args.results, args.label)
    print(f"\nsaved {path}")

    worst = [r for r in run["records"] if r.get("metrics", {}).get("recall@5") == 0][:10]
    if worst:
        print(f"\n{len(worst)} shown of the questions that found nothing in the top 5 "
              f"— read these, they are where the next improvement is:")
        for r in worst:
            print(f"  [{r['id']}] {r['question'][:70]}")
            print(f"      gold {r['gold']} | got {r['retrieved'][:5]}")


if __name__ == "__main__":
    main()
