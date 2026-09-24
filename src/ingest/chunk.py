"""Structure-aware chunking.

Rule 1: one legal section = one chunk. Sections are the unit lawyers cite, so
        they are the unit we retrieve.
Rule 2: a section that is too long (e.g. a 'Definitions' section with 40
        clauses) is split at subsection/clause boundaries, never mid-sentence
        unless a single clause is itself too long.
Rule 3: every chunk's embedded text starts with a context header
        (act > chapter > section) so a chunk like "(2) The fine shall not
        exceed..." is still findable and understandable on its own.
"""
from __future__ import annotations

import re

from .models import Act, Chunk, Section
from .textutils import extract_section_refs, nfc

# Line starts a new subsection/clause: (1) (১) (a) (ক) (i) 1. ১।
SUBSECTION_START = re.compile(nfc(
    r"^\s*(?:\(\s*[0-9০-৯]+[A-Za-z]?\s*\)|\(\s*[a-zA-Zক-হ]{1,4}\s*\)|[0-9০-৯]+\s*[।.)])"
))
SENTENCE_END = re.compile(r"(?<=[।.;])\s+")


def _header(act: Act, sec: Section) -> str:
    label = "ধারা" if act.language == "bn" else "Section"
    parts = [act.title]
    if sec.chapter:
        parts.append(sec.chapter)
    parts.append(f"{label} {sec.number}: {sec.title}".strip())
    return " > ".join(parts)


def _split_units(text: str) -> list[str]:
    """Split a section body into subsection/clause units."""
    units: list[list[str]] = [[]]
    for line in text.splitlines():
        if SUBSECTION_START.match(line) and units[-1]:
            units.append([])
        units[-1].append(line)
    return ["\n".join(u).strip() for u in units if "\n".join(u).strip()]


def _pack(units: list[str], max_chars: int) -> list[str]:
    """Greedily pack units into parts <= max_chars; sentence-split oversize units."""
    pieces: list[str] = []
    for u in units:
        if len(u) <= max_chars:
            pieces.append(u)
        else:
            pieces.extend(s for s in SENTENCE_END.split(u) if s.strip())
    parts, cur = [], ""
    for p in pieces:
        if cur and len(cur) + 1 + len(p) > max_chars:
            parts.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        parts.append(cur)
    return parts


def chunk_section(act: Act, sec: Section, max_chars: int = 1800) -> list[Chunk]:
    if not sec.text.strip():
        return []
    header = _header(act, sec)
    units = _split_units(sec.text)
    parts = [sec.text] if len(sec.text) <= max_chars else _pack(units, max_chars)

    # The lead-in ("In this Act, unless the context otherwise requires,—")
    # gives meaning to every later clause, so repeat it for parts 2..n.
    lead_in = units[0] if len(units) > 1 and len(units[0]) < 400 else ""

    chunks = []
    for i, body in enumerate(parts, start=1):
        prefix = header
        if i > 1 and lead_in and not body.startswith(lead_in):
            prefix += f"\n{lead_in} …"
        chunks.append(
            Chunk(
                chunk_id=f"{act.act_id}-{sec.section_id}-{i}",
                text=f"{prefix}\n\n{body}",
                body=body,
                metadata={
                    "type": "section",
                    "act_id": act.act_id,
                    "act_title": act.title,
                    "act_number": act.act_number,
                    "act_year": act.year,
                    "language": act.language,
                    "repealed": act.repealed,
                    "chapter": sec.chapter,
                    "section_id": sec.section_id,
                    "section_number": sec.number,
                    "section_number_ascii": sec.number_ascii,
                    "section_title": sec.title,
                    "part": i,
                    "n_parts": len(parts),
                    "refs": extract_section_refs(body),
                    "act_refs": sec.act_refs if i == 1 else [],
                    "amended": bool(sec.footnotes),
                    "footnotes": sec.footnotes if i == 1 else [],
                    "url": sec.url,
                    "char_len": len(body),
                },
            )
        )
    return chunks


def act_overview_chunk(act: Act, max_sections: int = 150) -> Chunk:
    """One chunk per act answering 'what is this law / what does it cover?'."""
    toc_lines, chapter = [], None
    for s in act.sections[:max_sections]:
        if s.chapter and s.chapter != chapter:
            chapter = s.chapter
            toc_lines.append(f"{chapter}")
        toc_lines.append(f"  {s.number}. {s.title}")
    head = [act.title]
    if act.act_number:
        head.append(f"({act.act_number})")
    if act.date:
        head.append(f"[{act.date}]")
    body = "\n".join(head + ([act.preamble] if act.preamble else []) + [""] + toc_lines)
    return Chunk(
        chunk_id=f"{act.act_id}-overview",
        text=body,
        body=body,
        metadata={
            "type": "act_overview",
            "act_id": act.act_id,
            "act_title": act.title,
            "act_number": act.act_number,
            "act_year": act.year,
            "language": act.language,
            "repealed": act.repealed,
            "n_sections": len(act.sections),
            "url": act.url,
            "char_len": len(body),
        },
    )
