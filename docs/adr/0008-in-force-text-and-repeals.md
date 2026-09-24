# ADR 0008 — Treat the site's text as consolidated; prefer in-force law

**Status:** accepted · **Date:** 2026-09

## Context
bdlaws publishes each act as currently amended: amendments are already applied
to the section text and recorded as footnotes. Repealed acts stay on the site
with a notice naming the replacing act. The first version penalised any section
with an amendment footnote, which pushed the *current* text of heavily amended
sections (e.g. many Penal Code sections) below stale or unrelated ones.

## Decision
- Section text is taken as the law in force. Amendment footnotes that belong to
  the section (matched by their markers) are kept as metadata and appended to the
  embedded text under "Amendments:", not mixed into the body shown to users.
- Amended sections are **not** penalised. Sections marked omitted and sections
  of repealed acts are down-weighted by `boost_in_force`, and answers label
  repealed sources `[REPEALED ACT]` with the site's repeal note.
- Ingest skips repealed acts by default (`--include-repealed` keeps them), using
  the `[Repealed]` / `[রহিত]` tag in the site index, which saves a large share
  of download time and disk space.

## Consequences
- Answers reflect the law as the site presents it today. Point-in-time questions
  ("what did section X say in 2005?") are out of scope.
- Correctness depends on the site's consolidation. Live verification (ADR 0010)
  re-checks cited sections against the current page.
