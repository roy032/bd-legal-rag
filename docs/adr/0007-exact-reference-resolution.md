# ADR 0007 — Resolve "section N of Act X" exactly before searching

**Status:** accepted · **Date:** 2026-09

## Context
A large share of real questions name the law: "ধারা ৩০২ দণ্ডবিধি", "section 154
CrPC", "article 27". Dense and BM25 retrieval both treat the number as one weak
token among many, so "section 302" regularly returned sections 300, 304 or 302
of a different act. Act names also come in many forms: official titles, short
titles ("Penal Code"), Bangla names (দণ্ডবিধি) and abbreviations (CrPC).

## Decision
`src/rag/refs.py` parses section/article references from the query
(`query.SECTION_REF`) and resolves the act with `ActResolver`: title stems from
the corpus plus a small hand-kept alias table (`ACT_ALIASES`). When several acts
share a stem, the in-force and most recent one wins. A resolved reference adds
the exact section's chunks at the top of the candidate list, and an
act-filtered search runs alongside the normal hybrid search. With no resolvable
reference, retrieval is unchanged. It is on by default (`resolve_refs`) and is a
row of its own in the ablation (`+resolve`).

## Consequences
- Exact-reference questions stop depending on embedding luck; the ablation row
  shows the gain on the `exact_ref` slice.
- The alias table is manual. A missing alias falls back to normal retrieval, so
  the failure mode is "no better than before", never a wrong forced answer.
- A wrong act match is possible when titles share words; preferring in-force,
  latest acts makes the common case right, and the answer still cites the act
  so the reader can see which one was used.
