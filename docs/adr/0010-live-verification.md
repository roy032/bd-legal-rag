# ADR 0010 — Optional live check of cited sections

**Status:** accepted · **Date:** 2026-09

## Context
The index is a snapshot; the law changes. A user reading an answer should know
whether the cited section still says what the snapshot says, without the
service depending on a slow government website for every request.

## Decision
`src/rag/verify.py` re-fetches the official page of each cited section, parses
it with the ingest parser, normalises both texts and reports `current`,
`changed` or `unavailable`. It runs in parallel with a total timeout and is
**off by default** (`BDRAG_VERIFY_LIVE=1` turns it on); the web UI shows a
badge per citation.

## Consequences
- Staleness becomes visible per answer instead of silent.
- With it on, latency includes the site's response time up to the timeout; with
  it off, the service never touches the site at query time.
- A `changed` result says "re-index", not what changed; `ingest.py --update`
  is how the snapshot is refreshed.
