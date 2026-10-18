"""Everyday situations -> the provisions that govern them.

The scenario run (2026-10-16) failed in the same way three times: the question
was about a common situation, the governing section was in the index, and
retrieval never reached it.

  "the shop sold me a faulty fridge"   -> ভোক্তা-অধিকার সংরক্ষণ আইন ss. 45, 60, 66
                                          (English question, Bangla act: no shared words)
  "someone posted lies about me"       -> Penal Code ss. 499, 500
  "my employer hasn't paid my salary"  -> শ্রম আইন ss. 123, 132 (the act is huge; the
                                          wage-payment sections lose to definitions)

A lawyer does not search for these: they know where to look. This table is that
knowledge, written down. A topic names trigger words (English, Bangla and the
colloquial forms people type), the act that governs it (by title phrase, with
the bdlaws act id as a hint) and the sections a lawyer would open first. The
pipeline looks those sections up and gives them reserved places in the
results, next to whatever the search found.

Section numbers marked VERIFIED are the gold sections of data/eval/eval_scenarios.jsonl,
checked against the full index. The others are the standard provisions for the
topic; `bdrag topics` prints what each one resolves to in your index, so a
wrong number shows up as a wrong section title, not as a silent miss.
A number that does not exist in the index adds nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.textutils import nfc

from .refs import ActResolver, _norm
from .store import Hit


@dataclass(frozen=True)
class ActRef:
    phrases: tuple[str, ...]          # any one occurring in the official title
    sections: tuple[str, ...] = ()    # () = search inside the act, pin nothing
    act_id: int | None = None         # bdlaws id; used when its title matches a phrase


@dataclass(frozen=True)
class Topic:
    name: str
    triggers: tuple[str, ...]         # word prefixes (Bangla case endings attach); "x!" = whole word
    acts: tuple[ActRef, ...]
    pattern: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        alts = "|".join(re.escape(_norm(t[:-1])) + r"(?![\wঀ-৿])" if t.endswith("!")
                        else re.escape(_norm(t)) for t in self.triggers)
        object.__setattr__(self, "pattern", re.compile(rf"(?<![\wঀ-৿])(?:{alts})"))


PENAL = ("penal code", "দণ্ডবিধি")
CRPC = ("code of criminal procedure", "ফৌজদারী কার্যবিধি")
LABOUR = ("বাংলাদেশ শ্রম আইন", "bangladesh labour act")
CONSUMER = ("ভোক্তা অধিকার সংরক্ষণ আইন", "consumer rights protection")
WOMEN_CHILD = ("নারী ও শিশু নির্যাতন দমন আইন", "women and children repression")
MFLO = ("muslim family laws ordinance", "মুসলিম পারিবারিক আইন অধ্যাদেশ")

# Most specific first: when several topics match, earlier ones get the reserved places.
TOPICS: tuple[Topic, ...] = (
    Topic("dowry", ("dowry", "যৌতুক"), (
        ActRef(("যৌতুক নিরোধ আইন", "dowry prohibition"), ("3",), 1256),          # VERIFIED
        ActRef(WOMEN_CHILD, ("11",), 835),                                       # VERIFIED
    )),
    Topic("rape", ("rape", "raped", "ধর্ষণ", "sexual assault", "sexually assault",
                   "যৌন নিপীড়ন", "যৌন হয়রানি", "sexual harass"), (
        ActRef(WOMEN_CHILD, ("9", "10"), 835),
    )),
    Topic("child marriage", ("child marriage", "underage marriage", "বাল্যবিবাহ",
                             "বাল্য বিবাহ"), (
        ActRef(("বাল্যবিবাহ নিরোধ আইন", "child marriage restraint"), ("7", "8")),
    )),
    Topic("domestic violence", ("domestic violence", "পারিবারিক সহিংসতা", "beats me",
                                "beat me", "hits me", "husband beat", "মারধর", "নির্যাতন করে"), (
        ActRef(("পারিবারিক সহিংসতা", "domestic violence"), ("3", "11")),
        ActRef(PENAL, ("323",), 11),
    )),
    Topic("defamation", ("defam", "libel", "slander", "মানহানি", "অপবাদ", "বদনাম",
                         "spreading lies", "spread lies", "false rumour", "false rumor",
                         "posted lies", "মিথ্যা অপপ্রচার", "কুৎসা"), (
        ActRef(PENAL, ("499", "500"), 11),                                       # VERIFIED
    )),
    Topic("cheque", ("cheque", "check bounce", "bounced check", "চেক ডিজঅনার", "চেক বাউন্স",
                     "চেক ফেরত", "চেকের টাকা", "চেক প্রত্যাখ্যা", "চেক দিয়ে"), (
        ActRef(("negotiable instruments act", "হস্তান্তরযোগ্য দলিল আইন"), ("138",), 46),  # VERIFIED
    )),
    Topic("defective goods", ("defective", "faulty", "ত্রুটিপূর্ণ", "নষ্ট পণ্য"), (
        ActRef(CONSUMER, ("45", "60", "66"), 1014),                              # VERIFIED
        ActRef(("sale of goods act", "পণ্য বিক্রয় আইন"), ("16",), 150),             # VERIFIED
    )),
    Topic("consumer", ("consumer", "ভোক্তা", "ভেজাল", "adulterat", "expired product",
                       "মেয়াদোত্তীর্ণ", "overcharg", "বেশি দাম", "false advertis",
                       "মিথ্যা বিজ্ঞাপন", "sold me", "shopkeeper", "দোকানদার"), (
        ActRef(CONSUMER, ("45", "60", "66"), 1014),                              # VERIFIED
    )),
    Topic("wages", ("wage", "salary", "salaries", "overtime", "মজুরি", "বেতন"), (
        ActRef(LABOUR, ("123", "132"), 952),                                     # VERIFIED
    )),
    Topic("dismissal", ("dismiss", "fired", "terminat", "retrench", "laid off", "sacked",
                        "বরখাস্ত", "ছাঁটাই", "চাকরিচ্যুত", "চাকরি থেকে বের", "অব্যাহতি"), (
        ActRef(LABOUR, ("26", "33"), 952),                                       # 26 VERIFIED
    )),
    Topic("maternity", ("maternity", "pregnan", "প্রসূতি", "মাতৃত্ব", "গর্ভবতী"), (
        ActRef(LABOUR, ("45", "46"), 952),
    )),
    Topic("rent", ("landlord", "tenant", "rent", "বাড়িওয়ালা", "বাড়িওয়ালা", "ভাড়াটিয়া",
                   "ভাড়াটে", "বাসা ভাড়া", "বাড়ি ভাড়া", "ভাড়া"), (
        ActRef(("বাড়ি ভাড়া নিয়ন্ত্রণ আইন", "premises rent control"),
               ("7", "18", "23", "10"), 748),                                    # 7, 18, 23 VERIFIED
    )),
    Topic("land dispossession", ("dispossess", "grabbed my land", "land grab",
                                 "occupied my land", "জমি দখল", "বেদখল", "জোর করে দখল",
                                 "দখল করে নিয়েছে"), (
        ActRef(("specific relief act", "সুনির্দিষ্ট প্রতিকার আইন"), ("9",)),
        ActRef(CRPC, ("145",)),
    )),
    Topic("divorce", ("divorce", "talaq", "তালাক", "ডিভোর্স"), (
        ActRef(MFLO, ("7",)),
    )),
    Topic("maintenance", ("maintenance", "ভরণপোষণ", "খোরপোশ", "দেনমোহর", "dower", "mohr"), (
        ActRef(MFLO, ("9",)),
    )),
    Topic("second marriage", ("second marriage", "polygam", "দ্বিতীয় বিয়ে", "দ্বিতীয় বিবাহ"), (
        ActRef(MFLO, ("6",)),
    )),
    Topic("murder", ("murder", "killed", "হত্যা", "খুন"), (
        ActRef(PENAL, ("300", "302"), 11),
    )),
    Topic("theft", ("theft", "stole", "stolen", "চুরি"), (
        ActRef(PENAL, ("378", "379"), 11),
    )),
    Topic("cheating", ("cheat", "fraud", "scam", "প্রতারণা", "প্রতারক", "ঠকিয়ে", "ঠকিয়েছে"), (
        ActRef(PENAL, ("415", "420"), 11),
    )),
    Topic("threat", ("threat", "intimidat", "হুমকি", "ভয় দেখা"), (
        ActRef(PENAL, ("503", "506"), 11),
    )),
    Topic("hurt", ("assault", "attacked", "beaten", "injured", "আঘাত", "জখম", "মেরেছে"), (
        ActRef(PENAL, ("319", "323", "325"), 11),
    )),
    Topic("arrest", ("arrest", "detained", "গ্রেপ্তার", "গ্রেফতার", "আটক"), (
        ActRef(CRPC, ("54", "61")),
    )),
    Topic("bail", ("bail", "জামিন"), (
        ActRef(CRPC, ("496", "497")),
    )),
    Topic("police case", ("fir!", "police station", "police case", "file a case",
                          "thana", "থানা", "এজাহার", "জিডি", "মামলা করতে", "মামলা করব"), (
        ActRef(CRPC, ("154", "200")),
    )),
    Topic("deed registration", ("deed", "দলিল", "রেজিস্ট্রি", "registry"), (
        ActRef(("the registration act", "রেজিস্ট্রেশন আইন"), ("17",)),
    )),
    # Act-level only: these acts are recent or renumbered, so search inside them.
    Topic("cyber", ("cyber", "hack", "online harass", "facebook", "সাইবার", "হ্যাক",
                    "ফেসবুক", "অনলাইনে"), (
        ActRef(("সাইবার",)),
    )),
    Topic("trafficking", ("traffick", "মানব পাচার"), (
        ActRef(("মানব পাচার", "human trafficking"),),
    )),
    Topic("narcotics", ("narcotic", "drugs", "yaba", "মাদক", "ইয়াবা"), (
        ActRef(("মাদকদ্রব্য নিয়ন্ত্রণ আইন", "narcotics control"),),
    )),
    Topic("road accident", ("road accident", "hit by a", "সড়ক দুর্ঘটনা", "গাড়ি চাপা"), (
        ActRef(("সড়ক পরিবহন আইন", "road transport act"),),
    )),
)


def match_topics(question: str, topics: tuple[Topic, ...] = TOPICS) -> list[Topic]:
    q = _norm(nfc(question))
    return [t for t in topics if t.pattern.search(q)]


class TopicIndex:
    """Topic -> the act ids and section hits it resolves to in one index. Built once."""

    def __init__(self, resolver: ActResolver, topics: tuple[Topic, ...] = TOPICS) -> None:
        self.resolver, self.topics = resolver, topics
        self._acts: dict[ActRef, int | None] = {}

    def act_id(self, ref: ActRef) -> int | None:
        if ref not in self._acts:
            found = None
            title = self.resolver.titles.get(ref.act_id) if ref.act_id is not None else None
            if title and any(_norm(p) in _norm(title) for p in ref.phrases):
                found = ref.act_id
            else:
                for phrase in ref.phrases:
                    if ids := self.resolver.find_act(_norm(phrase)):
                        found = ids[0]
                        break
            self._acts[ref] = found
        return self._acts[ref]

    def resolve(self, question: str) -> tuple[list[Hit], list[int]]:
        """(the governing sections to pin, in priority order; act ids to search inside)."""
        hits: list[Hit] = []
        acts: list[int] = []
        seen: set[str] = set()
        for topic in match_topics(question, self.topics):
            for ref in topic.acts:
                aid = self.act_id(ref)
                if aid is None:
                    continue
                if aid not in acts:
                    acts.append(aid)
                for num in ref.sections:
                    # The first part of a section carries its heading and operative words.
                    for h in self.resolver.lookup(aid, num, max_parts=1):
                        if h.chunk_id not in seen:
                            seen.add(h.chunk_id)
                            hits.append(Hit(h.chunk_id, h.score, h.text, h.body,
                                            {**h.metadata, "topic": topic.name}))
        return hits, acts


def pin_topic_sections(hits: list[Hit], pinned: list[Hit], k: int, slots: int) -> list[Hit]:
    """Give up to `slots` governing sections a place in the top k, after any requested section.

    At least two places stay with the search, so a question the table misreads
    still gets what retrieval found.
    """
    slots = min(slots, max(k - 2, 1), len(pinned))
    if slots <= 0:
        return hits[:k]
    requested = [h for h in hits if h.metadata.get("requested")]
    chosen = [h for h in pinned if h.chunk_id not in {r.chunk_id for r in requested}][:slots]
    taken = {h.chunk_id for h in requested} | {h.chunk_id for h in chosen}
    # A governing section the search also found keeps its own (real) score.
    found = {h.chunk_id: h for h in hits}
    top = max((h.score for h in hits), default=1.0)
    chosen = [Hit(h.chunk_id, found[h.chunk_id].score if h.chunk_id in found else top,
                  h.text, h.body, {**(found[h.chunk_id].metadata if h.chunk_id in found
                                      else h.metadata), "topic": h.metadata["topic"]})
              for h in chosen]
    rest = [h for h in hits if h.chunk_id not in taken]
    return (requested + chosen + rest)[:k]
