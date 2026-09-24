"""Metadata filtering shared by every backend.

A filter value can be a scalar (equality), a list (membership) or a callable
(predicate). Keeping this in one place means the dense store, the BM25 index and
anything added later filter identically — a filter that behaves differently per
backend is a silent evaluation bug.
"""
from __future__ import annotations

from typing import Any


def matches(metadata: dict, filters: dict[str, Any] | None) -> bool:
    for key, want in (filters or {}).items():
        got = metadata.get(key)
        if callable(want):
            if not want(got):
                return False
        elif isinstance(want, (list, tuple, set)):
            if got not in want:
                return False
        elif got != want:
            return False
    return True
