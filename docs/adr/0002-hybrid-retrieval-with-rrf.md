# ADR 0002 — Hybrid retrieval fused with reciprocal rank

**Status:** accepted · **Date:** 2026-09

## Context
Dense embeddings handle paraphrase; they are unreliable on exact tokens like
"ধারা ৩০২", "304A" or a defined term quoted verbatim — which is a large share of
real legal questions. BM25 is the opposite.

## Decision
Run both, fuse with reciprocal rank fusion (`Σ w/(rrf_k + rank)`) rather than
normalising scores. Weights are per query type (ADR 0004) and tuned on a
held-out split.

## Consequences
- Scores from incomparable scales never have to be made comparable.
- Two indexes to build and keep in sync; `build_index.py --bm25` does both.
- rrf_k becomes a knob: small favours top rank, large favours agreement.

## Alternatives
Score normalisation (fragile to outliers); dense only (fails exact lookups);
BM25 only (fails paraphrase, and Bangla morphology makes it worse).
