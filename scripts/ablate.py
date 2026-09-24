#!/usr/bin/env python
"""Phase 4: run the standard sweep and print the ablation table in one command.

Each configuration is evaluated on the SAME questions with the same index, so
the comparison is paired and the verdicts mean something.

  python scripts/ablate.py --eval data/eval/eval.jsonl        # full sweep (needs a reranker model)
  python scripts/ablate.py --rerank-kind lexical              # no model download
  python scripts/ablate.py --only dense hybrid                # just these rows

Needs an index built with --bm25 (every row except "dense" uses it).
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
from rag.pipeline import RetrievalConfig, SearchPipeline, build_pipeline  # noqa: E402
from rag.refs import ActResolver  # noqa: E402
from rag.rerank import get_reranker  # noqa: E402

_RESOLVER: list[ActResolver] = []


def base_resolver(base: SearchPipeline, cfg: RetrievalConfig) -> ActResolver | None:
    if not cfg.resolve_refs:
        return None
    if not _RESOLVER:
        assert base.bm25 is not None
        _RESOLVER.append(ActResolver(base.bm25.records))
    return _RESOLVER[0]

# label -> overrides. Ordered so each row adds exactly one thing to the row above
# (the rerank row adds a cross-encoder on top of the full deterministic stack).
_H = {"mode": "hybrid"}
_R = {**_H, "expand_refs": True}
_D = {**_R, "max_parts_per_section": 2}
_S = {**_D, "synonyms": True, "transliterate": True}
_T = {**_S, "route": True}
_X = {**_T, "resolve_refs": True}
_F = {**_X, "boost_in_force": True}
SWEEP: dict[str, dict] = {
    "bm25":              {"mode": "bm25"},
    "dense":             {"mode": "dense"},
    "hybrid":            _H,
    "+refs":             _R,
    "+dedupe":           _D,
    "+synonyms":         _S,
    "+route":            _T,
    "+resolve":          _X,
    "+in-force":         _F,      # = the service's default pipeline
    "+rerank":           {**_F, "rerank": "cross"},
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--rerank-kind", choices=["cross", "lexical"], default="cross",
                    help="'lexical' runs with no model download (weaker, but free)")
    ap.add_argument("--rerank-model", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--only", nargs="*", help="subset of sweep labels to run")
    ap.add_argument("--baseline", default="dense", help="row the paired tests compare against")
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

    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)   # loaded once, reused by every row
    sweep = {k: v for k, v in SWEEP.items() if not args.only or k in args.only}
    if not sweep:
        sys.exit(f"--only matched nothing; available: {', '.join(SWEEP)}")

    # Load the indexes once; every row reuses them with its own RetrievalConfig.
    base = build_pipeline(RetrievalConfig(mode="hybrid"), args.index, embedder)
    rerankers: dict[str, object] = {}
    runs = []
    for label, overrides in sweep.items():
        overrides = {k: (args.rerank_kind if k == "rerank" else v) for k, v in overrides.items()}
        cfg = RetrievalConfig(rerank_model=args.rerank_model, embedder=embedder.name, **overrides)
        full_label = f"{args.prefix}{label}"
        print(f"\n### {full_label}: {overrides}")
        if cfg.rerank not in rerankers:
            try:
                rerankers[cfg.rerank] = get_reranker(cfg.rerank, model=cfg.rerank_model)
            except Exception as e:           # no model download possible here
                print(f"  skipped — reranker unavailable: {e}")
                continue
        pipeline = SearchPipeline(cfg, dense=base.dense if cfg.mode != "bm25" else None,
                                  bm25=base.bm25 if cfg.mode != "dense" else None,
                                  reranker=rerankers[cfg.rerank],
                                  resolver=base_resolver(base, cfg))
        run = run_retrieval(items, pipeline, k=args.k)
        summary = summarize(full_label, {"k": args.k, **pipeline.config.to_dict()}, items, run)
        print_summary(summary)
        save(summary, run, args.results, full_label)
        runs.append({**summary, "per_query": run["per_query"]})

    print("\n\n## Ablation table\n")
    table = markdown_table(runs, sort=False)
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
