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

Trigger words alone missed the same three situations when people described them
in their own words ("my boss hasn't paid me", "the seller won't take it back",
"telling everyone I am a thief"). Those get a second entry under the same name:
a broader word plus a word that places it (a job, a purchase gone wrong, spreading
a lie). data/eval/eval_gaps.jsonl holds 13 such questions, written before the
entries were.

Sections marked VERIFIED are also gold sections of data/eval/eval_scenarios.jsonl.
Every number here was checked against the full index on 2026-10-19 with
`bdrag topics` (43,966 chunks): each resolves to the section its topic means.
Re-run it after a re-ingest; a wrong number shows up as a wrong section title,
and a number that does not exist in the index adds nothing.
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
    also: tuple[str, ...] = ()        # if set, the question must contain one of these too
    pattern: re.Pattern = field(init=False, repr=False, compare=False)
    also_pattern: re.Pattern | None = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pattern", _compile(self.triggers))
        object.__setattr__(self, "also_pattern", _compile(self.also) if self.also else None)

    def matches(self, normalised_question: str) -> bool:
        return bool(self.pattern.search(normalised_question)) and (
            self.also_pattern is None or bool(self.also_pattern.search(normalised_question)))


def _compile(terms: tuple[str, ...]) -> re.Pattern:
    alts = "|".join(re.escape(_norm(t[:-1])) + r"(?![\wঀ-৿])" if t.endswith("!")
                    else re.escape(_norm(t)) for t in terms)
    return re.compile(rf"(?<![\wঀ-৿])(?:{alts})")


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
    Topic("rape", ("rape", "raped", "ধর্ষণ", "sexual assault", "sexually assault"), (
        ActRef(WOMEN_CHILD, ("9",), 835),
        ActRef(PENAL, ("376",), 11),
    )),
    Topic("sexual harassment", ("sexual harass", "যৌন হয়রানি", "যৌন নিপীড়ন", "যৌন পীড়ন",
                                "eve teas", "ইভটিজিং"), (
        ActRef(WOMEN_CHILD, ("10",), 835),
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
    # How people describe defamation without the word: a lie, plus harm to their name
    # or the act of spreading it.
    Topic("defamation", ("reputation", "good name", "সম্মানহানি", "সুনাম", "মান-সম্মান",
                         "সম্মান নষ্ট", "চরিত্র হনন"), (
        ActRef(PENAL, ("499", "500"), 11),
    )),
    Topic("defamation", ("false", "untrue", "lies!", "lying about", "lied about", "মিথ্যা"), (
        ActRef(PENAL, ("499", "500"), 11),
    ), also=("telling everyone", "told everyone", "telling people", "spreading", "spread",
             "sharing", "posted", "posting", "publish", "online", "social media", "facebook",
             "about me", "আমার নামে", "আমার বিরুদ্ধে", "ছড়া", "রটা", "পোস্ট", "ফেসবুক")),
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
    # A purchase that went wrong, told without "consumer" or "defective": the English
    # question has no word in common with the Bangla act, so the table has to bridge it.
    Topic("consumer", ("bought", "buying", "purchas", "seller", "shop", "store", "pharmacy",
                       "restaurant", "online order", "কেনা", "কিনেছি", "কিনেছিলাম", "কিনলাম",
                       "বিক্রেতা", "দোকান", "ফার্মেসি", "রেস্তোরাঁ", "রেস্টুরেন্ট"), (
        ActRef(CONSUMER, ("45", "60", "66"), 1014),
    ), also=("broke", "broken", "stopped working", "not working", "damaged", "rotten", "spoil",
             "stale", "fake", "counterfeit", "refund", "replace", "take it back", "take back", "return",
             "never delivered", "not delivered", "didn't deliver", "did not deliver",
             "printed price", "mrp", "নষ্ট", "ফেরত", "ভেজাল", "পচা", "নকল", "বদলে", "বেশি দাম",
             "দাম বেশি", "সরবরাহ")),
    Topic("wages", ("wage", "salary", "salaries", "overtime", "মজুরি", "বেতন"), (
        ActRef(LABOUR, ("123", "132"), 952),                                     # VERIFIED
    )),
    # Unpaid work described without "wage" or "salary": a missing payment plus a job.
    Topic("wages", ("paid me", "pay me", "paying me", "unpaid", "my pay!", "their pay!",
                    "last pay", "delaying pay", "owe me", "owes me", "earnings", "dues!",
                    "পারিশ্রমিক", "বকেয়া", "পাওনা", "টাকা দেয়নি", "টাকা দিচ্ছে না",
                    "টাকা দিচ্ছেন না"), (
        ActRef(LABOUR, ("123", "132"), 952),
    ), also=("employer", "boss", "factory", "company", "worker", "workers", "job", "office",
             "resigned", "garment", "মালিক", "অফিস", "কারখানা", "শ্রমিক", "চাকরি", "কোম্পানি",
             "বস", "গার্মেন্টস")),
    Topic("dismissal", ("dismiss", "fired", "terminat", "retrench", "laid off", "sacked",
                        "বরখাস্ত", "ছাঁটাই", "চাকরিচ্যুত", "চাকরি থেকে বের", "অব্যাহতি"), (
        ActRef(LABOUR, ("26", "33"), 952),                                       # 26 VERIFIED
    )),
    Topic("maternity", ("maternity", "pregnan", "প্রসূতি", "মাতৃত্ব", "গর্ভবতী"), (
        ActRef(LABOUR, ("45", "46"), 952),
    )),
    Topic("rent", ("landlord", "tenant", "rent", "বাড়িওয়ালা", "বাড়ীওয়ালা", "ভাড়াটিয়া",
                   "ভাড়াটে", "বাসা ভাড়া", "বাড়ি ভাড়া", "বাড়ী ভাড়া", "ভাড়া"), (
        ActRef(("বাড়ী ভাড়া নিয়ন্ত্রণ আইন", "বাড়ি ভাড়া নিয়ন্ত্রণ আইন", "premises rent control"),
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
    Topic("parent maintenance", ("maintenance", "ভরণপোষণ", "ভরণ-পোষণ", "look after", "দেখাশোনা"), (
        ActRef(("পিতা মাতার ভরণ পোষণ আইন", "maintenance of parents"), ("3", "5", "7"), 1132),
    ), also=("parent", "father", "mother", "elderly", "বাবা", "পিতা", "মা-বাবা", "মাতা")),
    Topic("maintenance", ("maintenance", "ভরণপোষণ", "ভরণ-পোষণ", "খোরপোশ", "দেনমোহর", "dower", "mohr"), (
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
    # Fraud that induced an agreement is a contract question first, a crime second.
    Topic("contract fraud", ("contract", "agreement", "চুক্তি", "সম্মতি"), (
        ActRef(("the contract act", "চুক্তি আইন"), ("17", "19"), 26),
    ), also=("fraud", "cheat", "deceiv", "misrepresent", "coerc", "প্রতারণা", "জবরদস্তি",
             "মিথ্যা বর্ণনা")),
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
        ActRef(("constitution of the people", "গণপ্রজাতন্ত্রী বাংলাদেশের সংবিধান"), ("33",), 367),
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
    Topic("road accident", ("road accident", "hit by a", "rash driving", "সড়ক দুর্ঘটনা",
                            "গাড়ি চাপা", "বেপরোয়া গাড়ি"), (
        ActRef(PENAL, ("279", "304A", "304B"), 11),
        ActRef(("সড়ক পরিবহন আইন", "road transport act"),),     # not in the 2026-10 index
    )),
)


def match_topics(question: str, topics: tuple[Topic, ...] = TOPICS) -> list[Topic]:
    """Matching topics, most specific first. Entries sharing a name are other ways of
    describing the same situation (they name the same acts), so each name counts once."""
    q = _norm(nfc(question))
    found: dict[str, Topic] = {}
    for t in topics:
        if t.name not in found and t.matches(q):
            found[t.name] = t
    return list(found.values())


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
    """Make sure up to `slots` governing sections are in the top k.

    A governing section the search already ranked in the top k stays where it
    is. The others take the last places, so the search's own best hits keep the
    first ones: measured on the full index, putting the table's sections first
    raised recall but pushed bge-m3's correct first hit down (MRR 0.78 -> 0.73).
    At least two places always stay with the search.
    """
    slots = min(slots, max(k - 2, 1), len(pinned))
    top_k = hits[:k]
    if slots <= 0:
        return top_k
    in_top = {h.chunk_id for h in top_k}
    requested = {h.chunk_id for h in hits if h.metadata.get("requested")}
    chosen = [h for h in pinned if h.chunk_id not in requested][:slots]
    topic = {h.chunk_id: h.metadata["topic"] for h in chosen}
    missing = [h for h in chosen if h.chunk_id not in in_top]
    kept = [h for h in hits if h.chunk_id not in topic or h.chunk_id in in_top][:k - len(missing)]
    floor = kept[-1].score if kept else 1.0
    return ([Hit(h.chunk_id, h.score, h.text, h.body, {**h.metadata, "topic": topic[h.chunk_id]})
             if h.chunk_id in topic else h for h in kept]
            + [Hit(h.chunk_id, floor, h.text, h.body, h.metadata) for h in missing])
