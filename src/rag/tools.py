"""Tools the agent can call, and the evidence book that keeps citations stable.

The problem an agent creates for citations: if every search renumbers the
excerpts, [2] means something different at every step and the final answer's
citations are meaningless. So all retrieval, from every tool call, lands in one
EvidenceBook that assigns each chunk a number once and never reuses it. The
answer cites those numbers, and Phase 5's checks verify them against the same
book.

Five tools, because a legal question needs five kinds of lookup:
  search           - find provisions by meaning or wording
  get_section      - fetch a section by number, when the question names one
  follow_refs      - resolve "as defined in section 2" from metadata["refs"], and
                     "under the Companies Act, 1994" from metadata["act_refs"]
  compare_sections - put two provisions side by side (a very common question)
  list_acts        - find the act_id for an act the user names
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar, cast

from ingest.textutils import bn_to_ascii_digits

from .store import Hit


@dataclass
class EvidenceBook:
    """Stable, global numbering for everything retrieved during one question."""
    hits: list[Hit] = field(default_factory=list)
    _seen: dict[str, int] = field(default_factory=dict)

    def add(self, hits: list[Hit]) -> list[int]:
        """Add hits, return their (possibly pre-existing) numbers."""
        numbers = []
        for h in hits:
            n = self._seen.get(h.chunk_id)
            if n is None:
                self.hits.append(h)
                n = len(self.hits)
                self._seen[h.chunk_id] = n
            numbers.append(n)
        return numbers

    def __len__(self) -> int:
        return len(self.hits)

    def render(self, numbers: list[int] | None = None, max_chars: int = 900) -> str:
        chosen = numbers or range(1, len(self.hits) + 1)
        blocks = []
        for n in chosen:
            h = self.hits[n - 1]
            head = f"[{n}] {h.citation}"
            if h.metadata.get("section_title"):
                head += f" — {h.metadata['section_title']}"
            if h.metadata.get("amended"):
                head += " [amended]"
            refs = h.metadata.get("refs") or []
            if refs:
                head += f"  (refers to sections: {', '.join(map(str, refs[:8]))})"
            blocks.append(f"{head}\n{h.body[:max_chars]}")
        return "\n\n".join(blocks) if blocks else "(nothing)"


class SectionLookup:
    """act_id + section number -> chunks, plus act overviews, for exact lookups."""

    def __init__(self, records: list[dict]) -> None:
        self.by_number: dict[tuple[int, str], list[Hit]] = {}
        self.overviews: dict[int, Hit] = {}
        self.acts: dict[int, str] = {}
        for r in records:
            m = r["metadata"]
            if m.get("act_id") is not None and m.get("act_title"):
                self.acts.setdefault(m["act_id"], m["act_title"])
            if m.get("type") == "act_overview":
                self.overviews.setdefault(m["act_id"],
                                          Hit(r["chunk_id"], 1.0, r["text"], r["body"], m))
            num = str(m.get("section_number_ascii") or m.get("section_number") or "")
            if not num:
                continue
            key = (m.get("act_id"), bn_to_ascii_digits(num).upper())
            self.by_number.setdefault(key, []).append(
                Hit(r["chunk_id"], 1.0, r["text"], r["body"], m))

    def get(self, act_id: int, number: str, max_parts: int = 3) -> list[Hit]:
        key = (act_id, bn_to_ascii_digits(str(number)).strip().upper())
        return self.by_number.get(key, [])[:max_parts]

    def overview(self, act_id: int) -> list[Hit]:
        hit = self.overviews.get(int(act_id))
        return [hit] if hit else []

    def find_acts(self, query: str, limit: int = 5) -> list[tuple[int, str]]:
        words = [w for w in query.lower().split() if len(w) > 2]
        scored = [(sum(w in title.lower() for w in words), aid, title)
                  for aid, title in self.acts.items()]
        return [(aid, title) for score, aid, title in sorted(scored, reverse=True)
                if score > 0][:limit]


class ToolBox:
    def __init__(self, pipeline, lookup: SectionLookup, book: EvidenceBook,
                 per_call_k: int = 5) -> None:
        self.pipeline, self.lookup, self.book, self.k = pipeline, lookup, book, per_call_k
        self.calls: list[dict] = []

    # ---- the tools ---------------------------------------------------
    def search(self, query: str, k: int | None = None, language: str | None = None,
               act_id: int | None = None) -> str:
        hits = self.pipeline.search(query, k=k or self.k, language=language, act_id=act_id)
        if not hits:
            return "No provisions matched. Try different wording, or a different act."
        return self.book.render(self.book.add(hits))

    def get_section(self, act_id: int, section: str) -> str:
        hits = self.lookup.get(int(act_id), section)
        if not hits:
            return (f"No section {section} in act {act_id}. Use search to find the right act, "
                    f"and check the act_id shown in an excerpt you already have.")
        return self.book.render(self.book.add(hits))

    def follow_refs(self, excerpt: int, limit: int = 3) -> str:
        """Fetch what excerpt [n] points at — sections of the same act, and other acts."""
        if not 1 <= int(excerpt) <= len(self.book):
            return f"No excerpt [{excerpt}] exists yet."
        src = self.book.hits[int(excerpt) - 1]
        refs = (src.metadata.get("refs") or [])[:limit]
        act_refs = cast(list[dict[str, Any]], (src.metadata.get("act_refs") or [])[:limit])
        if not refs and not act_refs:
            return f"Excerpt [{excerpt}] refers to no other provision."
        found: list[Hit] = []
        for ref in refs:
            act_id = src.metadata.get("act_id")
            if act_id is not None:
                found += self.lookup.get(int(act_id), ref)
        for entry in act_refs:                 # cross-act: give the act's overview
            entry_act_id = entry.get("act_id")
            if entry_act_id is not None:
                found += self.lookup.overview(int(entry_act_id))
        if not found:
            named = refs + [e.get("title", "") for e in act_refs]
            return (f"Excerpt [{excerpt}] refers to {named}, but none of them are in the "
                    f"corpus — say so in your answer rather than guessing their contents.")
        return self.book.render(self.book.add(found))

    def compare_sections(self, act_id: int, section_a: str, section_b: str) -> str:
        """Put two provisions side by side — 'what is the difference between 302 and 304A?'."""
        hits = self.lookup.get(int(act_id), section_a) + self.lookup.get(int(act_id), section_b)
        if not hits:
            return f"Neither section {section_a} nor {section_b} is in act {act_id}."
        return self.book.render(self.book.add(hits))

    def list_acts(self, query: str) -> str:
        """Find the act_id for an act named in the question."""
        found = self.lookup.find_acts(query)
        if not found:
            return f"No act in the corpus matches '{query}'."
        return "\n".join(f"act_id {aid}: {title}" for aid, title in found)

    # ---- dispatch -----------------------------------------------------
    SPECS: ClassVar[dict[str, dict[str, Any]]] = {
        "search": {"args": {"query": "str, required", "k": "int, optional",
                            "language": "'bn' or 'en', optional",
                            "act_id": "int, optional — restrict to one act"},
                   "use": "find provisions by meaning or exact wording"},
        "get_section": {"args": {"act_id": "int, required", "section": "str, required, e.g. '302'"},
                        "use": "fetch a numbered section when the question names one"},
        "follow_refs": {"args": {"excerpt": "int, required — an excerpt number you already have",
                                 "limit": "int, optional"},
                        "use": "resolve cross-references like 'as defined in section 2' or "
                               "'under the Companies Act, 1994'"},
        "compare_sections": {"args": {"act_id": "int, required", "section_a": "str, required",
                                      "section_b": "str, required"},
                             "use": "fetch two provisions together to contrast them"},
        "list_acts": {"args": {"query": "str, required — words from the act's name"},
                      "use": "find the act_id of an act the question names"},
    }

    def describe(self) -> str:
        lines = []
        for name, spec in self.SPECS.items():
            args = ", ".join(f"{k} ({v})" for k, v in spec["args"].items())
            lines.append(f"- {name}({args})\n    {spec['use']}")
        return "\n".join(lines)

    def run(self, name: str, args: dict) -> str:
        if name not in self.SPECS:
            return f"Unknown tool '{name}'. Available: {', '.join(self.SPECS)}."
        fn = getattr(self, name)
        allowed = set(self.SPECS[name]["args"])
        clean = {k: v for k, v in (args or {}).items() if k in allowed}
        try:
            result = fn(**clean)
        except TypeError as e:
            result = f"Bad arguments for {name}: {e}. Expected {json.dumps(list(allowed))}."
        except Exception as e:                      # a tool must never kill the loop
            result = f"{name} failed: {type(e).__name__}: {e}"
        self.calls.append({"tool": name, "args": clean, "chars": len(result)})
        return result
