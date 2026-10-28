"""Legal words in everyday language, for plain-language mode.

The plain prompt asks the model to explain a legal word in brackets, and a
small model forgets to about as often as it remembers. These short meanings
are written once, by people, in both languages, and shown under the answer for
the words it actually uses. They describe what a word means in general, never
what any section says, so they need no citation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.textutils import nfc


@dataclass(frozen=True)
class Term:
    en: str
    bn: str
    plain_en: str
    plain_bn: str
    forms: tuple[str, ...]            # English words (prefixes) and Bangla forms that signal it
    pattern: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # English forms are whole words ("suit", not "suitable"); Bangla forms are
        # prefixes, because case endings attach ("জামিনের", "জামিনে").
        alts = "|".join(re.escape(f) + r"(?:s|es|ed)?(?![\w])" if f.isascii()
                        else re.escape(nfc(f)) for f in self.forms)
        object.__setattr__(self, "pattern", re.compile(rf"(?<![\wঀ-৿])(?:{alts})", re.IGNORECASE))


TERMS: tuple[Term, ...] = (
    Term("bail", "জামিন",
         "Being let out of custody while the case goes on, usually on a promise to come to court.",
         "মামলা চলার সময় হাজতের বাইরে থাকার অনুমতি, সাধারণত আদালতে হাজির হওয়ার অঙ্গীকারে।",
         ("bail", "জামিন")),
    Term("bailable offence", "জামিনযোগ্য অপরাধ",
         "An offence for which the accused has a right to bail.",
         "যে অপরাধে অভিযুক্তের জামিন পাওয়ার অধিকার আছে।",
         ("bailable", "জামিনযোগ্য")),
    Term("cognizable offence", "আমলযোগ্য অপরাধ",
         "A serious offence the police can investigate, and arrest for, without a court's order.",
         "গুরুতর অপরাধ, যাতে পুলিশ আদালতের আদেশ ছাড়াই তদন্ত ও গ্রেপ্তার করতে পারে।",
         ("cognizable", "cognisable", "আমলযোগ্য")),
    Term("warrant", "পরোয়ানা",
         "A written order from a court, for example to arrest a person or search a place.",
         "আদালতের লিখিত আদেশ, যেমন কাউকে গ্রেপ্তার বা কোনো জায়গা তল্লাশি করার।",
         ("warrant", "পরোয়ানা", "ওয়ারেন্ট")),
    Term("FIR", "এজাহার",
         "The first report of a crime written down at the police station; it starts a police case.",
         "থানায় লেখা অপরাধের প্রথম বিবরণ; এ থেকেই পুলিশের মামলা শুরু হয়।",
         ("fir", "first information report", "এজাহার", "এফআইআর")),
    Term("complaint (to a magistrate)", "নালিশি মামলা",
         "Telling a magistrate about an offence directly, instead of going through the police.",
         "পুলিশের মাধ্যমে না গিয়ে সরাসরি ম্যাজিস্ট্রেটের কাছে অপরাধের অভিযোগ করা।",
         ("nalishi", "নালিশি", "petition case")),
    Term("magistrate", "ম্যাজিস্ট্রেট",
         "A judge who hears smaller criminal cases and decides on arrests, bail and complaints.",
         "যে বিচারক ছোট ফৌজদারি মামলা শোনেন এবং গ্রেপ্তার, জামিন ও অভিযোগ নিয়ে সিদ্ধান্ত দেন।",
         ("magistrate", "ম্যাজিস্ট্রেট")),
    Term("suit", "মোকদ্দমা",
         "A civil case one person brings against another in court, for example over land or money.",
         "দেওয়ানি মামলা, যা একজন আরেকজনের বিরুদ্ধে আদালতে করেন, যেমন জমি বা টাকা নিয়ে।",
         ("suit", "মোকদ্দমা")),
    Term("plaintiff", "বাদী",
         "The person who starts a case.", "যিনি মামলা শুরু করেন।",
         ("plaintiff", "complainant", "বাদী", "বাদি")),
    Term("defendant / accused", "বিবাদী / আসামি",
         "The person a case is brought against.", "যার বিরুদ্ধে মামলা করা হয়।",
         ("defendant", "accused", "বিবাদী", "আসামি", "আসামী")),
    Term("summons", "সমন",
         "A court's written order to come to court on a given day.",
         "নির্দিষ্ট দিনে আদালতে হাজির হওয়ার জন্য আদালতের লিখিত আদেশ।",
         ("summons", "সমন")),
    Term("injunction", "নিষেধাজ্ঞা",
         "A court order telling someone to stop doing something, or not to start.",
         "কাউকে কোনো কাজ বন্ধ রাখতে বা শুরু না করতে আদালতের আদেশ।",
         ("injunction", "নিষেধাজ্ঞা")),
    Term("limitation period", "তামাদি",
         "The time limit for going to court; after it runs out the case may not be heard.",
         "আদালতে যাওয়ার সময়সীমা; তা পার হলে মামলা শোনা না-ও হতে পারে।",
         ("limitation", "time-barred", "তামাদি")),
    Term("compensation", "ক্ষতিপূরণ",
         "Money paid to make up for a loss or harm.", "ক্ষতি বা আঘাতের বদলে দেওয়া টাকা।",
         ("compensation", "damages", "ক্ষতিপূরণ")),
    Term("fine", "অর্থদণ্ড / জরিমানা",
         "A money penalty paid to the state.", "রাষ্ট্রকে দেওয়া টাকার শাস্তি।",
         ("fine", "fined", "অর্থদণ্ড", "জরিমানা")),
    Term("rigorous imprisonment", "সশ্রম কারাদণ্ড",
         "Prison with hard labour.", "কারাগারে থেকে কঠোর পরিশ্রমসহ সাজা।",
         ("rigorous imprisonment", "সশ্রম")),
    Term("simple imprisonment", "বিনাশ্রম কারাদণ্ড",
         "Prison without labour.", "পরিশ্রম ছাড়া কারাদণ্ড।",
         ("simple imprisonment", "বিনাশ্রম")),
    Term("dower (mohr)", "দেনমোহর",
         "Money or property a Muslim husband owes his wife under the marriage contract.",
         "বিয়ের চুক্তি অনুযায়ী মুসলিম স্বামী স্ত্রীকে যে টাকা বা সম্পদ দিতে বাধ্য।",
         ("dower", "mohr", "mahr", "দেনমোহর", "মোহরানা")),
    Term("maintenance", "ভরণপোষণ / খোরপোশ",
         "Regular money for food, housing and living costs that one family member must pay another.",
         "খাওয়া, থাকা ও জীবনযাপনের খরচ বাবদ পরিবারের একজনকে অন্যজনের নিয়মিত দেওয়া টাকা।",
         ("maintenance", "ভরণপোষণ", "ভরণ-পোষণ", "খোরপোশ")),
    Term("Union Parishad / Arbitration Council", "ইউনিয়ন পরিষদ / সালিসি পরিষদ",
         "The local council; under family law its chairman sets up a council to try to settle disputes.",
         "স্থানীয় পরিষদ; পারিবারিক আইনে এর চেয়ারম্যান বিরোধ মীমাংসার জন্য সালিসি পরিষদ গঠন করেন।",
         ("arbitration council", "union parishad", "সালিসি পরিষদ", "ইউনিয়ন পরিষদ")),
    Term("mediation", "মধ্যস্থতা / আপস",
         "Settling a dispute by agreement, with a neutral person helping, instead of a full trial.",
         "পূর্ণ বিচারের বদলে একজন নিরপেক্ষ ব্যক্তির সহায়তায় সমঝোতায় বিরোধ মেটানো।",
         ("mediation", "মধ্যস্থতা", "আপস-মীমাংসা", "এডিআর")),
    Term("appeal", "আপিল",
         "Asking a higher court to change a lower court's decision.",
         "নিচের আদালতের সিদ্ধান্ত বদলাতে উচ্চতর আদালতে আবেদন।",
         ("appeal", "আপিল")),
    Term("affidavit", "হলফনামা",
         "A written statement sworn to be true before an authorised officer.",
         "অনুমোদিত কর্মকর্তার সামনে সত্য বলে শপথ করা লিখিত বিবৃতি।",
         ("affidavit", "হলফনামা")),
    Term("deed", "দলিল",
         "A signed document that transfers or records rights in property, usually registered.",
         "সম্পত্তির অধিকার হস্তান্তর বা লিপিবদ্ধ করার স্বাক্ষরিত কাগজ, সাধারণত নিবন্ধিত।",
         ("deed", "দলিল")),
)


def terms_in(text: str, lang: str, limit: int = 6) -> list[dict]:
    """[{"term", "plain"}] for the glossary words the text uses, in order of first use."""
    text = nfc(text or "")
    found = []
    for t in TERMS:
        m = t.pattern.search(text)
        if m:
            found.append((m.start(), t))
    found.sort(key=lambda x: x[0])
    bn = lang == "bn"
    return [{"term": t.bn if bn else t.en, "plain": t.plain_bn if bn else t.plain_en}
            for _, t in found[:limit]]
