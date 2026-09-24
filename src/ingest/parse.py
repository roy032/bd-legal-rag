"""HTML -> structured data for bdlaws.minlaw.gov.bd.

Page types (observed on the live site):
  index   : /laws-of-bangladesh-chronological-index.html  -> links to /act-{id}.html
  act     : /act-{id}.html  -> title (h3), act number (h4), date (.publish-date),
            an optional repeal notice (section.bt-act-repealed), the long title and
            preamble (.lineremove), then the table of contents (section.search-here):
            .act-part-group / .act-chapter-group / .act-section-head headings and
            p.act-section-name links to /act-{id}/section-{sid}.html
  section : /act-{id}/section-{sid}.html -> .txt-head (section title),
            .txt-details (the operative text), .footnoteListAll (amendment notes)

The site's own markup is used first because it is exact: the body of a section is
one element, footnote markers are <span class="footnote">, and amendment notes
are list items. Every page also carries a nav bar with ~60 volume links, the
act header, and a copyright footer — a generic "text of the page" approach picks
all of that up, which is exactly what the first version of this parser did.

When those classes are missing (a layout change, or the synthetic fixtures in
tests/), a structure-agnostic fallback based on URL patterns and document order
takes over, so a redesign degrades quality instead of emptying the corpus.
"""
from __future__ import annotations

import copy
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .fetch import BASE_URL
from .models import Act, ActRef, Section, SectionRef
from .textutils import (
    bn_to_ascii_digits,
    detect_lang,
    extract_year,
    fix_legacy_bangla,
    nfc,
    normalize,
)

ACT_HREF = re.compile(r"/act-(\d+)\.html(?:\?.*)?$")
SECTION_HREF = re.compile(r"/act-(\d+)/section-(\d+)\.html(?:\?.*)?$")

# "CHAPTER I - PRELIMINARY", "PART II", "প্রথম অধ্যায় - প্রারম্ভিক", "দ্বিতীয় পরিচ্ছেদ", "তৃতীয় ভাগ"
CHAPTER_RE = re.compile(nfc(
    r"^(?:(?:CHAPTER|Chapter|PART|Part)\s+[IVXLCDM\d]+[A-Z]?"
    r"|\S+\s+(?:অধ্যায়|পরিচ্ছেদ|ভাগ|খণ্ড|খন্ড)(?=$|\s|[-–—:]))"
))
# "১৷ সংক্ষিপ্ত শিরোনাম", "25A. Punishment", "2. Definitions.-", "৫ক৷ ..."
SECTION_LABEL_RE = re.compile(r"^\s*([0-9০-৯]{1,3}[A-Za-zক-হ]{0,3})\s*[।৷.:)\-–]\s*(.*)$", re.S)
TOC_MARKERS = {nfc(x) for x in {"সূচি", "সূচী", "ধারাসমূহ", "sections", "contents", "index"}}
REPEALED_RE = re.compile(nfc(r"রহিত\s*করা\s*হইয়াছে|রহিত\s*হইয়াছে|\bRepealed\b"), re.I)
OMITTED_RE = re.compile(nfc(r"^\s*(?:[0-9০-৯]+[A-Za-zক-হ]{0,2}\s*[।৷.:]\s*)?\[?\s*"
                            r"(?:Repealed|Omitted|বিলুপ্ত|রহিত)\b.{0,200}$"), re.I | re.S)
# "[***]", "6A. [***]", "[[* * *]]" — the site's placeholder for text that was removed
STARS_ONLY_RE = re.compile(r"^\s*(?:[0-9০-৯]+[A-Za-zক-হ]{0,2}\s*[।৷.:]\s*)?[\[\]\s]*\*[\s*\[\]]*$")
OMITTED_TITLE_RE = re.compile(nfc(r"^\[?\s*(?:\*[\s*]*|repealed|omitted|repeal|বিলুপ্ত|রহিত)\s*\.?\s*\]?\.?$"), re.I)


def is_omitted(text: str, title: str = "") -> bool:
    """True for sections the site shows only as removed: empty, '[***]', 'Omitted.'…"""
    t = text.strip()
    return (not t or bool(OMITTED_RE.match(t)) or bool(STARS_ONLY_RE.match(t))
            or bool(OMITTED_TITLE_RE.match(title.strip())))
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
# Decorative glyphs the site sprinkles into preambles ("♣WHEREAS").
DECORATION = re.compile(r"[♣♠♦♥•]")
BLOCK_TAGS = ("p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol")


def _abs(href: str) -> str:
    return href if href.startswith("http") else BASE_URL + "/" + href.lstrip("/")


def _clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "iframe", "button", "select", "svg"]):
        t.decompose()
    return soup


def _clean_text(text: str) -> str:
    return normalize(fix_legacy_bangla(DECORATION.sub("", text)))


def _block_text(tag: Tag | None, drop_markers: bool = True) -> str:
    """Visible text of one element, with block boundaries as line breaks and
    inline footnote markers (<span class="footnote"><sup>2</sup></span>) removed."""
    if tag is None:
        return ""
    tag = copy.copy(tag)
    if drop_markers:
        for t in tag.select("span.footnote, sup"):
            t.decompose()
    for t in tag.find_all(BLOCK_TAGS):
        t.insert_before("\n")
        t.insert_after("\n")
    return _clean_text(tag.get_text(""))


def _inline(tag: Tag | None) -> str:
    """Single-line text (titles, headings)."""
    return re.sub(r"\s+", " ", _block_text(tag)).strip()


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

# Irregular labels of omitted sections in the site's contents list:
#   "৩২ ক। [বিলুপ্ত]" (space before the letter), "২০।ক [বিলুপ্ত]" (letter after the
#   full stop), "৫৮ক  [বিলুপ্ত]" (no full stop). Without these the section inherited
#   the previous number, and "ধারা ৫৮" could resolve to the omitted ৫৮ক.
_LABEL_FIXES = [
    (re.compile(r"^([0-9০-৯]+)\s+([A-Zক-হ]{1,2})\s*([।৷.:])"), r"\1\2\3"),
    (re.compile(r"^([0-9০-৯]+)[।৷.]([ক-হ]{1,2})\s+(?=\[)"), r"\1\2। "),
    (re.compile(r"^([0-9০-৯]+[A-Za-zক-হ]{0,2})\s+(?=\[)"), r"\1। "),
]


# Contents-list entries only (never section bodies, where "5 persons" is text):
#   "[7A. The main functions" (amendment bracket first), "9 and 10. [Repealed]"
#   (a range: keep the first number), "125A Crossing a cheque" (no full stop).
_TOC_LABEL_FIXES = [
    (re.compile(r"^\[\s*([0-9০-৯]+[A-Za-zক-হ]{0,2})\s*([।৷.])"), r"\1\2 "),
    (re.compile(r"^([0-9]{1,3}[A-Z]{0,3})\s*(?:and|to|,|-|–)\s*[0-9]+[A-Z]{0,3}\s*[.:]?\s*"), r"\1. "),
    # 1-3 digits only: a 4-digit start is a year ("১৯৯১ সনের ... সংশোধন"), not a number
    (re.compile(r"^([0-9]{1,3}[A-Z]{0,3})\s+(?=[A-Z][a-z])"), r"\1. "),
    (re.compile(r"^([০-৯]{1,3}[ক-হ]{0,3})\s+(?=[ঀ-৿])"), r"\1। "),
    (re.compile(r"^([0-9০-৯]{1,3}[A-Za-zক-হ]{0,3})\s*[.।]?\s*$"), r"\1. "),   # a bare number: "4A", "91F"
]


def _parse_section_label(text: str, toc: bool = False) -> tuple[str, str]:
    text = normalize(text)
    for pattern, repl in _LABEL_FIXES + (_TOC_LABEL_FIXES if toc else []):
        text = pattern.sub(repl, text, count=1)
    m = SECTION_LABEL_RE.match(text)
    if not m:
        return "", re.sub(r"\s+", " ", text).strip()
    number, title = m.group(1), m.group(2).strip()
    title = re.sub(r"[।.\s\-–:]+$", "", re.sub(r"\s+", " ", title))
    return number, title


def _join_heading(no: str, name: str) -> str | None:
    no, name = no.strip(), name.strip()
    if no and name:
        return f"{no} - {name}"
    return no or name or None


def _act_header(soup: BeautifulSoup) -> tuple[str, str | None, str | None]:
    """Title, act number and date from the act banner."""
    banner = soup.find("section", class_="bg-act-section")
    h3 = banner.find("h3") if banner else None
    h4 = banner.find("h4") if banner else None
    title = _inline(h3)
    number = _inline(h4).strip("() ").strip() or None
    if number:
        number = re.sub(r"\s+", " ", number)
    date_tag = soup.find(class_="publish-date")
    date = None
    if date_tag:
        date = _inline(date_tag).strip("[] ").strip() or None
    return title, number, date


def _toc(soup: BeautifulSoup, act_id: int) -> list[SectionRef]:
    toc = soup.find("section", class_="search-here")
    if toc is None:
        return []
    refs: list[SectionRef] = []
    part = chapter = heading = None
    last_number = ""
    for node in toc.find_all(True):
        classes = node.get("class") or []
        if "act-part-group" in classes:
            part = _join_heading(_inline(node.find(class_="act-part-no")),
                                 _inline(node.find(class_="act-part-name")))
            chapter = heading = None
        elif "act-chapter-group" in classes:
            chapter = _join_heading(_inline(node.find(class_="act-chapter-no")),
                                    _inline(node.find(class_="act-chapter-name")))
            heading = None
        elif "act-section-head" in classes:
            heading = _inline(node) or None
        elif node.name == "a" and isinstance(node.get("href"), str):
            m = SECTION_HREF.search(node["href"])
            if not m or int(m.group(1)) != act_id:
                continue
            sid = int(m.group(2))
            if any(r.section_id == sid for r in refs):
                continue
            number, title = _parse_section_label(_block_text(node), toc=True)
            inherited = False
            if not number and last_number and title.lower() not in ("preamble", "প্রস্তাবনা"):
                number, inherited = last_number, True
            if number and not inherited:
                last_number = number
            refs.append(SectionRef(
                section_id=sid, number=number, number_ascii=bn_to_ascii_digits(number),
                title=title, chapter=chapter, url=_abs(f"act-{act_id}/section-{sid}.html"),
                part=part, heading=heading, inherited_number=inherited))
    return refs


def parse_act(html: str, act_id: int, url: str | None = None) -> Act:
    soup = _clean_soup(html)
    title, act_number, date = _act_header(soup)
    sections = _toc(soup, act_id)
    if not title or not sections:
        return _parse_act_generic(soup, act_id, url)

    notice = soup.find("section", class_="bt-act-repealed")
    repeal_note = _inline(notice) or None if notice else None
    pre = soup.find(class_="lineremove")
    preamble = _block_text(pre) or None
    if preamble:
        preamble = re.sub(r"^\s*Preamble\s*", "", preamble).strip() or None

    lang_text = " ".join([title, preamble or ""] + [s.title for s in sections[:40]])
    return Act(
        act_id=act_id,
        title=title,
        act_number=act_number,
        date=date,
        preamble=preamble,
        year=extract_year(title),
        language=detect_lang(lang_text),
        repealed=repeal_note is not None or soup.find(class_="bn-repealed") is not None,
        url=url or _abs(f"act-{act_id}.html"),
        sections=sections,
        repeal_note=repeal_note,
    )


def _parse_act_generic(soup: BeautifulSoup, act_id: int, url: str | None) -> Act:
    """Structure-agnostic fallback: URL patterns and document order only."""
    body = soup.body or soup
    for t in body.find_all("form"):
        t.unwrap()

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
                number, title = _parse_section_label(node.get_text(" "), toc=True)
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

    lines = [ln for ln in normalize(body.get_text("\n")).splitlines() if ln]
    title_tag = body.find("h3")
    title = normalize(title_tag.get_text(" ")) if title_tag else ""
    if not title and soup.title:
        title = normalize(soup.title.get_text()).split("|")[0].strip()

    act_number = date = None
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
        else:
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

def _act_refs(tags: list[Tag], own_act: int) -> list[dict]:
    """Cross-ACT references: the site links "Companies Act, 1994" to /act-788.html.
    Capturing the id here is what lets the agent follow a reference into another
    statute later; recovering it from the text alone is much harder."""
    refs: list[dict] = []
    for tag in tags:
        for a in tag.find_all("a", href=True):
            href = a.get("href")
            if not isinstance(href, str):
                continue
            m = ACT_HREF.search(href)
            title = _inline(a)
            if m and int(m.group(1)) != own_act and title:
                entry = {"act_id": int(m.group(1)), "title": title}
                if entry not in refs:
                    refs.append(entry)
    return refs


def _marker_numbers(tag: Tag) -> set[str]:
    """Footnote numbers referenced from inside this element."""
    nums = (bn_to_ascii_digits(s.get_text("", strip=True)) for s in tag.select("span.footnote sup"))
    return {n for n in nums if n}


def parse_section(html: str, ref: SectionRef, act: Act) -> Section:
    soup = _clean_soup(html)
    details = soup.find(class_="txt-details")
    if details is None:
        return _parse_section_generic(soup, ref, act)

    text = _block_text(details)
    head = soup.find(class_="txt-head")
    title = ref.title or _inline(head)

    # Page-level context, used when the table of contents did not carry it.
    chapter = ref.chapter
    if chapter is None and (grp := soup.find(class_="act-chapter-group")):
        chapter = _join_heading(_inline(grp.find(class_="act-chapter-no")),
                                _inline(grp.find(class_="act-chapter-name")))
    part = ref.part
    if part is None and (grp := soup.find(class_="act-part-group")):
        part = _join_heading(_inline(grp.find(class_="act-part-no")),
                             _inline(grp.find(class_="act-part-name")))

    # Amendment notes: keep only the ones this section's text points at. Note 1 on
    # most pages belongs to the act title ("Throughout this Act ... substituted")
    # and would otherwise mark every section as amended.
    used = _marker_numbers(details) | (_marker_numbers(head) if head else set())
    footnotes: list[str] = []
    note_tags: list[Tag] = []
    for li in soup.select(".footnoteListAll li"):
        num_tag = li.find(["h6", "sup"])
        num = bn_to_ascii_digits(num_tag.get_text("", strip=True)) if num_tag else ""
        if num_tag:
            num_tag.decompose()
        note = _inline(li)
        if note and num in used:
            footnotes.append(f"{num}. {note}" if num else note)
            note_tags.append(li)

    omitted = is_omitted(text, title)
    return Section(
        act_id=act.act_id,
        section_id=ref.section_id,
        number=ref.number,
        number_ascii=ref.number_ascii,
        title=title,
        chapter=chapter,
        text=text,
        footnotes=footnotes,
        url=ref.url,
        act_refs=_act_refs([details, *note_tags], act.act_id),
        part=part,
        heading=ref.heading,
        omitted=omitted,
    )


def _nonlink_len(tag: Tag) -> int:
    total = len(tag.get_text(" ", strip=True))
    links = sum(len(a.get_text(" ", strip=True)) for a in tag.find_all("a"))
    return max(total - links, 0)


def _main_block(soup: BeautifulSoup) -> Tag:
    """Tightest container that still holds >= 80% of the page's non-link text."""
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


def _parse_section_generic(soup: BeautifulSoup, ref: SectionRef, act: Act) -> Section:
    block = _main_block(soup)
    act_refs = _act_refs([block], act.act_id)
    lines = list(normalize(block.get_text("\n")).splitlines())

    act_title_variants = {act.title, f"[{act.title}]", f"[ {act.title} ]"}
    cleaned: list[str] = []
    for ln in lines:
        low = ln.strip().lower()
        if low in BOILERPLATE_LINES or ln.strip() in act_title_variants:
            continue
        cleaned.append(ln)

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and cleaned[0].strip():
        n, t = _parse_section_label(cleaned[0])
        if (n and bn_to_ascii_digits(n) == ref.number_ascii and len(cleaned[0]) < 300 and
                (not t or t in ref.title or ref.title in t)) or ref.title and cleaned[0].strip().rstrip("।.") == ref.title:
            cleaned.pop(0)
        else:
            break

    footnotes: list[str] = []
    while cleaned and (not cleaned[-1].strip() or FOOTNOTE_RE.match(cleaned[-1].strip())):
        ln = cleaned.pop().strip()
        if ln:
            footnotes.insert(0, ln)

    text = normalize("\n".join(cleaned))
    return Section(
        act_id=act.act_id,
        section_id=ref.section_id,
        number=ref.number,
        number_ascii=ref.number_ascii,
        title=ref.title,
        chapter=ref.chapter,
        text=text,
        footnotes=footnotes,
        url=ref.url,
        act_refs=act_refs,
        part=ref.part,
        heading=ref.heading,
        omitted=is_omitted(text),
    )
