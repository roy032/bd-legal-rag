"""Law beyond the Acts: rules, regulations, SROs, orders and court judgments.

bdlaws publishes the Acts and Ordinances. Much of what people actually need sits
below them: the rules an act lets the government make (the fee, the form, the
deadline), SROs in the Bangladesh Gazette, and the Supreme Court's reading of a
provision. These come as PDFs from other official sites, so they are listed in a
manifest, one JSON object per line, in data/sources/manifest.jsonl:

  {"id": "hcd-fa-311-2016", "kind": "judgment", "title": "...",
   "url": "https://supremecourt.gov.bd/resources/documents/....pdf",
   "division": "HCD", "case_number": "First Appeal No. 311 of 2016", "parties": "...",
   "date": "2026-08-25"}
  {"id": "consumer-rules-2021", "kind": "rule", "title": "ভোক্তা-অধিকার সংরক্ষণ বিধিমালা, ২০২১",
   "url": "https://www.dpp.gov.bd/....pdf", "parent_act": "ভোক্তা-অধিকার সংরক্ষণ আইন, ২০০৯",
   "citation": "এস.আর.ও. নং ...", "date": "2021-..."}

Only official hosts are accepted (OFFICIAL_HOSTS): the point of the corpus is
that every citation leads to the government's own copy. `bdrag sources` fetches,
ingests and lists them; see that command's help.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import zlib
from pathlib import Path
from urllib.parse import urljoin, urlparse

KINDS = ("rule", "regulation", "sro", "order", "judgment")
KIND_LABELS = {
    "act": ("আইন", "Act"),
    "rule": ("বিধিমালা", "Rules"),
    "regulation": ("প্রবিধানমালা", "Regulations"),
    "sro": ("প্রজ্ঞাপন (এসআরও)", "SRO / notification"),
    "order": ("আদেশ", "Order"),
    "judgment": ("রায়", "Judgment"),
}
# Government sites only. A Scribd copy or a law firm's blog post may be easier to
# find, but a citation to it proves nothing.
OFFICIAL_HOSTS = (
    "bdlaws.minlaw.gov.bd", "supremecourt.gov.bd", "www.supremecourt.gov.bd",
    "dpp.gov.bd", "www.dpp.gov.bd", "legislativediv.gov.bd", "minlaw.gov.bd",
    "nbr.gov.bd", "www.nbr.gov.bd", "bangladesh.gov.bd",
)
SOURCE_ID_BASE = 950_000       # synthetic act ids; PDFs from `bdrag pdf` use 900_000
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,80}$")


def official(url: str) -> bool:
    """True for https/http URLs on a government host (any *.gov.bd ministry portal too)."""
    u = urlparse(url or "")
    host = (u.hostname or "").lower()
    return u.scheme in ("http", "https") and (host in OFFICIAL_HOSTS or host.endswith(".gov.bd"))


def source_act_id(source_id: str) -> int:
    return SOURCE_ID_BASE + zlib.crc32(source_id.encode()) % 49_999


def validate(entry: dict) -> list[str]:
    """Problems with one manifest entry; [] when it can be fetched and ingested."""
    errs = []
    if not _ID.match(str(entry.get("id") or "")):
        errs.append("id: lowercase letters, digits, '.', '_' or '-' (3-80 chars)")
    if entry.get("kind") not in KINDS:
        errs.append(f"kind: one of {', '.join(KINDS)}")
    if not entry.get("title"):
        errs.append("title: required")
    if not entry.get("url") and not entry.get("file"):
        errs.append("url (or a local file): required")
    elif entry.get("url") and not official(entry["url"]):
        errs.append(f"url: not an official government host ({urlparse(entry['url']).hostname})")
    return errs


def load_manifest(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            raise ValueError(f"{p}:{n}: not JSON ({e})") from e
        row["_line"] = n
        rows.append(row)
    seen: dict[str, int] = {}
    ids: dict[int, str] = {}
    for row in rows:
        sid = str(row.get("id"))
        if sid in seen:
            raise ValueError(f"{p}:{row['_line']}: id '{sid}' repeats line {seen[sid]}")
        seen[sid] = row["_line"]
        aid = source_act_id(sid)
        if aid in ids:
            raise ValueError(f"{p}:{row['_line']}: id '{sid}' hashes like '{ids[aid]}'; rename one")
        ids[aid] = sid
    return rows


def append_manifest(path: str | Path, entries: list[dict]) -> int:
    """Add entries whose url is not in the manifest yet. Returns how many were added."""
    p = Path(path)
    have = {r.get("url") for r in load_manifest(p)}
    new = [e for e in entries if e.get("url") not in have]
    if new:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            for e in new:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return len(new)


def local_path(entry: dict, raw_dir: str | Path = "data/raw/sources") -> Path:
    if entry.get("file"):
        return Path(entry["file"])
    suffix = Path(urlparse(entry["url"]).path).suffix.lower() or ".pdf"
    return Path(raw_dir) / f"{entry['id']}{suffix}"


# --- Supreme Court judgment lists ------------------------------------------------

SC_BASE = "https://supremecourt.gov.bd/web/"
SC_LIST = SC_BASE + "?page=judgments.php&menu=00&div_id={div}&lang="
DIVISIONS = {"AD": 1, "HCD": 2}

_ROW = re.compile(r'<tr class="font_e_12".*?</tr>', re.S)
_TD = re.compile(r"<td.*?</td>", re.S)
_PDF = re.compile(r'href="([^"]*resources/documents/[^"]+\.pdf)"', re.I)
_UPLOADED = re.compile(r"Uploaded on\s*:\s*(\d{1,2})-([A-Z]{3})-(\d{2})", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}


def _text(fragment: str) -> str:
    return " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def parse_sc_list(page_html: str, division: str) -> list[dict]:
    """Manifest entries from one judgments.php page of supremecourt.gov.bd.

    Each row: case number (+ "Uploaded on"), parties, short description, and a link
    to the judgment PDF under /resources/documents/.
    """
    out = []
    for row in _ROW.findall(page_html):
        cells = [_text(td) for td in _TD.findall(row)]
        links = _PDF.findall(row)
        if len(cells) < 3 or not links:
            continue
        url = urljoin(SC_BASE, links[0])
        # "First Appeal (TN) 311/2016 (First Appeal (TN) 311/2016) অনুবাদ (Google) Uploaded on : ..."
        case = re.split(r"\s*অনুবাদ|\s*Uploaded on", cells[1])[0].strip()
        if m := re.match(r"^(.+?)\s*\(\1\)$", case):
            case = m.group(1)
        if not case:
            continue
        uploaded = None
        if m := _UPLOADED.search(cells[1]):
            d, mon, yy = m.groups()
            uploaded = f"20{yy}-{_MONTHS.get(mon.upper(), 1):02d}-{int(d):02d}"
        stem = Path(urlparse(url).path).stem
        out.append({
            "id": f"{division.lower()}-{_slug(case) or _slug(stem)}-{zlib.crc32(url.encode()) % 10_000:04d}",
            "kind": "judgment", "title": f"{case} ({division})", "url": url,
            # The list has typos ("311/20116"); the cause title in the PDF is read for
            # the case number at ingest, and this is only the fallback title.
            "division": division, "listed_as": case, "parties": cells[2],
            "summary": cells[3] if len(cells) > 3 and cells[3] not in (".", "") else None,
            "uploaded": uploaded,
        })
    return out
