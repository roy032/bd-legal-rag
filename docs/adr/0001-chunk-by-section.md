# ADR 0001 — Chunk by legal section, not by token count

**Status:** accepted · **Date:** 2026-09

## Context
Retrieval needs units. The default in most RAG tutorials is a fixed window of
500–1000 tokens with overlap, chosen because it is easy, not because it fits the
data. Statutes are already divided into the units people cite: sections.

## Decision
One section = one chunk. Sections longer than `--max-chars` split at clause
boundaries (`(১)`, `(ক)`, `(a)`), and every later part repeats the section's
lead-in. Each chunk carries a context header (act > chapter > section).

## Consequences
- Citations are natural: "ধারা ৩০২" is a retrievable unit and a legally meaningful one.
- Evaluation labels are section-level and survive re-chunking (ADR 0003).
- Long definition sections still need splitting, which is why the lead-in is repeated.
- Schedules and forms are not sections, so they are currently out of scope.

## Alternatives
Fixed windows (simpler, cuts clauses in half); whole acts (too large); sentence
windows (loses the operative structure).
