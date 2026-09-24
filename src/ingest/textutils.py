"""Small text helpers for mixed Bangla/English legal text."""
from __future__ import annotations

import re
import unicodedata

BN_DIGITS = "০১২৩৪৫৬৭৮৯"
_BN_TO_ASCII = str.maketrans(BN_DIGITS, "0123456789")

# Bangla Unicode block
_BN_CHAR = re.compile(r"[ঀ-৿]")
_LATIN_CHAR = re.compile(r"[A-Za-z]")


def nfc(s: str) -> str:
    """Canonical Unicode form. Bangla has two encodings of য় (and ড়, ঢ়):
    one precomposed code point, or the base letter + nukta. NFC always yields
    the second, so normalize both the text *and* your regex patterns."""
    return unicodedata.normalize("NFC", s)


def bn_to_ascii_digits(s: str) -> str:
    """'ধারা ২৫' -> 'ধারা 25'."""
    return s.translate(_BN_TO_ASCII)


def detect_lang(text: str) -> str:
    """Return 'bn', 'en', or 'mixed' by script ratio.

    Most pre-1987 laws are in English, most later ones in Bangla, so this is
    per-document metadata you will filter and evaluate on later.
    """
    bn = len(_BN_CHAR.findall(text))
    en = len(_LATIN_CHAR.findall(text))
    total = bn + en
    if total == 0:
        return "unknown"
    ratio = bn / total
    if ratio > 0.7:
        return "bn"
    if ratio < 0.3:
        return "en"
    return "mixed"


def normalize(text: str) -> str:
    """Unicode-normalize and tidy whitespace, keeping paragraph breaks."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace(" ", " ").replace("‌", "").replace("​", "")
    # The site uses both '।' (dari) and '৷' (Bangla isshar-like) as full stop.
    text = text.replace("৷", "।")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if not ln:
            if not blank and out:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


_YEAR = re.compile(r"(1[6-9]\d\d|20\d\d)")


def extract_year(title: str) -> int | None:
    """Pull the enactment year from a title like 'বীমা আইন, ২০১০' or 'The Penal Code, 1860'."""
    years = _YEAR.findall(bn_to_ascii_digits(title))
    return int(years[-1]) if years else None


# "section 25", "sections 3 and 4", "ধারা ২৫", "ধারা ২৫ এর উপ-ধারা (২)"
_XREF = re.compile(nfc(r"(?:\bsections?|ধারা(?:র)?)\s+([0-9০-৯]+[A-Za-z]?)"), re.IGNORECASE)


def extract_section_refs(text: str) -> list[str]:
    """Cross-references to other sections — used for multi-hop retrieval in Phase 6."""
    refs = {bn_to_ascii_digits(m) for m in _XREF.findall(text)}
    return sorted(refs, key=lambda r: (int(re.sub(r"\D", "", r) or 0), r))
