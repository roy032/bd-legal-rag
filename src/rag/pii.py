"""Personal data in questions: find it and replace it before it goes anywhere.

People describe their own situation ("my landlord, phone 01712-345678, ...") and
paste their NID number or email into the box. None of it helps retrieval, and
each copy is a liability: the question is sent to the answering model (a hosted
free API in many setups), written to data/queries.jsonl and data/feedback.jsonl,
and cached. The service replaces it at the door (BDRAG_REDACT_PII, on by default).

Only identifiers with a fixed shape are matched, in ASCII and Bangla digits:
Bangladeshi mobile numbers, NID numbers (10, 13 or 17 digits), card numbers,
passport numbers and email addresses. Section numbers, years and amounts of
money do not have those shapes; data/eval/redteam.jsonl checks both ways.
"""
from __future__ import annotations

import re

_D = "[0-9০-৯]"
_NOT_DIGIT_BEFORE = r"(?<![0-9০-৯])"
_NOT_DIGIT_AFTER = r"(?![0-9০-৯])"

# Order matters: a phone number with the country code is 13 digits, like an NID.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("card", re.compile(_NOT_DIGIT_BEFORE + rf"{_D}{{4}}(?:[ -]{_D}{{4}}){{3}}" + _NOT_DIGIT_AFTER)),
    ("phone", re.compile(
        _NOT_DIGIT_BEFORE
        # 01XXX-XXXXXX, or with the country code, where the 0 may go: +880 1XXX ...
        + rf"(?:(?:\+|00)?(?:88|৮৮)[\s-]?[0০]?[\s-]?|[0০])[1১][3-9৩-৯]{_D}{{2}}[\s-]?{_D}{{3}}[\s-]?{_D}{{3}}"
        + _NOT_DIGIT_AFTER)),
    ("nid", re.compile(_NOT_DIGIT_BEFORE + rf"(?:{_D}{{17}}|{_D}{{13}}|{_D}{{10}})"
                       + _NOT_DIGIT_AFTER)),
    ("passport", re.compile(r"\b[A-Z]{1,2}[0-9]{7,8}\b")),
]

PLACEHOLDER = {"email": "[email]", "card": "[card]", "phone": "[phone]", "nid": "[NID]",
               "passport": "[passport]"}


def redact(text: str) -> tuple[str, list[str]]:
    """(text with each identifier replaced by a placeholder, the kinds replaced)."""
    kinds = []
    for kind, pattern in PATTERNS:
        text, n = pattern.subn(PLACEHOLDER[kind], text or "")
        if n:
            kinds.append(kind)
    return text, kinds
