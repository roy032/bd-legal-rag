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
    # Khanda ta: 'ত্' + ZWJ is the legacy spelling of 'ৎ'. Folding it on both the
    # corpus and the query side is what lets "বলবত্‍" match "বলবৎ".
    text = text.replace("ত্\u200d", "ৎ").replace("ৎ\u200d", "ৎ")
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


# Artefacts of the site's SutonnyMJ -> Unicode conversion. Only patterns that
# never occur in correctly spelled words are listed: a bare 'তিগ' is left alone
# because it is legitimate in ব্যক্তিগত; only 'েতিগ' / 'ংতিগ' are rewritten.
_LEGACY_FIXES = [
    (re.compile("অা"), "আ"),                  # অ + া -> আ (অাইন -> আইন)
    (re.compile("তৃর্"), "র্তৃ"),               # কতৃর্ক -> কর্তৃক
    (re.compile("তর্ৃ"), "র্তৃ"),               # কতর্ৃক -> কর্তৃক
    # ক্ষ was mapped to "ত্মগ" / "তগ" / "তিগ" by the old font converter:
    (re.compile("(?<!আ)ত্ম([েিীা]?)গ"), "ক্ষ\\1"),  # ত্মেগত্রে -> ক্ষেত্রে, ত্মগমতা -> ক্ষমতা (not আত্মগোপন)
    (re.compile("তেগ"), "ক্ষে"),                # তেগত্রে -> ক্ষেত্রে, কর্তৃপতেগর -> কর্তৃপক্ষের
    (re.compile("(?<=[েং])তিগ"), "ক্ষি"),       # পরিপ্রেতিগতে -> পরিপ্রেক্ষিতে (plain তিগ is real: ব্যক্তিগত)
    (re.compile("(?<![্ঀ-৿])তগ(?=[ঀ-৿])"), "ক্ষ"),   # তগতিপূরণ -> ক্ষতিপূরণ (word-initial)
    (re.compile("(?<!্)তগ(?=[া্কর])"), "ক্ষ"),  # সাতগ্য -> সাক্ষ্য, পরীতগা -> পরীক্ষা (not যতগুলি, হস্তগত)
    (re.compile("স্ত্ম"), "স্ত"),               # হস্ত্মান্তর -> হস্তান্তর
    (re.compile("ন্ত্ম"), "ন্ত"),               # স্থানান্ত্মর -> স্থানান্তর
    (re.compile("ল([িীুূে]?)\u00ad"), "ল্ল\\1"),  # উলি<SHY>খিত -> উল্লিখিত
    (re.compile("\u00ad"), ""),               # any other soft hyphen
    (re.compile("ে্য"), "্যে"),                 # vowel sign before য-ফলা: লক্ষে্য -> লক্ষ্যে
    # Stray zero-width joiners: legitimate only next to a virama (র‍্য, ক্‍).
    (re.compile("ব\u200dসর"), "বৎসর"),          # ব<ZWJ>সর -> বৎসর (the ত্ was lost)
    (re.compile("ত\u200d(?=[^ঀ-৿]|$)"), "ৎ"),   # ত<ZWJ> at a word end -> ৎ
    (re.compile("(?<!্)\u200d(?!্)"), ""),
    # Khanda ta last, so it also catches ত্ produced by the fixes above.
    (re.compile("ত্\u200d*(?=[সকপখফশ]|$|[^ঀ-৿\u200d])"), "ৎ"),   # বত্সর -> বৎসর, বত্<ZWJ>সর -> বৎসর
]


def fix_legacy_bangla(text: str) -> str:
    """Repair the handful of mis-encoded conjuncts that bdlaws pages contain."""
    text = unicodedata.normalize("NFC", text)
    for pattern, repl in _LEGACY_FIXES:
        text = pattern.sub(repl, text)
    return text


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
