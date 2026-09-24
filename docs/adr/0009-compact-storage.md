# ADR 0009 — Compressed cache, float16 vectors, incremental rebuilds

**Status:** accepted · **Date:** 2026-09

## Context
The full corpus is tens of thousands of section pages. Stored as raw HTML plus
float32 bge-m3 vectors, the project needed several GB on a student laptop, and
re-embedding everything on CPU after each small parser change took hours.

## Decision
- The page cache is gzip-compressed (`.html.gz`); old plain `.html` files are
  still read, and `ingest.py --compact-cache` converts them.
- Vectors are stored as float16; chunk records and the BM25 index are
  gzipped JSON (`src/rag/jsonio.py` reads either form). BM25 shares the dense
  index's records instead of keeping a second copy.
- `build_index.py` reuses the embedding of any chunk whose text hash is
  unchanged, and checkpoints progress so an interrupted build resumes.
- `ingest.py --update` fetches only new acts and acts named by newly added
  amending acts, driven by a manifest of the previous run.

## Consequences
- Disk use drops to roughly a quarter; float16 changes cosine scores by less
  than 1e-3, which does not change rankings in the tests.
- Rebuilding after a parser fix only re-embeds chunks whose text changed.
- The update heuristic can miss an amendment that does not appear as a new act;
  a full offline re-parse of the cache is the fallback and costs no network.
