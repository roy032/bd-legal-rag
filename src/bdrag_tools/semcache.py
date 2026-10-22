#!/usr/bin/env python
"""Tune and check the paraphrase cache threshold (service/semcache.py).

  bdrag semcache --embedder st --model BAAI/bge-m3      # no index needed
  bdrag semcache --index data/index                     # + the evidence gate

Pairs come from data/eval/paraphrases.jsonl (same: true = one answer serves both,
false = a near miss that must not merge) plus every pair of answerable eval
questions whose gold sections are disjoint. Each pair goes through the same gates
as the service (script, numbers, negation, topics, and with --index the dense
top-5 overlap). The recommended threshold is the highest similarity of a negative
that passes the gates, plus --margin, rounded up to 0.005.

Exits 1 when a negative merges at --threshold (default: the tuned value for the
embedder), so a new embedder or lexicon change cannot loosen it unnoticed.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

EVAL_SETS = ("data/eval/eval.jsonl", "data/eval/tune.jsonl", "data/eval/eval_gaps.jsonl",
             "data/eval/eval_scenarios.jsonl")


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def eval_negatives(paths: list[str]) -> list[dict]:
    """Pairs of answerable eval questions that share no gold section."""
    qs = [r for p in paths if Path(p).exists() for r in read_jsonl(p) if r.get("gold")]
    return [{"id": f"{a['id']}~{b['id']}", "a": a["question"], "b": b["question"], "same": False,
             "source": "eval"}
            for a, b in itertools.combinations(qs, 2) if not set(a["gold"]) & set(b["gold"])]


def recommend(neg_sims: list[float], margin: float) -> float:
    top = max(neg_sims, default=0.0) + margin
    return min(math.ceil(round(top / 0.005, 6)) * 0.005, 1.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", default="data/eval/paraphrases.jsonl")
    ap.add_argument("--eval", nargs="*", default=list(EVAL_SETS),
                    help="eval sets for automatic negatives; pass none to skip")
    ap.add_argument("--index", help="index dir: use its embedder and gate on evidence overlap")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--threshold", type=float, help="check this value (default: tuned for the embedder)")
    ap.add_argument("--min-overlap", type=float, default=None)
    ap.add_argument("--margin", type=float, default=0.005)
    ap.add_argument("--json-out")
    args = ap.parse_args(argv)

    import numpy as np

    from rag.embed import get_embedder
    from rag.topics import match_topics
    from service.semcache import DEFAULT_OVERLAP, TUNED, evidence, overlap, signature

    pairs = read_jsonl(args.pairs) + eval_negatives(args.eval or [])
    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)
    store = None
    if args.index:
        from rag.pipeline import open_store
        store = open_store(args.index)
    min_overlap = DEFAULT_OVERLAP if args.min_overlap is None else args.min_overlap

    texts = sorted({p[s] for p in pairs for s in ("a", "b")})
    vectors = dict(zip(texts, np.asarray(embedder.encode_queries(texts), dtype=np.float32), strict=True))
    sigs = {t: signature(t, "", [x.name for x in match_topics(t)]) for t in texts}
    evid = ({t: evidence(store.search(vectors[t], k=5)) for t in texts} if store is not None
            else {})

    rows = []
    for p in pairs:
        a, b = p["a"], p["b"]
        sim = float(np.dot(vectors[a], vectors[b]))
        gate = None
        if sigs[a] != sigs[b]:
            gate = next(name for name, x, y in zip(
                ("scope", "script", "numbers", "negation", "topics"), sigs[a], sigs[b], strict=True) if x != y)
        elif evid and overlap(evid[a], evid[b]) < min_overlap:
            gate = "evidence"
        rows.append({**p, "similarity": round(sim, 4), "blocked_by": gate})

    pos = [r for r in rows if r["same"]]
    neg = [r for r in rows if not r["same"]]
    neg_open = [r for r in neg if r["blocked_by"] is None]
    rec = recommend([r["similarity"] for r in neg_open], args.margin)
    threshold = args.threshold if args.threshold is not None else TUNED.get(embedder.name)

    def merged(rs, t):
        return [r for r in rs if r["blocked_by"] is None and r["similarity"] >= t]

    print(f"embedder {embedder.name}; {len(pos)} paraphrases, {len(neg)} negatives "
          f"({sum(r.get('source') == 'eval' for r in neg)} from eval sets)"
          + (f"; evidence gate on, overlap >= {min_overlap}" if evid else "; no evidence gate"))
    blocked: dict[str, int] = {}
    for r in neg:
        if r["blocked_by"]:
            blocked[r["blocked_by"]] = blocked.get(r["blocked_by"], 0) + 1
    print("negatives stopped by a gate: "
          + (", ".join(f"{k} {v}" for k, v in sorted(blocked.items())) or "none"))
    print("closest negatives past the gates:")
    for r in sorted(neg_open, key=lambda r: -r["similarity"])[:8]:
        print(f"  {r['similarity']:.3f}  {r['a'][:60]}  |  {r['b'][:60]}")
    print(f"\nrecommended threshold: {rec:.3f}  "
          f"(paraphrases merged: {len(merged(pos, rec))}/{len(pos)})")

    false_merges: list[dict] = []
    if threshold is not None:
        false_merges = merged(neg, threshold)
        print(f"at {threshold:.3f}: paraphrases merged {len(merged(pos, threshold))}/{len(pos)}, "
              f"false merges {len(false_merges)}")
        for r in false_merges:
            print(f"  FALSE MERGE {r['similarity']:.3f}  {r['a']}  |  {r['b']}")
        missed = [r for r in pos if r not in merged(pos, threshold)]
        for r in sorted(missed, key=lambda r: -r["similarity"])[:10]:
            why = r["blocked_by"] or "similarity"
            print(f"  missed ({why}) {r['similarity']:.3f}  {r['a'][:50]}  |  {r['b'][:50]}")
    else:
        print(f"no tuned threshold for {embedder.name}; pass --threshold to check one")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "embedder": embedder.name, "recommended": rec, "threshold": threshold,
            "evidence_gate": bool(evid), "min_overlap": min_overlap,
            "paraphrases": len(pos), "negatives": len(neg),
            "merged_at_threshold": len(merged(pos, threshold)) if threshold is not None else None,
            "false_merges": len(false_merges),
            "rows": [r for r in rows if r.get("source") != "eval" or r["blocked_by"] is None],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if false_merges else 0


if __name__ == "__main__":
    sys.exit(main())
