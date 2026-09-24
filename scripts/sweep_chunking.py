#!/usr/bin/env python
"""Does chunk size matter? You built the knob in Phase 1 and never measured it.

Re-chunks the corpus at several sizes, rebuilds an index for each, and evaluates
the same questions against all of them. Gold labels are section-level, so they
survive re-chunking — which is exactly why they were defined that way.

  python scripts/sweep_chunking.py --sizes 800 1200 1800 2500 --embedder hashing
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_eval  # noqa: E402
from evalkit.metrics import aggregate  # noqa: E402
from evalkit.runner import run_retrieval  # noqa: E402
from ingest.chunk import act_overview_chunk, chunk_section  # noqa: E402
from ingest.models import Act, Section, SectionRef  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.lexical import BM25Index  # noqa: E402
from rag.pipeline import RetrievalConfig, build_pipeline  # noqa: E402
from rag.store import NumpyStore  # noqa: E402


def rechunk(acts_path: Path, sections_path: Path, max_chars: int) -> list[dict]:
    acts = {}
    for line in acts_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            d["sections"] = [SectionRef(**s) for s in d.get("sections", [])]
            acts[d["act_id"]] = Act(**d)
    chunks = [act_overview_chunk(a) for a in acts.values()]
    for line in sections_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sec = Section(**json.loads(line))
        act = acts.get(sec.act_id)
        if act:
            chunks += chunk_section(act, sec, max_chars=max_chars)
    return [c.to_dict() for c in chunks]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processed", default="data/processed", help="directory with acts/sections jsonl")
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--sizes", type=int, nargs="+", default=[800, 1200, 1800, 2500])
    ap.add_argument("--embedder", choices=["st", "hashing"], default="st")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--mode", default="hybrid")
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--metric", default="recall@5")
    args = ap.parse_args()

    processed = Path(args.processed)
    items = load_eval(args.eval)
    embedder = get_embedder(args.embedder, model=args.model)
    print(f"{len(items)} questions · embedder {embedder.name}\n")
    print(f"{'max_chars':>10} {'chunks':>8} {'median len':>11} {args.metric:>12}")

    for size in args.sizes:
        chunks = rechunk(processed / "acts.jsonl", processed / "sections.jsonl", size)
        tmp = Path(tempfile.mkdtemp(prefix=f"chunks{size}-"))
        try:
            store = NumpyStore(embedder.dim, embedder.name)
            store.add(embedder.encode_passages([c["text"] for c in chunks]), chunks)
            store.save(tmp)
            bm25 = BM25Index()
            bm25.add(chunks)
            bm25.save(tmp)
            pipeline = build_pipeline(RetrievalConfig(mode=args.mode, expand_refs=True),
                                      tmp, embedder, records=chunks)
            run = run_retrieval(items, pipeline, k=args.k)
            stats = aggregate([{k2: v for k2, v in q.items()
                                if k2 not in ("id", "language", "type")} for q in run["per_query"]])
            lengths = sorted(c["metadata"]["char_len"] for c in chunks)
            print(f"{size:>10} {len(chunks):>8} {lengths[len(lengths)//2]:>11} "
                  f"{stats.get(args.metric, {}).get('mean', 0):>12.3f}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print("\nSmaller chunks usually raise precision and lower recall of long provisions; "
          "the point is to know which way it goes on YOUR corpus.")


if __name__ == "__main__":
    main()
