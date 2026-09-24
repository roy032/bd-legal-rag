"""Parent–child retrieval.

Small chunks match a question precisely; whole sections read correctly. So:
search the children, then hand the model the parent section. The classic case
here is a long 'Definitions' section — a query matches clause (ঝ), but an
answer that quotes clause (ঝ) without its lead-in ("In this Act, unless the
context otherwise requires—") misstates the law.

Scores and chunk ids stay those of the matching child, so evaluation still
measures what retrieval actually ranked.
"""
from __future__ import annotations

from .store import Hit


class ParentIndex:
    """Section key -> the section's full text, rebuilt from its chunk parts."""

    def __init__(self, records: list[dict]) -> None:
        parts: dict[tuple, list[tuple[int, str]]] = {}
        for r in records:
            m = r["metadata"]
            if m.get("type") != "section":
                continue
            key = (m.get("act_id"), m.get("section_id"))
            parts.setdefault(key, []).append((int(m.get("part", 1)), r["body"]))
        self.sections = {k: "\n".join(body for _, body in sorted(v)) for k, v in parts.items()}

    def get(self, metadata: dict) -> str | None:
        return self.sections.get((metadata.get("act_id"), metadata.get("section_id")))

    def __len__(self) -> int:
        return len(self.sections)


def expand_to_parents(hits: list[Hit], index: ParentIndex, max_chars: int = 4000,
                      dedupe: bool = True) -> list[Hit]:
    """Replace each chunk's body with its whole section, dropping duplicates."""
    out: list[Hit] = []
    seen: set[tuple] = set()
    for h in hits:
        key = (h.metadata.get("act_id"), h.metadata.get("section_id"))
        if dedupe and key in seen:
            continue
        seen.add(key)
        parent = index.get(h.metadata)
        body = h.body if not parent else parent[:max_chars]
        out.append(Hit(h.chunk_id, h.score, h.text, body,
                       {**h.metadata, "parent_expanded": bool(parent) and body != h.body}))
    return out
