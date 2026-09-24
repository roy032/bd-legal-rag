# ADR 0005 — Enforce the answer contract in code, not only in the prompt

**Status:** accepted · **Date:** 2026-09

## Context
Prompts ask for citations, verbatim quotes and the right language. Models comply
most of the time, and "most of the time" is not a contract you can ship in a
legal setting.

## Decision
Deterministic checks run on every answer: per-sentence citation coverage,
verbatim quote verification against the *cited* excerpts, language match, and —
when an entailer is configured — per-claim entailment. One corrective re-prompt,
kept only if it reduces the failure count. Failures are reported, never hidden.

## Consequences
- Hallucinated quotations and unsupported claims are caught mechanically.
- One extra model call on the answers that fail, and `clean_first_pass` becomes
  the metric to watch over time.
- Checks are strict and produce occasional false alarms; the cost of a false
  alarm is a re-prompt, the cost of a miss is credibility.
