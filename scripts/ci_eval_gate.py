#!/usr/bin/env python
"""Fail the build when retrieval gets worse.

Tests tell you the code still runs. This tells you the system still works.
A pull request that drops recall@5 below the committed baseline exits non-zero,
so quality regressions are caught the same way syntax errors are.

  python scripts/ci_eval_gate.py --baseline results/baseline.json --tolerance 0.03

Create the baseline once from a run you trust:
  python scripts/eval_retrieval.py --label baseline && cp results/baseline.json results/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_corpus_keys, load_eval, validate  # noqa: E402
from evalkit.metrics import paired_bootstrap  # noqa: E402
from evalkit.runner import run_retrieval, summarize  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["st", "hashing"], default="st")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--metric", default="recall@5")
    ap.add_argument("--baseline", default="results/baseline.json")
    ap.add_argument("--tolerance", type=float, default=0.03,
                    help="how far below the baseline is still acceptable (noise band)")
    ap.add_argument("--min", type=float, help="absolute floor, used when there is no baseline")
    add_retrieval_args(ap)
    args = ap.parse_args()

    items = load_eval(args.eval)
    keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
    problems = validate(items, keys)
    if problems:
        print("\n".join(f"  - {p}" for p in problems[:20]))
        sys.exit("evaluation set is invalid")

    embedder = get_embedder(args.embedder, model=args.model)
    pipeline = build_pipeline(args, args.index, embedder)
    run = run_retrieval(items, pipeline, k=args.k)
    summary = summarize("ci", {"k": args.k, **pipeline.config.to_dict()}, items, run)
    current = summary["overall"].get(args.metric, {}).get("mean")
    if current is None:
        sys.exit(f"{args.metric} not produced (k too small?)")
    print(f"{args.metric}: {current:.3f} over {summary['dataset']['answerable']} answerable questions")

    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        if args.min is None:
            print(f"no baseline at {baseline_path} and no --min given; nothing to compare against")
            return
        print(f"floor: {args.min:.3f}")
        sys.exit(0 if current >= args.min else f"FAIL: {current:.3f} < floor {args.min:.3f}")

    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    before = base["overall"][args.metric]["mean"]
    delta = current - before
    print(f"baseline '{base.get('label')}': {before:.3f}  ->  {delta:+.3f}")

    bscores = {q["id"]: q.get(args.metric) for q in base.get("per_query", [])}
    cscores = {q["id"]: q.get(args.metric) for q in run["per_query"]}
    shared = [i for i in bscores if bscores[i] is not None and cscores.get(i) is not None]
    if shared:
        paired = paired_bootstrap([bscores[i] for i in shared], [cscores[i] for i in shared])
        verdict = ("better" if paired["lo"] > 0 else "worse" if paired["hi"] < 0 else "within noise")
        print(f"paired: {paired['diff']:+.3f} [{paired['lo']:+.3f}, {paired['hi']:+.3f}] {verdict}")

    if delta < -abs(args.tolerance):
        sys.exit(f"FAIL: {args.metric} dropped {delta:+.3f}, more than the {args.tolerance} tolerance")
    print("OK")


if __name__ == "__main__":
    main()
