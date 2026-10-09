"""Query-side transforms. The cheapest ones are not the LLM ones.

expand_section_refs  free, deterministic, and the highest-value trick in this
                     corpus: "ধারা ৩০২" also searches "section 302" and "302".
multi_query          ask the LLM for 2-3 rephrasings, retrieve each, fuse.
hyde                 ask the LLM to write the provision it expects, embed THAT.
                     An answer looks more like a statute than a question does.

Both LLM transforms cost a call per question: measure whether they beat
expand_section_refs before paying for them on every query.
"""
from __future__ import annotations

import re

from ingest.textutils import bn_to_ascii_digits, nfc

# The optional letter suffix ("304A", "৫ক") must touch the digits and end the
# token: "ধারা ৩০২ কী" is section 302, not "302ক", and "section 2 of" is not "2OF".
# "article"/"অনুচ্ছেদ" because the Constitution numbers its provisions as articles.
SECTION_REF = re.compile(nfc(r"(?:ধারা(?:র|য়|য়ে|তে)?|উপ-?ধারা|অনুচ্ছেদ(?:ের|ে)?|sections?|sec\.?|ss?\.|"
                             r"article|art\.)\s*"
                             r"([0-9০-৯]+(?:[A-Za-z]{1,2}(?![A-Za-z])|[ক-হ](?![ঀ-৿]))?)"),
                         re.IGNORECASE)


_NUM = r"[0-9০-৯]+(?:[A-Za-z]{1,2}(?![A-Za-z])|[ক-হ](?![ঀ-৿]))?"
# "ধারা ৩০২ ও ৩০৪", "sections 302, 304 and 304A": numbers chained after the first one.
_MORE_REFS = re.compile(nfc(rf"\s*(?:,|ও|এবং|আর|and|&|or|বা)\s*(?:ধারা\s*)?({_NUM})"), re.IGNORECASE)


def section_numbers(question: str, limit: int = 4) -> list[str]:
    """Every section number the question names, including ones listed after the first."""
    found: list[str] = []
    for m in SECTION_REF.finditer(question):
        found.append(m.group(1))
        end = m.end()
        while (more := _MORE_REFS.match(question, end)):
            found.append(more.group(1))
            end = more.end()
    nums = [bn_to_ascii_digits(n).replace(" ", "").upper() for n in found]
    return list(dict.fromkeys(nums))[:limit]


def expand_section_refs(question: str) -> str:
    """Add the other spellings of any section number mentioned.

    'ধারা ৩০২ এ কী আছে?' -> 'ধারা ৩০২ এ কী আছে? ধারা 302 section 302 302'
    This helps BM25 a lot and dense retrieval a little, costs nothing, and
    never fires when no section number is mentioned.
    """
    extras: list[str] = []
    for num in section_numbers(question):
        extras += [f"ধারা {num}", f"section {num}", num]
    return f"{question} {' '.join(dict.fromkeys(extras))}".strip() if extras else question


MULTI_QUERY_PROMPT = """Rewrite this legal question in {n} different ways someone might
phrase it when searching the text of Bangladeshi statutes. Keep the same meaning and the
same language as the question. Use the words a statute would use where you can.

Question: {question}

Reply with one rewrite per line, no numbering, nothing else."""

HYDE_PROMPT = """Write the text of a statutory provision from Bangladeshi law that would
answer this question. Two or three sentences, in the drafting style of an Act, in the same
language as the question. Do not say you are unsure; an approximate provision is fine —
it is used only as a search query.

Question: {question}"""


def multi_query(question: str, llm, n: int = 3, max_variants: int = 4) -> list[str]:
    try:
        text = llm("You rewrite search queries. Output only the rewrites.",
                   MULTI_QUERY_PROMPT.format(n=n, question=question))
    except Exception:
        return [question]                      # never let a rewrite failure kill a query
    variants = [ln.strip(" -•\t") for ln in (text or "").splitlines() if ln.strip()]
    out = [question] + [v for v in variants if v.lower() != question.lower()]
    return out[:max_variants]


def hyde(question: str, llm) -> str:
    try:
        text = llm("You draft statutory text for use as a search query.",
                   HYDE_PROMPT.format(question=question))
    except Exception:
        return question
    return (text or "").strip() or question
