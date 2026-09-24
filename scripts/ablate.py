#!/usr/bin/env python
"""Phase 4: run the standard sweep and print the ablation table in one command.

Each configuration is evaluated on the SAME questions with the same index, so
the comparison is paired and the verdicts mean something.

  python scripts/ablate.py --eval data/eval/eval.jsonl        # full sweep (needs a reranker model)
  python scripts/ablate.py --rerank-kind lexical              # no model download
  python scripts/ablate.py --only dense hybrid                # just these rows
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_corpus_keys, load_eval, validate  # noqa: E402
from evalkit.report import markdown_table, paired_report  # noqa: E402
from evalkit.runner import print_summary, run_retrieval, save, summarize  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.pipeline import build_pipeline  # noqa: E402

# label -> overrides. Ordered so each row adds exactly one thing to the row above.
SWEEP: dict[str, dict] = {
    "bm25":            {"mode": "bm25"},
    "dense":           {"mode": "dense"},
    "hybrid":          {"mode": "hybrid"},
    "hybrid+refs":     {"mode": "hybrid", "expand_refs": True},
    "hybrid+refs+dedupe": {"mode": "hybrid", "expand_refs": True, "max_parts_per_section": 2},
    "hybrid+refs+rerank": {"mode": "hybrid", "expand_refs": True, "rerank": "cross"},
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["st", "hashing"], default="st")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--rerank-kind", choices=["cross", "lexical"], default="cross",
                    help="'lexical' runs with no model download (weaker, but free)")
    ap.add_argument("--rerank-model", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--only", nargs="*", help="subset of sweep labels to run")
    ap.add_argument("--baseline", default="dense")
    ap.add_argument("--results", default="results")
    ap.add_argument("--prefix", default="", help="prefix for result labels, e.g. 'v2-'")
    ap.add_argument("--out", help="write the markdown table here (e.g. results/ablation.md)")
    args = ap.parse_args()

    items = load_eval(args.eval)
    keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
    problems = validate(items, keys)
    if problems:
        for p in problems[:20]:
            print(f"  - {p}")
        sys.exit("fix the evaluation set first")

    embedder = get_embedder(args.embedder, model=args.model)   # loaded once, reused by every row
    sweep = {k: v for k, v in SWEEP.items() if not args.only or k in args.only}
    if not sweep:
        sys.exit(f"--only matched nothing; available: {', '.join(SWEEP)}")

    runs = []
    for label, overrides in sweep.items():
        cfg = argparse.Namespace(
            mode="dense", dense_weight=1.0, bm25_weight=1.0, rrf_k=60, candidates=50,
            rerank="none", rerank_model=args.rerank_model, expand_refs=False,
            multi_query=0, hyde=False, max_parts_per_section=None, include_repealed=False,
        )
        for key, value in overrides.items():
            setattr(cfg, key, args.rerank_kind if key == "rerank" and value == "cross" else value)
        full_label = f"{args.prefix}{label}"
        print(f"\n### {full_label}: {overrides}")
        try:
            pipeline = build_pipeline(cfg, args.index, embedder)
        except SystemExit as e:
            print(f"  skipped — {e}")
            continue
        run = run_retrieval(items, pipeline, k=args.k)
        summary = summarize(full_label, {"k": args.k, **pipeline.config.to_dict()}, items, run)
        print_summary(summary)
        save(summary, run, args.results, full_label)
        runs.append({**summary, "per_query": run["per_query"]})

    print("\n\n## Ablation table\n")
    table = markdown_table(runs)
    print(table)
    print()
    print(paired_report(runs, f"{args.prefix}{args.baseline}"))
    if args.out:
        Path(args.out).write_text(
            table + "\n\n```\n" + paired_report(runs, f"{args.prefix}{args.baseline}") + "\n```\n",
            encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
