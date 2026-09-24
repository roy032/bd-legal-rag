# ADR 0003 — Evaluation labels point at sections, not chunks

**Status:** accepted · **Date:** 2026-09

## Context
The evaluation set is the most expensive artefact in the project (a week of
hand-written questions). Chunk ids change whenever chunking changes.

## Decision
Gold labels are `act_id:section_id`. Duplicate chunks of one section collapse
before ranking, so a long section cannot inflate metrics. Graded relevance
(0/1/2) is optional per question.

## Consequences
- Chunk-size sweeps, contextual retrieval and re-ingestion all reuse the same labels.
- Retrieval metrics measure sections found, which is what a lawyer would ask about.
- Sub-section precision ("2(c)(iv)") is not measured; it would need finer labels.
