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
    if getattr(sec, "heading", None):
        parts.append(sec.heading)
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


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last resort for a single 'sentence' longer than max_chars (schedules,
    tables flattened to text): cut at the last space before the limit."""
    out = []
    while len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars)
        cut = cut if cut > max_chars // 2 else max_chars
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def _pack(units: list[str], max_chars: int) -> list[str]:
    """Greedily pack units into parts <= max_chars; sentence-split oversize units."""
    pieces: list[str] = []
    for u in units:
        if len(u) <= max_chars:
            pieces.append(u)
        else:
            for sent in SENTENCE_END.split(u):
                if sent.strip():
                    pieces.extend(_hard_split(sent, max_chars))
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
        embedded = f"{prefix}\n\n{body}"
        if i == 1 and sec.footnotes:
            # Amendment notes answer "when/how was this changed?" questions, so
            # they are searchable — but kept out of `body`, which is the quoted law.
            label = "সংশোধনী" if act.language == "bn" else "Amendments"
            embedded += f"\n\n{label}: " + " ".join(sec.footnotes)[:600]
        chunks.append(
            Chunk(
                chunk_id=f"{act.act_id}-{sec.section_id}-{i}",
                text=embedded,
                body=body,
                metadata={
                    "type": "section",
                    "act_id": act.act_id,
                    "act_title": act.title,
                    "act_number": act.act_number,
                    "act_year": act.year,
                    "language": act.language,
                    "repealed": act.repealed,
                    "repeal_note": act.repeal_note,
                    "part_of_act": getattr(sec, "part", None),
                    "chapter": sec.chapter,
                    "heading": getattr(sec, "heading", None),
                    "omitted": getattr(sec, "omitted", False),
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


def act_overview_chunk(act: Act, max_chars: int = 3000) -> Chunk:
    """One chunk per act answering 'what is this law / what does it cover?'.

    Bounded in size: a 500-section code would otherwise produce a 12k-character
    chunk that no embedder reads to the end. Chapter names come first because
    they summarise the act better than the first N section titles do.
    """
    head = [act.title]
    if act.act_number:
        head.append(f"({act.act_number})")
    if act.date:
        head.append(f"[{act.date}]")
    if act.repeal_note:
        head.append(act.repeal_note)
    if act.preamble:
        head.append(act.preamble[:800])
    chapters = list(dict.fromkeys(s.chapter for s in act.sections if s.chapter))
    lines = head + [""] + chapters + [""]
    for s in act.sections:
        if getattr(s, "inherited_number", False):
            continue
        lines.append(f"{s.number}. {s.title}" if s.number else s.title)
    body, used = [], 0
    for ln in lines:
        if used + len(ln) + 1 > max_chars:
            body.append("…")
            break
        body.append(ln)
        used += len(ln) + 1
    body = "\n".join(body).strip()
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
            "repeal_note": act.repeal_note,
            "n_sections": len(act.sections),
            "url": act.url,
            "char_len": len(body),
        },
    )
