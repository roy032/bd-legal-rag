"""Query -> chunks."""
from __future__ import annotations

from typing import Any

from .embed import Embedder
from .store import Hit


class Retriever:
    def __init__(self, embedder: Embedder, store) -> None:
        self.embedder = embedder
        self.store = store

    def search(
        self,
        question: str,
        k: int = 5,
        language: str | None = None,
        act_id: int | None = None,
        include_repealed: bool = False,
        year_from: int | None = None,
        extra_filters: dict[str, Any] | None = None,
        max_parts_per_section: int | None = None,
    ) -> list[Hit]:
        filters: dict[str, Any] = dict(extra_filters or {})
        if language:
            filters["language"] = [language, "mixed"]
        if act_id is not None:
            filters["act_id"] = act_id
        if not include_repealed:
            # Repealed law is still law-shaped text: retrieving it is how a RAG
            # system confidently cites a statute that no longer exists.
            filters["repealed"] = False
        if year_from is not None:
            filters["act_year"] = lambda y: y is not None and y >= year_from
        qvec = self.embedder.encode_queries([question])[0]
        if max_parts_per_section:
            # Over-fetch, drop surplus parts of the same section, then trim back to k.
            hits = self.store.search(qvec, k=k * 4, filters=filters)
            return dedupe_by_section(hits, max_parts=max_parts_per_section)[:k]
        return self.store.search(qvec, k=k, filters=filters)


def dedupe_by_section(hits: list[Hit], max_parts: int = 2) -> list[Hit]:
    """Keep at most `max_parts` chunks from the same section, so one long
    'Definitions' section cannot crowd out every other result."""
    seen: dict[tuple, int] = {}
    out = []
    for h in hits:
        key = (h.metadata.get("act_id"), h.metadata.get("section_id"))
        if seen.get(key, 0) >= max_parts:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(h)
    return out
