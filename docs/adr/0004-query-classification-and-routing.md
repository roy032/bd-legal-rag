# ADR 0004 — Route by query type instead of tuning one global weight

**Status:** accepted · **Date:** 2026-09

## Context
"ধারা ৩০২ কী বলে?" and "ভাড়াটিয়াকে উচ্ছেদ করা যায় কীভাবে?" want opposite things
from retrieval. A single fusion weight is a compromise that serves neither.

## Decision
Classify each question as `exact_ref`, `comparative` or `conceptual` with a
cheap regex, and pick a weight profile per class. The same signal decides
whether the agent is worth its extra calls.

## Consequences
- Better results than a global weight, at no inference cost.
- Two things to tune instead of one; both live in `lexicon.py` with the profiles.
- A misclassification degrades to the other profile's behaviour, not to failure.

## Alternatives
A learned classifier (needs labels, adds latency); one global weight (worse on
both ends); always running everything (costly and no better).
