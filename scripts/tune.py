#!/usr/bin/env python
"""Grid-search the retrieval knobs on a TUNING split — never on the reported set.

Fusion weights and rrf_k were set by hand in Phase 4 and never searched. This
does the search, and it enforces the discipline that makes the result honest:
it refuses to run on a file whose name suggests it is your reported evaluation
set unless you pass --i-know-this-is-my-test-set.

  python scripts/tune.py --eval data/eval/tune.jsonl --index data/index --mode hybrid
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_eval  # noqa: E402
from evalkit.metrics import aggregate  # noqa: E402
from evalkit.runner import run_retrieval  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.pipeline import RetrievalConfig, SearchPipeline, build_pipeline  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/tune.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--mode", default="hybrid", choices=["dense", "bm25", "hybrid"])
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--metric", default="recall@5")
    ap.add_argument("--dense-weights", type=float, nargs="+", default=[0.5, 1.0, 1.5])
    ap.add_argument("--bm25-weights", type=float, nargs="+", default=[0.5, 1.0, 1.5])
    ap.add_argument("--rrf-ks", type=int, nargs="+", default=[10, 60, 120])
    ap.add_argument("--candidates", type=int, nargs="+", default=[50])
    ap.add_argument("--out", default="results/tuning.json")
    ap.add_argument("--i-know-this-is-my-test-set", action="store_true")
    args = ap.parse_args()

    name = Path(args.eval).name.lower()
    if "tune" not in name and "dev" not in name and not args.i_know_this_is_my_test_set:
        sys.exit(f"'{args.eval}' does not look like a tuning split. Tuning on the set you report "
                 f"is fitting your own exam — split off ~30 questions as data/eval/tune.jsonl, "
                 f"or pass --i-know-this-is-my-test-set if you really mean it.")

    items = load_eval(args.eval)
    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)
    base = build_pipeline(RetrievalConfig(mode=args.mode, expand_refs=True, synonyms=True,
                                          route=False),
                          args.index, embedder)

    grid = list(itertools.product(args.dense_weights, args.bm25_weights, args.rrf_ks,
                                  args.candidates))
    print(f"{len(grid)} configurations over {len(items)} tuning questions\n")
    rows = []
    for dw, bw, rrf, cand in grid:
        cfg = replace(base.config, dense_weight=dw, bm25_weight=bw, rrf_k=rrf, candidates=cand)
        pipeline = SearchPipeline(cfg, dense=base.dense, bm25=base.bm25,
                                  reranker=base.reranker, llm=base.llm, parents=base.parents)
        run = run_retrieval(items, pipeline, k=max(args.k, 10))
        stats = aggregate([{k2: v for k2, v in q.items() if k2 not in ("id", "language", "type")}
                           for q in run["per_query"]])
        score = stats.get(args.metric, {}).get("mean", 0.0)
        rows.append({"dense_weight": dw, "bm25_weight": bw, "rrf_k": rrf, "candidates": cand,
                     args.metric: round(score, 4)})
        print(f"  dense={dw:<4} bm25={bw:<4} rrf_k={rrf:<4} cand={cand:<4} "
              f"{args.metric}={score:.3f}")

    rows.sort(key=lambda r: -r[args.metric])
    best = rows[0]
    print(f"\nbest: {json.dumps(best, ensure_ascii=False)}")
    print("Now re-run the ablation on your reported set with these values — and say in the "
          "README that they were tuned on a separate split.")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"metric": args.metric, "grid": rows},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
