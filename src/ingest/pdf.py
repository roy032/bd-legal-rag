"""Acts that only exist as PDFs, including scanned ones.

bdlaws serves most acts as HTML, which `parse.py` handles. Some acts (older
gazettes, ordinances, rules) are only available as PDF, and some of those are
scanned images with no text layer at all. This module turns such a PDF into the
same Act / Section / Chunk objects the HTML path produces, so the index, the
citations and the guardrails treat them alike.

    pages = extract_pages("gazette.pdf")          # text layer, OCR where it is missing
    act, sections = build_act(pages, act_id=900001, title="...")

OCR runs Tesseract with Bangla + English (`ben+eng`); English-only OCR turns
Bangla into noise. Both PyMuPDF and pytesseract are optional extras
(`pip install -e ".[pdf]"` plus the `tesseract-ocr-ben` language pack); the
pure-text helpers below need neither, which is what the tests exercise.
"""
from __future__ import annotations

import re
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .models import Act, Section, SectionRef
from .textutils import (
    bn_to_ascii_digits,
    detect_lang,
    extract_year,
    fix_legacy_bangla,
    nfc,
    normalize,
)

# A page whose text layer has fewer characters than this is treated as scanned.
MIN_TEXT_CHARS = 30
PDF_ACT_ID_BASE = 900_000      # synthetic ids, well above the site's act numbers
MAX_JUMP = 60


@dataclass
class PageText:
    page: int          # 1-based
    text: str
    ocr: bool          # True when the text came from OCR, not the PDF's text layer


def _ocr_page(page, lang: str, dpi: int) -> str:
    import pytesseract  # optional: pip install -e ".[pdf]"
    from PIL import Image

    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB" if pix.n < 4 else "RGBA", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img.convert("L"), lang=lang)


def extract_pages(path: str | Path, ocr: str = "auto", lang: str = "ben+eng",
                  dpi: int = 300, min_chars: int = MIN_TEXT_CHARS) -> list[PageText]:
    """Text of every page. ocr: 'auto' (only near-empty pages), 'always' or 'never'."""
    try:
        import pymupdf as fitz  # optional: pip install -e ".[pdf]"
    except ImportError:          # PyMuPDF before 1.24 only has the old name
        import fitz

    out: list[PageText] = []
    with fitz.open(str(path)) as doc:
        for n, page in enumerate(doc, start=1):
            text = page.get_text("text", sort=True) or ""   # sort: keep visual lines whole
            used_ocr = False
            if ocr == "always" or (ocr == "auto" and len(text.strip()) < min_chars):
                text = _ocr_page(page, lang, dpi)
                used_ocr = True
            out.append(PageText(n, clean_page(text), used_ocr))
    return out


# A vowel sign repeated back to back is never valid Bangla; some PDF text layers
# emit each one twice (ভোক্তাা).
_DOUBLED_SIGN = re.compile("([\u09be-\u09cc\u09d7])\\1+")
# OCR reads the em dash after a heading as "-_", "__" or "___".
_OCR_DASH = re.compile(r"\s*(?:-_+|_{2,}|-{2,})\s*")
# OCR often reads the dari (।) after a section number as a pipe: "৪৫ | ...".
_PIPE_DARI = re.compile(nfc(r"^([০-৯]{1,4}[ক-হ]?)\s*\|\s*"), re.M)


def clean_page(text: str) -> str:
    text = _DOUBLED_SIGN.sub(r"\1", nfc(text))
    text = _OCR_DASH.sub("—", text)
    text = _PIPE_DARI.sub(r"\1। ", text)
    return normalize(fix_legacy_bangla(text))


_PAGE_NO = re.compile(r"^(?:page\s*)?[-–]?\s*[0-9০-৯]{1,4}\s*(?:/\s*[0-9০-৯]{1,4}\s*)?[-–]?$", re.I)
_URL_LINE = re.compile(r"^(?:file|https?):/+\S+\|?$", re.I)


def _line_key(line: str) -> str:
    # Running headers differ only in their numbers (date, page): compare without them.
    return re.sub(r"[0-9০-৯]+", "#", line.strip().lower())


def strip_running_lines(pages: list[PageText], min_share: float = 0.5) -> list[PageText]:
    """Drop headers/footers that repeat across pages, and bare page numbers.

    Browser "print to PDF" copies stamp a date + title line on every page; left
    in, it ends up in a quarter of all chunks and drags retrieval toward them.
    """
    seen: Counter = Counter()
    for p in pages:
        seen.update({_line_key(ln) for ln in p.text.splitlines() if ln.strip()})
    limit = max(2, int(len(pages) * min_share + 0.999))
    # In a short document a sentence can recur by chance; there only lines with a
    # number in them (dates, page counters) count as running headers.
    repeated = {k for k, c in seen.items()
                if c >= limit and (len(pages) >= 4 or "#" in k)} if len(pages) >= 2 else set()
    out = []
    for p in pages:
        keep = [ln for ln in p.text.splitlines()
                if not _PAGE_NO.match(ln.strip()) and not _URL_LINE.match(ln.strip())
                and _line_key(ln) not in repeated]
        out.append(PageText(p.page, "\n".join(keep).strip(), p.ocr))
    return out


# "302. Punishment for murder.—", "25A. ...", "৩০২। খুনের শাস্তি।—". Bangla
# headings end the number with a dari; "১." is a clause in a list, not a section.
_EN_HEAD = re.compile(r"^(\d{1,4}[A-Z]{0,2})\.\s+(\S.*)$")
_BN_HEAD = re.compile(nfc(r"^([০-৯]{1,4}[ক-হ]?)\s*।\s*(\S.*)$"))
_TITLE_END = re.compile(nfc(r"\s*(?:[.।]\s*)?(?:[—–]|--)|[.।](?:\s|$)"))


def _number_value(no: str) -> int:
    return int(re.sub(r"\D", "", bn_to_ascii_digits(no)) or 0)


def _heading(line: str) -> tuple[str, str, str] | None:
    """(number as printed, title, rest of the line) for a section heading line."""
    m = _EN_HEAD.match(line) or _BN_HEAD.match(line)
    if not m:
        return None
    no, tail = m.group(1), m.group(2)
    end = _TITLE_END.search(tail)
    if not end or end.start() == 0 or end.start() > 160:
        return None                       # a numbered list item, not a section heading
    return no, tail[: end.start()].strip(), tail[end.end():].strip()


@dataclass
class _Draft:
    number: str
    title: str
    page: int
    lines: list[str]


def split_sections(pages: list[PageText]) -> list[_Draft]:
    """Cut the act's text at section headings.

    After the first heading, one is accepted only if its number moves forward, by at most MAX_JUMP,
    which keeps numbered clauses ("1. the Government; ...") inside the section
    they belong to while still allowing an excerpt that skips sections.
    """
    drafts: list[_Draft] = []
    last = 0
    preamble: list[str] = []
    for p in pages:
        lines = p.text.splitlines()
        i = 0
        while i < len(lines):
            line, used = lines[i].strip(), 1
            head = _heading(line)
            # A long heading wraps: "৪৫। প্রতিশ্রুত পণ্য ... না" / "করিবার দণ্ড।—কোন ...".
            while head is None and used < 3 and i + used < len(lines) and \
                    (_EN_HEAD.match(line) or _BN_HEAD.match(line)):
                line = f"{line} {lines[i + used].strip()}"
                used += 1
                head = _heading(line)
            if head:
                value = _number_value(head[0])
                same = bool(drafts) and value == last and head[0] != drafts[-1].number  # 25 -> 25A
                first = not drafts           # an excerpt may start anywhere
                if first or (last < value <= last + MAX_JUMP) or same:
                    drafts.append(_Draft(head[0], head[1], p.page, [head[2]] if head[2] else []))
                    last = value
                    i += used
                    continue
            (drafts[-1].lines if drafts else preamble).append(lines[i])
            i += 1
    if preamble and drafts:
        drafts.insert(0, _Draft("", "প্রস্তাবনা" if detect_lang("\n".join(preamble)) == "bn" else "Preamble",
                                pages[0].page, preamble))
    return drafts


def default_act_id(path: str | Path) -> int:
    return PDF_ACT_ID_BASE + zlib.crc32(Path(path).name.encode()) % 100_000


def build_act(pages: list[PageText], act_id: int, title: str | None = None,
              source: str = "") -> tuple[Act, list[Section], dict[int, dict]]:
    """Act + its sections, plus per-section extras (page, ocr) for chunk metadata.

    When no section headings are found (a schedule, a notification), each page
    becomes one pseudo-section so the text is still searchable and citable by page.
    """
    pages = strip_running_lines([p for p in pages if p.text.strip()])
    full = "\n".join(p.text for p in pages)
    if not title:
        title = next((ln.strip() for ln in full.splitlines() if len(ln.strip()) > 8), "Untitled PDF")
    lang = detect_lang(full)
    act = Act(act_id=act_id, title=title, act_number=None, date=None, preamble=None,
              year=extract_year(title), language=lang, repealed=False, url=source)
    ocr_pages = {p.page for p in pages if p.ocr}
    drafts = split_sections(pages) or [
        _Draft("", f"{'পৃষ্ঠা' if lang == 'bn' else 'Page'} {p.page}", p.page, p.text.splitlines())
        for p in pages]
    sections: list[Section] = []
    extras: dict[int, dict] = {}
    for i, d in enumerate(drafts, start=1):
        url = f"{source}#page={d.page}" if source else ""
        ascii_no = bn_to_ascii_digits(d.number)
        act.sections.append(SectionRef(i, d.number, ascii_no, d.title, None, url))
        sections.append(Section(act_id=act_id, section_id=i, number=d.number,
                                number_ascii=ascii_no, title=d.title, chapter=None,
                                text="\n".join(d.lines).strip().lstrip("—–- ").strip(),
                                footnotes=[], url=url))
        extras[i] = {"source": "pdf", "page": d.page, "ocr": d.page in ocr_pages}
    return act, sections, extras
