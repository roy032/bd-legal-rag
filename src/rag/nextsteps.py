"""A "what to do next" checklist for an answer about someone's situation.

answer-system/v6 asks the model to end a situation answer with numbered steps
under "What you can do" ("আপনি যা করতে পারেন"), each cited, and an optional
"Practical tips" list. This module reads those back out of the text, so the
page can show them as a checklist the person ticks off, prints or copies,
without a second model call.

The checklist has three parts, and only the first comes from the law:

  steps  the cited steps from the answer, kept with their [n] markers;
  tips   the model's uncited practical tips, or a fixed set when it gave none
         (keep papers, write down dates); they never state law;
  help   who to call: the legal aid hotline and the hotlines for the
         situation (legalaid.py), never written by the model.

A question that is not about a situation ("what does section 302 say?") gets
no checklist, and neither does a refusal.
"""
from __future__ import annotations

import re

from ingest.textutils import nfc

from .legalaid import contacts_for, lang_of
from .scope import classify_request
from .topics import match_topics

_STEPS_HEAD = re.compile(nfc(
    r"^[\s*_#>`\-]*(?:what you can do|what to do next|what you can do next|next steps|"
    r"steps you can take|আপনি যা করতে পারেন|আপনি কী করতে পারেন|আপনার করণীয়|করণীয়|"
    r"পরবর্তী পদক্ষেপ)[\s*_`:ঃ।.]*$"), re.IGNORECASE | re.MULTILINE)
# The tips heading as its own line (guardrails.TIPS_HEAD also matches it inline).
TIPS_HEAD_LINE = re.compile(r"^[\s*_#>`\-]*(?:practical tips|ব্যবহারিক পরামর্শ)[\s*_`:ঃ।.]*$",
                            re.IGNORECASE | re.MULTILINE)
_ITEM = re.compile(r"^\s*(?:[0-9০-৯]{1,2}[.)।]|[-*•‣–])\s+(.*\S)\s*$")
_HEADING = re.compile(r"^\s*(?:#{1,4}\s+\S|\*\*[^*]+\*\*[:ঃ]?\s*$)")
_CITES = re.compile(r"\[(\d{1,2})\]")
_MARKUP = re.compile(r"\*\*|__")

GENERAL_TIPS = {
    "en": ("Write down what happened, with dates, places and the names of anyone who saw it.",
           "Keep copies of every paper: receipts, letters, notices, agreements, photos and messages.",
           "Do not sign anything you do not understand; ask legal aid to read it with you first."),
    "bn": ("কী ঘটেছে তা তারিখ, স্থান ও সাক্ষীদের নামসহ লিখে রাখুন।",
           "সব কাগজের কপি রাখুন: রসিদ, চিঠি, নোটিশ, চুক্তি, ছবি ও মেসেজ।",
           "না বুঝে কিছুতে সই করবেন না; আগে লিগ্যাল এইডের কাউকে দিয়ে পড়িয়ে নিন।"),
}


def _list(lines: list[str]) -> tuple[list[str], int]:
    """(list items, lines used) from the top of `lines`. An unmarked line continues
    the item above it; a heading, or a paragraph after a blank line, ends the list."""
    items: list[str] = []
    used = 0
    gap = False
    for i, line in enumerate(lines):
        if not line.strip():
            gap = True
            continue
        m = _ITEM.match(line)
        if not m and (_HEADING.match(line) or gap or not items):
            break
        if m:
            items.append(m.group(1))
        else:
            items[-1] += " " + line.strip()
        used = i + 1
        gap = False
    return [_MARKUP.sub("", x).strip() for x in items if x.strip()], used


def _section(text: str, head: re.Pattern) -> tuple[list[str], int, int]:
    """(items, start, end) of the list under `head` in text; ([], -1, -1) if none."""
    m = head.search(text)
    if not m:
        return [], -1, -1
    rest = text[m.end():]
    lines = rest.split("\n")
    if lines and not lines[0].strip():
        lines = lines[1:]
        offset = m.end() + len(rest.split("\n", 1)[0]) + 1
    else:
        offset = m.end()
    items, used = _list(lines)
    end = offset + sum(len(x) + 1 for x in lines[:used])
    return items, m.start(), min(end, len(text))


def split_answer(text: str) -> tuple[str, list[dict], list[str]]:
    """(the answer without its steps and tips lists, the steps, the tips).

    Steps are [{"text": "...[2]", "cites": [2]}], their citations kept; tips are
    plain strings. A list that is not there comes back empty and leaves the text alone.
    """
    text = nfc(text or "")
    body = text
    steps, s0, s1 = _section(text, _STEPS_HEAD)
    if steps:
        body = text[:s0].rstrip() + "\n\n" + text[s1:].lstrip()
    tips, t0, t1 = _section(body, TIPS_HEAD_LINE)
    if tips:
        body = body[:t0].rstrip() + "\n\n" + body[t1:].lstrip()
    # The advice notice comes after the lists; it is never a tip.
    tips = [t for t in tips if "16430" not in t and "১৬৪৩০" not in t][:3]
    return (body.strip(),
            [{"text": x, "cites": sorted({int(n) for n in _CITES.findall(x)})} for x in steps],
            tips)


def extract_steps(text: str) -> list[dict]:
    return split_answer(text)[1]


def extract_tips(text: str) -> list[str]:
    return split_answer(text)[2]


def checklist(question: str, text: str, refused: bool = False,
              general: bool = False) -> dict | None:
    """The checklist for one answer, or None when there is nothing to act on."""
    if refused or not text:
        return None
    situation = classify_request(question)["advice"] or bool(match_topics(question))
    lang = lang_of(question)
    body, steps, tips = split_answer(text) if not general else (text, [], [])
    if not (steps or situation):
        return None
    return {"lang": lang, "steps": steps, "tips": tips or list(GENERAL_TIPS[lang]),
            "generic_tips": not tips, "help": contacts_for(question, lang),
            # The answer without the lists above, so the page shows each thing once.
            "body": body if (steps or tips) else None}
