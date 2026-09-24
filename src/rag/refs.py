"""Resolve explicit references in a question: which act, which section.

"দণ্ডবিধির ধারা ৩০২ কী বলে?" names a statute (by its colloquial Bangla name)
and a section. Similarity search treats both as ordinary words, so with 1,500
acts in the index "ধারা ৩০২" matches section 302 of whichever act happens to
share the most tokens with the question. A lawyer would simply open the Penal
Code at section 302 — this module lets the pipeline do the same:

  act + section  -> the exact chunks are put first (a lookup, not a search)
  section only   -> candidates with that section number are moved up
  act only       -> an extra search restricted to that act is fused in

Everything is deterministic and runs on metadata already in the index.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.textutils import bn_to_ascii_digits, nfc, normalize

from .query import SECTION_REF
from .store import Hit

# Colloquial name -> a phrase that occurs in the official title on bdlaws.
ACT_ALIASES: dict[str, str] = {nfc(k): v for k, v in {
    "দণ্ডবিধি": "penal code", "দন্ডবিধি": "penal code", "penal code": "penal code",
    "ফৌজদারী কার্যবিধি": "code of criminal procedure", "ফৌজদারি কার্যবিধি": "code of criminal procedure",
    "crpc": "code of criminal procedure", "cr.p.c": "code of criminal procedure",
    "দেওয়ানী কার্যবিধি": "code of civil procedure", "দেওয়ানি কার্যবিধি": "code of civil procedure",
    "cpc": "code of civil procedure",
    "সাক্ষ্য আইন": "evidence act", "evidence act": "evidence act",
    "চুক্তি আইন": "contract act", "contract act": "contract act",
    "তামাদি আইন": "limitation act", "limitation act": "limitation act",
    "সম্পত্তি হস্তান্তর আইন": "transfer of property act",
    "সংবিধান": "constitution", "constitution": "constitution",
    "শ্রম আইন": "শ্রম আইন", "labour act": "শ্রম আইন",
}.items()}

_YEAR_TAIL = re.compile(r"[,\s]*[(\[]?\s*[0-9০-৯]{4}\s*[)\]]?\s*$")
_PUNCT = re.compile(r"[^\w\sঀ-৿]")
_AMENDING = re.compile(nfc(r"সংশোধন|amendment|repeal|রহিতকরণ"), re.I)


def _norm(text: str) -> str:
    text = bn_to_ascii_digits(normalize(text).lower())
    text = _PUNCT.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Reference:
    act_ids: list[int] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.act_ids or self.numbers)


class ActResolver:
    """Built once from the index records (the same list BM25/dense already hold)."""

    def __init__(self, records: list[dict], min_title_chars: int = 6) -> None:
        self.titles: dict[int, str] = {}
        self.repealed: dict[int, bool] = {}
        self.by_number: dict[tuple[int, str], list[Hit]] = {}
        for r in records:
            m = r["metadata"]
            aid = m.get("act_id")
            if aid is None:
                continue
            if m.get("act_title"):
                self.titles.setdefault(aid, m["act_title"])
                self.repealed.setdefault(aid, bool(m.get("repealed")))
            num = str(m.get("section_number_ascii") or "")
            if m.get("type") == "section" and num:
                self.by_number.setdefault((aid, num.upper()), []).append(
                    Hit(r["chunk_id"], 0.0, r["text"], r["body"], m))
        # Title stems ("the penal code", "নারী ও শিশু নির্যাতন দমন আইন") for matching.
        # Several acts can share a stem (a Finance Act every year): keep the one in
        # force, most recent first.
        by_stem: dict[str, list[int]] = {}
        for aid, title in self.titles.items():
            stem = _norm(_YEAR_TAIL.sub("", title))
            stem = re.sub(r"^the ", "", stem)
            if len(stem) >= min_title_chars and not _AMENDING.search(stem):
                by_stem.setdefault(stem, []).append(aid)
        self.stems: list[tuple[str, int]] = []
        for stem, ids in by_stem.items():
            ids.sort(key=lambda a: (self.repealed.get(a, False), -(self._year(a) or 0)))
            self.stems.append((stem, ids[0]))
        self.stems.sort(key=lambda s: -len(s[0]))

    def _year(self, act_id: int) -> int | None:
        years = re.findall(r"(1[6-9]\d\d|20\d\d)", bn_to_ascii_digits(self.titles.get(act_id, "")))
        return int(years[-1]) if years else None

    def _principal(self, phrase: str) -> list[int]:
        """Acts whose title contains `phrase`: in force first, amending acts last, shortest first."""
        found = [(aid, t) for aid, t in self.titles.items() if phrase in _norm(t)]
        found.sort(key=lambda x: (self.repealed.get(x[0], False), bool(_AMENDING.search(x[1])), len(x[1])))
        return [aid for aid, _ in found[:1]]

    def resolve(self, question: str) -> Reference:
        q = _norm(question)
        acts: list[int] = []
        for stem, aid in self.stems:              # longest official title first
            if stem in q and aid not in acts:
                acts.append(aid)
                q = q.replace(stem, " ")
        if not acts:
            for alias, phrase in ACT_ALIASES.items():
                if re.search(rf"(?<![\wঀ-৿]){re.escape(_norm(alias))}", q):
                    for aid in self._principal(phrase):
                        if aid not in acts:
                            acts.append(aid)
        numbers = [bn_to_ascii_digits(n).replace(" ", "").upper() for n in SECTION_REF.findall(question)]
        return Reference(act_ids=acts[:3], numbers=list(dict.fromkeys(numbers))[:4])

    def lookup(self, act_id: int, number: str, max_parts: int = 3) -> list[Hit]:
        return self.by_number.get((act_id, number.upper()), [])[:max_parts]


def apply_reference(hits: list[Hit], ref: Reference, resolver: ActResolver) -> list[Hit]:
    """Put exact matches first, then move same-number / same-act hits up (stable)."""
    if not ref:
        return hits
    top = hits[0].score if hits else 1.0
    exact: list[Hit] = []
    if ref.act_ids and ref.numbers:
        for aid in ref.act_ids:
            for num in ref.numbers:
                exact += resolver.lookup(aid, num)
    seen = {h.chunk_id for h in exact}
    rest = [h for h in hits if h.chunk_id not in seen]

    def wanted(h: Hit) -> bool:
        m = h.metadata
        num_ok = not ref.numbers or str(m.get("section_number_ascii") or "").upper() in ref.numbers
        act_ok = not ref.act_ids or m.get("act_id") in ref.act_ids
        return num_ok and act_ok

    promoted = [h for h in rest if wanted(h)]
    others = [h for h in rest if not wanted(h)]
    ordered = exact + promoted + others
    # Keep scores monotone so later stages (thresholds, rerankers) see the new order.
    n = len(ordered)
    return [Hit(h.chunk_id, float(top) + (n - i) * 1e-6 if i < len(exact) + len(promoted) else h.score,
                h.text, h.body, h.metadata) for i, h in enumerate(ordered)]
