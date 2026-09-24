"""Romanised Bangla ("Banglish") input.

Real people type `dhara 302 e ki ache`, `bhara briddhi`, `ain`. Both halves of
the retrieval stack are blind to it: the embedding model sees Latin script and
lands near English text, and BM25 matches no Bangla token at all. So a query
that looks romanised gets a Bangla variant generated and searched alongside the
original.

Two layers, because neither alone is enough:
  1. a lexicon of the words that actually appear in these questions — exact and
     safe;
  2. a phonetic fallback for everything else, applied only when the query
     already looks romanised, so ordinary English is never mangled.

This is the piece of the system that is specific to where it is used, and it is
worth measuring separately: report recall on a romanised slice of your
evaluation set.
"""
from __future__ import annotations

import re

# Words that carry the meaning of a legal question. Extend this from your own
# query logs — that is where the real vocabulary comes from.
LEXICON: dict[str, str] = {
    # structure
    "dhara": "ধারা", "dhaara": "ধারা", "upodhara": "উপ-ধারা", "ain": "আইন", "aain": "আইন",
    "bidhi": "বিধি", "adhyay": "অধ্যায়", "tofsil": "তফসিল", "ordinance": "অধ্যাদেশ",
    # question words
    "ki": "কী", "kee": "কী", "kono": "কোন", "kothay": "কোথায়", "kobe": "কবে", "keno": "কেন",
    "kivabe": "কীভাবে", "kibhabe": "কীভাবে", "kto": "কত", "koto": "কত", "kotodin": "কত দিন",
    "ache": "আছে", "bole": "বলে", "hoy": "হয়", "hobe": "হবে", "korte": "করতে", "kora": "করা",
    "jonno": "জন্য", "songjha": "সংজ্ঞা", "songgya": "সংজ্ঞা",
    # common subjects
    "shasti": "শাস্তি", "sasti": "শাস্তি", "danda": "দণ্ড", "jorimana": "জরিমানা",
    "bhara": "ভাড়া", "vara": "ভাড়া", "barirmalik": "বাড়িওয়ালা", "malik": "মালিক",
    "bharatiya": "ভাড়াটিয়া", "bhatatiya": "ভাড়াটিয়া", "uchched": "উচ্ছেদ",
    "chukti": "চুক্তি", "notish": "নোটিশ", "notice": "নোটিশ", "abedon": "আবেদন",
    "nibondhon": "নিবন্ধন", "registration": "নিবন্ধন", "bima": "বীমা", "polisi": "পলিসি",
    "chakri": "চাকরি", "sromik": "শ্রমিক", "kormochari": "কর্মচারী", "beton": "বেতন",
    "hottya": "হত্যা", "khun": "খুন", "chuti": "ছুটি", "adalot": "আদালত", "mamla": "মামলা",
    "odhikar": "অধিকার", "obohela": "অবহেলা", "mrittu": "মৃত্যু", "somoy": "সময়",
}

# Longest first so digraphs win over single letters.
_PHONETIC: list[tuple[str, str]] = [
    ("kkh", "ক্ষ"), ("chh", "ছ"), ("bh", "ভ"), ("ch", "চ"), ("dh", "ধ"), ("gh", "ঘ"),
    ("jh", "ঝ"), ("kh", "খ"), ("ph", "ফ"), ("sh", "শ"), ("th", "থ"), ("ng", "ং"),
    ("aa", "া"), ("ee", "ী"), ("oo", "ু"), ("ou", "ৌ"), ("oi", "ৈ"),
    ("a", "া"), ("i", "ি"), ("u", "ু"), ("e", "ে"), ("o", "ো"),
    ("b", "ব"), ("c", "ক"), ("d", "দ"), ("f", "ফ"), ("g", "গ"), ("h", "হ"), ("j", "জ"),
    ("k", "ক"), ("l", "ল"), ("m", "ম"), ("n", "ন"), ("p", "প"), ("q", "ক"), ("r", "র"),
    ("s", "স"), ("t", "ত"), ("v", "ভ"), ("w", "ও"), ("x", "ক্স"), ("y", "য়"), ("z", "জ"),
]

_LATIN_TOKEN = re.compile(r"[a-z]+", re.IGNORECASE)
# Words that mean the query is ordinary English, not romanised Bangla.
ENGLISH_MARKERS = {
    "what", "which", "who", "when", "where", "why", "how", "is", "are", "the", "of", "for",
    "section", "act", "law", "punishment", "does", "do", "can", "must", "shall", "under",
    "penalty", "fine", "court", "notice", "rent", "tenant", "employer", "contract", "insurance",
}


def looks_romanised(question: str) -> bool:
    """True when the Latin words look like Bangla rather than English."""
    tokens = [t.lower() for t in _LATIN_TOKEN.findall(question)]
    if not tokens:
        return False
    english = sum(t in ENGLISH_MARKERS for t in tokens)
    bangla = sum(t in LEXICON for t in tokens)
    if english and english >= bangla:
        return False
    return bangla > 0


def _phonetic(token: str) -> str:
    out, i = [], 0
    low = token.lower()
    while i < len(low):
        for src, dst in _PHONETIC:
            if low.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            out.append(low[i])
            i += 1
    return "".join(out)


def transliterate(question: str, phonetic_fallback: bool = True) -> str:
    """Romanised Bangla -> Bangla. Digits and unknown English words pass through."""
    def convert(match: re.Match) -> str:
        token = match.group(0)
        low = token.lower()
        if low in LEXICON:
            return LEXICON[low]
        if low in ENGLISH_MARKERS or not phonetic_fallback:
            return token
        return _phonetic(token)

    return _LATIN_TOKEN.sub(convert, question)


def maybe_variant(question: str, phonetic: bool = False) -> str | None:
    """The Bangla search variant of a romanised query, or None if not romanised.

    The phonetic fallback is OFF by default and that is a measured decision, not
    timidity: rule-based romanisation without inherent-vowel and conjunct
    handling produces tokens like "বরিদধির" for "briddhir", which match nothing
    and add noise to the dense query. The lexicon substitution alone is exact.
    Turn the fallback on, run the romanised slice of your evaluation set, and
    keep it only if the numbers improve — a proper transliteration library
    (indic-transliteration, or a learned model) is the real fix.
    """
    if not looks_romanised(question):
        return None
    variant = transliterate(question, phonetic_fallback=phonetic)
    return variant if variant != question else None
