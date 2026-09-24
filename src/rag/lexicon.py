"""Legal synonyms and query classification.

Two cheap, deterministic wins that sit in front of retrieval:

SYNONYMS — people and statutes use different words for the same thing
(উচ্ছেদ / eviction / বেদখল). Adding the counterparts to the search query costs
nothing at query time and bridges a gap no embedding model was trained for in
this language pair.

CLASSIFICATION — "ধারা ৩০২ কী বলে?" and "ভাড়াটিয়াকে উচ্ছেদ করা যায় কীভাবে?" want
different retrieval. The first is a lookup and belongs to BM25; the second is
conceptual and belongs to the embedder. Routing by query shape is a bigger,
cheaper win than tuning either side.
"""
from __future__ import annotations

import re

from ingest.textutils import nfc

from .lexical import BN_SUFFIXES
from .query import SECTION_REF

# One entry per concept; every term in a group expands to the others.
SYNONYM_GROUPS: list[list[str]] = [
    ["উচ্ছেদ", "বেদখল", "eviction", "evict"],
    ["ভাড়া", "rent", "ভাড়াটিয়া", "tenant"],
    ["শাস্তি", "দণ্ড", "punishment", "penalty"],
    ["জরিমানা", "fine", "অর্থদণ্ড"],
    ["কারাদণ্ড", "imprisonment", "জেল"],
    ["হত্যা", "খুন", "murder", "homicide"],
    ["অবহেলা", "negligence", "negligent"],
    ["চুক্তি", "contract", "agreement"],
    ["নিবন্ধন", "registration", "register", "নথিভুক্ত"],
    ["নোটিশ", "notice", "বিজ্ঞপ্তি"],
    ["আবেদন", "application", "দরখাস্ত"],
    ["কর্মচারী", "employee", "শ্রমিক", "worker"],
    ["মালিক", "employer", "owner", "নিয়োগকর্তা"],
    ["বীমা", "insurance", "বীমাকারী", "insurer"],
    ["সংজ্ঞা", "definition", "means", "অর্থ"],
    ["আদালত", "court", "ট্রাইব্যুনাল", "tribunal"],
    ["অপরাধ", "offence", "offense", "crime"],
    ["ক্ষতিপূরণ", "compensation", "damages"],
    ["উত্তরাধিকার", "inheritance", "succession"],
    ["ছুটি", "leave", "holiday"],
]

_INDEX: dict[str, set[str]] = {}
for _group in SYNONYM_GROUPS:
    for _term in _group:
        _INDEX.setdefault(nfc(_term.lower()), set()).update(nfc(t) for t in _group)

_WORD = re.compile(r"[\wঀ-৿]+", re.UNICODE)
COMPARATIVE = re.compile(nfc(r"পার্থক্য|তুলনা|difference|compare|versus|\bvs\b"), re.IGNORECASE)


def _stem_candidates(word: str) -> set[str]:
    return {word[: -len(suf)] for suf in BN_SUFFIXES
            if word.endswith(suf) and len(word) - len(suf) >= 3}


def expand_synonyms(question: str, max_added: int = 6) -> str:
    """Append the counterparts of any known legal term in the question."""
    raw = {nfc(w.lower()) for w in _WORD.findall(question)}
    # Try every suffix strip, not just the first match: the crude stemmer turns
    # "উচ্ছেদের" into "উচ্ছে" (it strips the plural "দের"), so a single stem
    # would miss the "উচ্ছেদ" group. Generating candidates costs nothing.
    present = raw | {c for w in raw for c in _stem_candidates(w)}
    extras: list[str] = []
    for word in present:
        for alt in sorted(_INDEX.get(word, ())):
            if nfc(alt.lower()) not in present and alt not in extras:
                extras.append(alt)
    return f"{question} {' '.join(extras[:max_added])}".strip() if extras else question


def classify(question: str) -> str:
    """'exact_ref' | 'comparative' | 'conceptual' — used to pick retrieval weights."""
    if SECTION_REF.search(question):
        return "exact_ref"
    if COMPARATIVE.search(question):
        return "comparative"
    return "conceptual"


# Weight profiles per query type: lexical matching wins on lookups, dense
# retrieval wins on paraphrase. Starting points — tune them on a held-out split.
ROUTE_WEIGHTS = {
    "exact_ref": {"dense_weight": 0.6, "bm25_weight": 1.6},
    "comparative": {"dense_weight": 1.0, "bm25_weight": 1.0},
    "conceptual": {"dense_weight": 1.3, "bm25_weight": 0.8},
}
