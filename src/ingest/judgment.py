"""Court judgments (Supreme Court PDFs) -> chunks.

A judgment is not cut into sections the way an act is. It has a cause title
(court, case number, parties, judges, dates), then the reasoning as running
paragraphs that the Supreme Court's PDFs mostly leave unnumbered. So:

  * one overview chunk: the cause title plus the opening of the judgment, which
    says what the case is about and is what "is there a case on X?" should find;
  * body chunks packed from paragraphs up to `max_chars`, each tagged with the
    page it starts on. The page is the pin-point a reader can open: the citation
    reads "First Appeal No. 311 of 2016 (HCD), p. 5" and links to `url#page=5`.

The court, the case number and the date are read from the cause title when the
manifest does not give them. Nothing here needs PyMuPDF or Tesseract: the pages
come in as `PageText` from `ingest.pdf.extract_pages`, which the tests fake.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Chunk
from .pdf import PageText, strip_running_lines
from .textutils import detect_lang, nfc

_DIVISION = re.compile(r"\b(HIGH COURT|APPELLATE) DIVISION\b", re.I)
_BN_DIVISION = re.compile(nfc(r"(হাইকোর্ট|আপিল) বিভাগ"))
# "FIRST APPEAL NO.311 OF 2016", "Civil Petition for Leave to Appeal No. 4549 of 2018",
# "Writ Petition No. 1234 of 2020", "CIVIL APPEAL NO.73 OF 2023." The first match in
# the cause title is the case; later ones are connected cases and the case below.
_CASE_WORD = (r"(?:Civil|Criminal|First|Second|M+iscellaneous|Misc\.?|Writ|Jail|Death|Review|"
              r"Leave|Company|Admiralty|Contempt|Original|Petition|Appeal|Revision|Reference|"
              r"Rule|Matter|Suit|Application|for|to)")
_CASE = re.compile(
    rf"\b({_CASE_WORD}(?:\s+{_CASE_WORD}){{0,6}})\s*(\(\w+\)\s*)?Nos?\s*\.?\s*"
    r"([0-9][0-9A-Z()\-]*)\s+of\s+((?:19|20)\d\d)\b", re.I)
# The court's own list: "First Appeal 37/2022", "Civil Revision 2692/2017".
_LISTED = re.compile(r"^([A-Za-z][A-Za-z .()]+?)\s+(\d+)/((?:19|20)\d\d)$")
_DECIDED = re.compile(
    # Not "judgment and order dated ...": that is the decision appealed from.
    r"(?:Judgment|Judgement|Decided|Date of judgment)\s*(?:on|delivered on)?\s*:?\s*"
    r"(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d\d)", re.I)
# The first line of the reasoning: "S M Kuddus Zaman, J:" / "Hasan Foez Siddique, C.J.:"
_AUTHOR = re.compile(r"^\s*[A-Z][\w .'-]{2,60},\s*(?:C\.\s*)?J\.?\s*:", re.M)
_PAGE_ONLY = re.compile(r"^\s*[0-9০-৯]{1,3}\s*$")


@dataclass
class CaseInfo:
    court: str           # "Supreme Court of Bangladesh, High Court Division"
    division: str        # "HCD" | "AD" | ""
    case_number: str     # "First Appeal No. 311 of 2016"
    parties: str
    decided: str | None  # ISO date
    language: str


def _title(words: str) -> str:
    words = " ".join(words.split())
    if words.isupper() or words.islower():
        words = " ".join(w if w.lower() in ("for", "to") else w.capitalize() for w in words.split())
        words = words.replace("For ", "for ").replace("To ", "to ")
    return words


def find_case_number(text: str, listed: str | None = None) -> str:
    """'First Appeal No. 311 of 2016': the court list's entry when it is well formed,
    else the first case number in the cause title."""
    if listed and (m := _LISTED.match(listed.strip())):
        return f"{_title(m.group(1))} No. {m.group(2)} of {m.group(3)}"
    if m := _CASE.search(text):
        words, tag, number, year = m.groups()
        return f"{_title(words)}{' ' + tag.strip() if tag else ''} No. {number} of {year}"
    return ""


def case_info(text: str, meta: dict | None = None) -> CaseInfo:
    """Court, case number, parties and date from the cause title; the manifest wins."""
    meta = meta or {}
    head = text[:4000]
    division = meta.get("division") or ""
    if not division:
        m = _DIVISION.search(head) or _BN_DIVISION.search(head)
        if m:
            word = m.group(1).lower()
            division = "AD" if word in ("appellate", "আপিল") else "HCD"
    court = meta.get("court") or "Supreme Court of Bangladesh" + (
        {"AD": ", Appellate Division", "HCD": ", High Court Division"}.get(division, ""))
    case = meta.get("case_number") or find_case_number(head, meta.get("listed_as"))
    decided = meta.get("date")
    if not decided and (m := _DECIDED.search(head)):
        d, mo, y = m.groups()
        decided = f"{y}-{int(mo):02d}-{int(d):02d}"
    return CaseInfo(court=court, division=division, case_number=case,
                    parties=meta.get("parties") or "", decided=decided,
                    language=meta.get("language") or detect_lang(text))


def judgment_citation(m: dict) -> str:
    """'First Appeal No. 311 of 2016 (HCD), p. 5' for a body chunk; no page for the overview."""
    case = m.get("case_number") or m.get("act_title") or "Judgment"
    court = f" ({m['division']})" if m.get("division") else ""
    page = m.get("page")
    if m.get("part_of") == "overview" or not page:
        return f"{case}{court}"
    return f"{case}{court}, {'পৃ.' if m.get('language') == 'bn' else 'p.'} {page}"


def _paragraphs(pages: list[PageText]) -> list[tuple[int, str]]:
    """(page, paragraph) in reading order. A paragraph ends at a blank line or at a
    line that starts indented after a line that ended a sentence; page numbers
    printed on their own line are dropped."""
    out: list[tuple[int, str]] = []

    def flush(page: int, cur: list[str]) -> None:
        text = " ".join(" ".join(cur).split())
        if text:
            out.append((page, text))
        cur.clear()

    for p in pages:
        cur: list[str] = []
        for raw in p.text.splitlines():
            line = raw.rstrip()
            if _PAGE_ONLY.match(line):
                continue
            if not line.strip():
                flush(p.page, cur)
                continue
            ended = bool(cur) and cur[-1].rstrip().endswith((".", "।", ":", "?"))
            if ended and raw[:1].isspace():
                flush(p.page, cur)
            cur.append(line.strip())
        flush(p.page, cur)
    # A paragraph that runs over a page break continues on the next page: join
    # it back when the first piece did not end a sentence.
    joined: list[tuple[int, str]] = []
    for page, text in out:
        if joined and not joined[-1][1].endswith((".", "।", ":", "?", ";")) and text[:1].islower():
            joined[-1] = (joined[-1][0], f"{joined[-1][1]} {text}")
        else:
            joined.append((page, text))
    return joined


def reasoning_pages(pages: list[PageText], within: int = 6000) -> list[PageText]:
    """The pages from the author line ("S M Kuddus Zaman, J:") on, that page cut there."""
    seen = 0
    for i, p in enumerate(pages):
        if (m := _AUTHOR.search(p.text)) and seen + m.start() < within:
            return [PageText(p.page, p.text[m.end():], p.ocr), *pages[i + 1:]]
        seen += len(p.text)
        if seen >= within:
            break
    return pages


def judgment_chunks(pages: list[PageText], doc_id: int, meta: dict,
                    max_chars: int = 1800, overview_chars: int = 2500) -> list[Chunk]:
    """Overview + page-anchored body chunks for one judgment."""
    pages = strip_running_lines([p for p in pages if p.text.strip()])
    full = "\n".join(p.text for p in pages)
    if not full.strip():
        return []
    info = case_info(full, meta)
    title = info.case_number or meta.get("title") or "Judgment"
    url = meta.get("url") or ""
    base = {
        "type": "judgment", "doc_type": "judgment", "act_id": doc_id, "act_title": title,
        "act_year": int(info.decided[:4]) if info.decided else None,
        "language": info.language, "repealed": False, "court": info.court,
        "division": info.division, "case_number": info.case_number, "parties": info.parties,
        "decided": info.decided, "source": "judgment", "source_id": meta.get("id"),
    }
    header = " > ".join(x for x in (info.court, info.case_number, info.parties) if x)

    # Overview: everything before the author line ("..., J:") is the cause title;
    # keep it and the first paragraphs of the reasoning.
    m = _AUTHOR.search(full)
    cut = m.end() if m and m.start() < 6000 else 0
    cause = " ".join(full[:cut].split()) if cut else ""
    opening = " ".join(full[cut:cut + overview_chars].split())
    body = (f"{cause}\n\n{opening}" if cause else opening)[:overview_chars].strip()
    chunks = [Chunk(chunk_id=f"{doc_id}-overview", text=f"{header}\n\n{body}", body=body,
                    metadata={**base, "part_of": "overview", "page": 1, "section_id": 0,
                              "url": url, "char_len": len(body)})]

    # The body starts at the author line; the cause title before it (counsel,
    # judges) is in the overview already and answers no legal question.
    paras = _paragraphs(reasoning_pages(pages) if cause else pages)
    parts: list[tuple[int, str]] = []
    cur_page, cur = 0, ""
    for page, text in paras:
        while len(text) > max_chars:          # one enormous paragraph (a quoted schedule)
            cut_at = text.rfind(" ", 0, max_chars)
            cut_at = cut_at if cut_at > max_chars // 2 else max_chars
            if cur:
                parts.append((cur_page, cur))
                cur = ""
            parts.append((page, text[:cut_at].strip()))
            text = text[cut_at:].strip()
        if cur and len(cur) + 2 + len(text) > max_chars:
            parts.append((cur_page, cur))
            cur = ""
        if not cur:
            cur_page = page
        cur = f"{cur}\n\n{text}" if cur else text
    if cur:
        parts.append((cur_page, cur))
    label = "পৃষ্ঠা" if info.language == "bn" else "Page"
    for i, (page, text) in enumerate(parts, start=1):
        chunks.append(Chunk(
            chunk_id=f"{doc_id}-{i}",
            text=f"{header} > {label} {page}\n\n{text}",
            body=text,
            metadata={**base, "part_of": "body", "page": page, "section_id": i,
                      "section_number": str(page), "section_number_ascii": str(page),
                      "part": i, "n_parts": len(parts),
                      "url": f"{url}#page={page}" if url else "", "char_len": len(text)}))
    return chunks
