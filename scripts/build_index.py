#!/usr/bin/env python
"""Phase 2a: chunks.jsonl -> vector index.

  python scripts/build_index.py                          # bge-m3 + numpy index
  python scripts/build_index.py --embedder hashing       # offline, no model download
  python scripts/build_index.py --backend qdrant         # needs a running Qdrant
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from rag import jsonio  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.lexical import BM25Index  # noqa: E402
from rag.store import NumpyStore, QdrantStore  # noqa: E402


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def embed_with_reuse(chunks: list[dict], embedder, out: Path, checkpoint_every: int = 2000) -> np.ndarray:
    """Embed only what has not been embedded before.

    Vectors are reused, by hash of the embedded text, from (a) the index already
    in `out` if it was built with the same embedder, and (b) a checkpoint left
    by an interrupted run. So re-running after `ingest.py --update`, or after a
    crash three hours into a CPU run, only pays for the new chunks.
    """
    known: dict[str, np.ndarray] = {}
    info = out / "index.json"
    if info.exists() and json.loads(info.read_text(encoding="utf-8")).get("embedder") == embedder.name:
        try:
            old = NumpyStore.load(out)
            known.update({_key(r["text"]): v for r, v in zip(old.records, old.vectors, strict=True)})
        except Exception as e:                      # a broken old index is just not reused
            print(f"  (previous index not reusable: {e})")
    ckpt_v, ckpt_k = out / "embed_checkpoint.npy", out / "embed_checkpoint.json"
    if ckpt_v.exists() and ckpt_k.exists():
        meta = json.loads(ckpt_k.read_text(encoding="utf-8"))
        if meta.get("embedder") == embedder.name:
            known.update(zip(meta["keys"], np.load(ckpt_v).astype(np.float32), strict=True))

    keys = [_key(c["text"]) for c in chunks]
    todo = sorted({k: i for i, k in enumerate(keys) if k not in known}.values())
    print(f"  reusing {len(chunks) - len(todo)} vectors, embedding {len(todo)} new chunk(s)")
    out.mkdir(parents=True, exist_ok=True)
    fresh_keys: list[str] = []
    fresh_vecs: list[np.ndarray] = []
    for start in range(0, len(todo), max(checkpoint_every, 1)):
        batch = todo[start:start + checkpoint_every]
        vecs = embedder.encode_passages([chunks[i]["text"] for i in batch])
        for i, v in zip(batch, vecs, strict=True):
            known[keys[i]] = v
            fresh_keys.append(keys[i])
            fresh_vecs.append(v)
        np.save(ckpt_v, np.asarray(fresh_vecs, dtype=np.float16))
        ckpt_k.write_text(json.dumps({"embedder": embedder.name, "keys": fresh_keys}), encoding="utf-8")
        print(f"  {min(start + checkpoint_every, len(todo))}/{len(todo)} embedded", flush=True)
    vectors = np.asarray([known[k] for k in keys], dtype=np.float32)
    for p in (ckpt_v, ckpt_k):
        if p.exists():
            p.unlink()
    return vectors


def load_chunks(path: Path) -> list[dict]:
    return jsonio.read_jsonl(path)


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
    ap.add_argument("--checkpoint-every", type=int, default=2000,
                    help="save embedding progress every N new chunks (a crash resumes from there)")
    ap.add_argument("--quantize", action="store_true",
                    help="store int8 vectors (4x smaller, rescored exactly — measure the recall cost)")
    args = ap.parse_args()

    chunks = load_chunks(Path(args.chunks))
    print(f"{len(chunks)} chunks from {args.chunks}")

    if args.bm25 or args.bm25_only:
        t0 = time.perf_counter()
        bm25 = BM25Index(stem=args.bm25_stem)
        bm25.add(chunks)
        # The dense index writes the same records; keep one copy on disk.
        bm25.save(args.out, write_records=args.bm25_only or args.backend != "numpy")
        print(f"BM25: {len(bm25)} docs, {len(bm25.postings)} terms, "
              f"avg length {bm25.avgdl:.0f} tokens, stem={args.bm25_stem} "
              f"({time.perf_counter() - t0:.1f}s) -> {args.out}")
        if args.bm25_only:
            return

    kw = {"batch_size": args.batch_size} if args.embedder == "st" else {}
    embedder = get_embedder(args.embedder, model=args.model, **kw)
    print(f"embedder: {embedder.name} (dim {embedder.dim})")

    t0 = time.perf_counter()
    vectors = embed_with_reuse(chunks, embedder, Path(args.out), args.checkpoint_every)
    took = time.perf_counter() - t0
    print(f"embedded in {took:.1f}s")

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
