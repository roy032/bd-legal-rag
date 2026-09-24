#!/usr/bin/env python
"""Phase 2a: chunks.jsonl -> vector index.

  python scripts/build_index.py                          # bge-m3 + numpy index
  python scripts/build_index.py --embedder hashing       # offline, no model download
  python scripts/build_index.py --backend qdrant         # needs a running Qdrant
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.embed import get_embedder  # noqa: E402
from rag.lexical import BM25Index  # noqa: E402
from rag.store import NumpyStore, QdrantStore  # noqa: E402


def load_chunks(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--out", default="data/index")
    ap.add_argument("--embedder", choices=["st", "hashing"], default="st")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--backend", choices=["numpy", "qdrant"], default="numpy")
    ap.add_argument("--collection", default="bdlaws")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--bm25", action="store_true", help="also build a BM25 index (needed for hybrid)")
    ap.add_argument("--bm25-stem", action="store_true", help="strip common Bangla suffixes")
    ap.add_argument("--bm25-only", action="store_true", help="skip embeddings entirely")
    ap.add_argument("--quantize", action="store_true",
                    help="store int8 vectors (4x smaller, rescored exactly — measure the recall cost)")
    args = ap.parse_args()

    chunks = load_chunks(Path(args.chunks))
    print(f"{len(chunks)} chunks from {args.chunks}")

    if args.bm25 or args.bm25_only:
        t0 = time.perf_counter()
        bm25 = BM25Index(stem=args.bm25_stem)
        bm25.add(chunks)
        bm25.save(args.out)
        print(f"BM25: {len(bm25)} docs, {len(bm25.postings)} terms, "
              f"avg length {bm25.avgdl:.0f} tokens, stem={args.bm25_stem} "
              f"({time.perf_counter() - t0:.1f}s) -> {args.out}")
        if args.bm25_only:
            return

    kw = {"batch_size": args.batch_size} if args.embedder == "st" else {}
    embedder = get_embedder(args.embedder, model=args.model, **kw)
    print(f"embedder: {embedder.name} (dim {embedder.dim})")

    t0 = time.perf_counter()
    vectors = embedder.encode_passages([c["text"] for c in chunks])
    took = time.perf_counter() - t0
    print(f"embedded in {took:.1f}s ({len(chunks) / max(took, 1e-9):.1f} chunks/s)")

    store = (NumpyStore(embedder.dim, embedder.name, quantize=args.quantize)
             if args.backend == "numpy"
             else QdrantStore(embedder.dim, args.collection, embedder_name=embedder.name, recreate=True))
    store.add(vectors, chunks)
    if args.backend == "numpy":
        store.save(args.out)
        print(f"saved {len(store)} vectors to {args.out}")
    else:
        print(f"upserted {len(store)} points into Qdrant collection '{args.collection}'")


if __name__ == "__main__":
    main()
