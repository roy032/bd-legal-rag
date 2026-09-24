"""HTML -> structured data for bdlaws.minlaw.gov.bd.

Page types (observed on the live site):
  index   : /laws-of-bangladesh-chronological-index.html  -> links to /act-{id}.html
  act     : /act-{id}.html  -> title (h3), act number (h4), date "[ ... ]",
            preamble, then a table of contents: chapter headings as plain text,
            sections as links to /act-{id}/section-{sid}.html
  section : /act-{id}/section-{sid}.html -> the section body

The parser relies on URL patterns and document order rather than CSS class
names, so it survives cosmetic changes to the site. If the site changes
structurally, run with --save-raw and look at data/raw/ to adjust.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .fetch import BASE_URL
from .models import Act, ActRef, Section, SectionRef
from .textutils import bn_to_ascii_digits, detect_lang, extract_year, nfc, normalize

ACT_HREF = re.compile(r"/act-(\d+)\.html(?:\?.*)?$")
SECTION_HREF = re.compile(r"/act-(\d+)/section-(\d+)\.html(?:\?.*)?$")

# "CHAPTER I - PRELIMINARY", "PART II", "প্রথম অধ্যায় - প্রারম্ভিক", "দ্বিতীয় পরিচ্ছেদ", "তৃতীয় ভাগ"
CHAPTER_RE = re.compile(nfc(
    r"^(?:(?:CHAPTER|Chapter|PART|Part)\s+[IVXLCDM\d]+[A-Z]?"
    r"|\S+\s+(?:অধ্যায়|পরিচ্ছেদ|ভাগ|খণ্ড|খন্ড)(?=$|\s|[-–—:]))"
))
# "১৷ সংক্ষিপ্ত শিরোনাম", "25A. Punishment", "2. Definitions.-"
SECTION_LABEL_RE = re.compile(r"^\s*([0-9০-৯]+[A-Za-zক-হ]{0,2})\s*[।৷.:)\-–]\s*(.*)$", re.S)
TOC_MARKERS = {nfc(x) for x in {"সূচি", "সূচী", "ধারাসমূহ", "sections", "contents", "index"}}
REPEALED_RE = re.compile(nfc(r"রহিত\s*করা\s*হইয়াছে|রহিত\s*হইয়াছে|\bRepealed\b"), re.I)
DATE_RE = re.compile(r"^\[\s*(.{4,60}?)\s*\]$")
FOOTNOTE_RE = re.compile(nfc(
    r"^[0-9০-৯]+\s*[\S].*(প্রতিস্থাপিত|সন্নিবেশিত|বিলুপ্ত|সংযোজিত|রহিত|"
    r"substituted|inserted|omitted|added|repealed|amended)"),
    re.I,
)
BOILERPLATE_LINES = {nfc(x) for x in {
    "বাংলা", "english", "|", "প্রিন্টেবল ভার্সন", "printable version", "print",
    "সূচি", "সূচী", "home", "হোম",
}}


def _abs(href: str) -> str:
    return href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")


def _clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "iframe", "form", "button", "select", "svg"]):
        t.decompose()
    return soup


# ---------------------------------------------------------------- index

def parse_index(html: str) -> list[ActRef]:
    soup = _clean_soup(html)
    seen: dict[int, ActRef] = {}
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not isinstance(href, str):
            continue
        m = ACT_HREF.search(href)
        title = normalize(a.get_text(" "))
        if m and title:
            act_id = int(m.group(1))
            seen.setdefault(act_id, ActRef(act_id, title, _abs(f"act-{act_id}.html")))
    return list(seen.values())


# ---------------------------------------------------------------- act page

def _parse_section_label(text: str) -> tuple[str, str]:
    text = normalize(text)
    m = SECTION_LABEL_RE.match(text)
    if not m:
        return "", text
    number, title = m.group(1), m.group(2).strip()
    title = re.sub(r"[।.\s\-–:]+$", "", title)
    return number, title


def parse_act(html: str, act_id: int, url: str | None = None) -> Act:
    soup = _clean_soup(html)
    body = soup.body or soup

    # Walk the document in order: chapter headings are plain text, sections are links.
    sections: list[SectionRef] = []
    chapter: str | None = None
    for node in body.descendants:
        if isinstance(node, Tag) and node.name == "a" and node.get("href"):
            href = node.get("href")
            if not isinstance(href, str):
                continue
            m = SECTION_HREF.search(href)
            if m and int(m.group(1)) == act_id:
                sid = int(m.group(2))
                if any(s.section_id == sid for s in sections):
                    continue
                number, title = _parse_section_label(node.get_text(" "))
                sections.append(
                    SectionRef(
                        section_id=sid,
                        number=number,
                        number_ascii=bn_to_ascii_digits(number),
                        title=title,
                        chapter=chapter,
                        url=_abs(f"act-{act_id}/section-{sid}.html"),
                    )
                )
        elif isinstance(node, NavigableString) and node.find_parent("a") is None:
            text = normalize(str(node))
            if text and len(text) < 200 and CHAPTER_RE.match(text):
                chapter = text

    # Header fields from the text lines above the table of contents.
    lines = [ln for ln in normalize(body.get_text("\n")).splitlines() if ln]
    title_tag = body.find("h3")
    title = normalize(title_tag.get_text(" ")) if title_tag else ""
    if not title and soup.title:
        title = normalize(soup.title.get_text()).split("|")[0].strip()

    act_number = date = preamble = None
    try:
        start = lines.index(title) + 1
    except ValueError:
        start = 0
    header: list[str] = []
    for ln in lines[start:]:
        if ln.strip().lower() in TOC_MARKERS or SECTION_LABEL_RE.match(ln) or CHAPTER_RE.match(ln):
            break
        header.append(ln)
    rest = []
    for ln in header:
        stripped = ln.strip("() ").strip()
        if act_number is None and re.search(r"নং\s*(আইন|অধ্যাদেশ)|\b(ACT|ORDINANCE|ORDER|REGULATION)\s+NO\b", stripped, re.I):
            act_number = stripped
        elif date is None:
            date_match = DATE_RE.match(ln)
            if date_match:
                date = date_match.group(1)
            else:
                rest.append(ln)
        elif date is not None:
            rest.append(ln)
    preamble = " ".join(rest).strip() or None

    head_text = " ".join([title, act_number or "", " ".join(header[:6])])
    return Act(
        act_id=act_id,
        title=title,
        act_number=act_number,
        date=date,
        preamble=preamble,
        year=extract_year(title),
        language=detect_lang(" ".join([title, preamble or ""] + [s.title for s in sections])),
        repealed=bool(REPEALED_RE.search(head_text)),
        url=url or _abs(f"act-{act_id}.html"),
        sections=sections,
    )


# ---------------------------------------------------------------- section page

def _nonlink_len(tag: Tag) -> int:
    total = len(tag.get_text(" ", strip=True))
    links = sum(len(a.get_text(" ", strip=True)) for a in tag.find_all("a"))
    return max(total - links, 0)


def _main_block(soup: BeautifulSoup) -> Tag:
    """Tightest container that still holds >= 80% of the page's non-link text.

    Nav bars and footers are either link-heavy or small, so this lands on the
    content column without needing to know the site's CSS classes.
    """
    body = soup.body or soup
    for t in body.find_all(["nav", "header", "footer"]):
        t.decompose()
    total = _nonlink_len(body)
    if total == 0:
        return body
    best, best_depth = body, 0
    for tag in body.find_all(["div", "section", "article", "main", "td"]):
        if _nonlink_len(tag) >= 0.8 * total:
            depth = len(list(tag.parents))
            if depth > best_depth:
                best, best_depth = tag, depth
    return best


def parse_section(html: str, ref: SectionRef, act: Act) -> Section:
    soup = _clean_soup(html)
    block = _main_block(soup)

    # Cross-ACT references: the site links "Companies Act, 1994" to /act-788.html.
    # Capturing the id here is what lets the agent follow a reference into
    # another statute later; recovering it from the text alone is much harder.
    act_refs: list[dict] = []
    for a in block.find_all("a", href=True):
        href = a.get("href")
        if not isinstance(href, str):
            continue
        m = ACT_HREF.search(href)
        title = normalize(a.get_text(" "))
        if m and int(m.group(1)) != act.act_id and title:
            entry = {"act_id": int(m.group(1)), "title": title}
            if entry not in act_refs:
                act_refs.append(entry)
    lines = list(normalize(block.get_text("\n")).splitlines())

    act_title_variants = {act.title, f"[{act.title}]", f"[ {act.title} ]"}
    cleaned: list[str] = []
    for ln in lines:
        low = ln.strip().lower()
        if low in BOILERPLATE_LINES or ln.strip() in act_title_variants:
            continue
        cleaned.append(ln)

    # Drop the heading line(s) if they just repeat "number. title".
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and cleaned[0].strip():
        n, t = _parse_section_label(cleaned[0])
        if (n and bn_to_ascii_digits(n) == ref.number_ascii and len(cleaned[0]) < 300 and
                (not t or t in ref.title or ref.title in t)) or ref.title and cleaned[0].strip().rstrip("।.") == ref.title:
            cleaned.pop(0)
        else:
            break

    # Amendment footnotes live at the bottom of the page.
    footnotes: list[str] = []
    while cleaned and (not cleaned[-1].strip() or FOOTNOTE_RE.match(cleaned[-1].strip())):
        ln = cleaned.pop().strip()
        if ln:
            footnotes.insert(0, ln)

    return Section(
        act_id=act.act_id,
        section_id=ref.section_id,
        number=ref.number,
        number_ascii=ref.number_ascii,
        title=ref.title,
        chapter=ref.chapter,
        text=normalize("\n".join(cleaned)),
        footnotes=footnotes,
        url=ref.url,
        act_refs=act_refs,
    )
