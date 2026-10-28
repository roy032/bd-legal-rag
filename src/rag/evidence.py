"""What a reader needs to check an answer without trusting it.

Three things, all deterministic and free (no model call):

  claim map   each statement of the answer, the excerpts it cites, and whether
              those excerpts plausibly say it: "linked" (the cited text shares
              the statement's words and every number in it), "check" (it does
              not, so the reader should read the section), "uncited".
  evidence    for each cited excerpt, the clause(s) the answer leaned on, so the
              UI can highlight them inside the section instead of leaving the
              reader to find the sentence in a long provision.
  provenance  where each excerpt comes from and how current it is: the official
              act page, the day the text was copied from the site, and the year
              of the newest amendment the copy reflects.

The word-overlap test is a screen, not a proof: "linked" means the reader will
find the words there, not that a lawyer has checked the inference. When the
service runs an entailment model (GuardConfig.entailer) its verdict wins.
"""
from __future__ import annotations

import re
import time

from ingest.textutils import bn_to_ascii_digits, detect_lang

from .guardrails import CITE_RE, QUOTE_RE, factual_sentences, split_tips
from .store import Hit

PUBLISHER = "Laws of Bangladesh (bdlaws.minlaw.gov.bd), Legislative and Parliamentary Affairs Division"

_WORD = re.compile(r"[A-Za-z0-9ঀ-৿]+")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?![\w])")
_YEAR = re.compile(r"(?<![0-9০-৯])([12০১২][0-9০-৯]{3})(?![0-9০-৯])")
# Clause boundaries inside a provision: sentence ends, semicolons, and the
# "(1)", "(ক)" sub-section markers both scripts use.
_CLAUSE = re.compile(r"(?<=[।.;:])\s+|\n+|\s+(?=\((?:[0-9০-৯]{1,3}|[a-z]{1,3}|[ক-হ])\)\s)")
_STOP_EN = """a an the of to in on at by for from with and or but not no is are was were be
been being this that these those it its as any such shall may will can under which who whom
whose what when where how if than then there their they he she his her him them you your i we
our section sections act article excerpt"""
_STOP_BN = """এবং ও বা যে যা এই সেই তবে কোন কোনো করা করে হয় হবে হইবে হইলে থাকে কিংবা অথবা জন্য দ্বারা
তাহার তার তাহা উক্ত এমন কেবল মধ্যে পর্যন্ত সহিত সাথে সঙ্গে ধারা অনুচ্ছেদ আইন"""
_STOP = frozenset(_STOP_EN.split()) | frozenset(_STOP_BN.split())

# Below this share of a statement's words found in its cited excerpts, the
# reader is asked to check the section. A paraphrase keeps the provision's key
# nouns and verbs ("punished", "imprisonment", "seven years"), so it clears a
# third easily; a statement citing the wrong excerpt shares almost nothing.
LINK_MIN_OVERLAP = 0.34


def _stem(word: str) -> str:
    """Six characters is enough to merge English inflections ("punish-ed/-ment")
    and Bangla case endings ("শাস্তি-র/-তে") without merging unrelated words."""
    w = bn_to_ascii_digits(word).lower()
    return w[:6] if len(w) > 6 else w


def content_stems(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text or ""):
        lw = bn_to_ascii_digits(w).lower()
        if lw in _STOP or w in _STOP or (len(w) < 3 and not lw.isdigit()):
            continue
        out.add(_stem(w))
    return out


def numbers_in(text: str) -> set[str]:
    """Amounts, durations and section numbers, digits normalised ("৫০,০০০" -> "50000")."""
    flat = bn_to_ascii_digits(CITE_RE.sub(" ", text or ""))
    return {re.sub(r"[,]", "", n).rstrip(".") for n in _NUMBER.findall(flat)}


def _found(stem: str, pool: set[str]) -> bool:
    """In the pool as is, or as a prefix either way when the shorter has 4+
    characters: Bangla inflects by suffix ("হত্যা" / "হত্যার" / "হত্যাকারী")."""
    if stem in pool:
        return True
    return len(stem) >= 4 and any(p.startswith(stem) or (len(p) >= 4 and stem.startswith(p))
                                  for p in pool)


def share_found(want: set[str], pool: set[str]) -> float:
    return sum(_found(w, pool) for w in want) / len(want) if want else 1.0


def overlap(claim: str, passage: str) -> float:
    return share_found(content_stems(claim), content_stems(passage))


def clauses(body: str, max_chars: int = 320) -> list[str]:
    parts = [p.strip() for p in _CLAUSE.split(body or "") if p and p.strip()]
    return [p if len(p) <= max_chars else p[:max_chars].rsplit(" ", 1)[0] for p in parts]


def best_clause(claim: str, body: str) -> tuple[str, float]:
    """The clause of `body` that shares most words with `claim`, verbatim."""
    best, score = "", 0.0
    want = content_stems(claim)
    if not want:
        return best, score
    for c in clauses(body):
        s = share_found(want, content_stems(c))
        # On a tie the longer clause wins: the operative words, not the heading.
        if s > score or (s == score and s > 0 and len(c) > len(best)):
            best, score = c, s
    return best, round(score, 3)


def claim_map(text: str, hits: list[Hit], entailment: dict | None = None) -> list[dict]:
    """One row per factual statement of the grounded part of an answer.

    The trailing practical-tips list is skipped: it is allowed to be uncited
    and is checked separately for law creeping into it (guardrails.law_in_tips).
    """
    grounded = split_tips(text or "")[0]
    by_claim = {r["claim"]: r for r in (entailment or {}).get("claims", [])}
    rows = []
    for sentence in factual_sentences(grounded):
        cites = sorted({int(n) for n in CITE_RE.findall(sentence) if 1 <= int(n) <= len(hits)})
        plain = re.sub(r"\s+([.।,;:])", r"\1", CITE_RE.sub("", sentence)).strip()
        row: dict = {"text": plain, "cites": cites}
        if not cites:
            row.update(status="uncited", why="no section cited")
            rows.append(row)
            continue
        # The heading counts: "section 302 of the Penal Code, 1860" names numbers
        # that are in the citation, not in the provision's body.
        cited_text = " ".join(f"{hits[n - 1].citation} {hits[n - 1].metadata.get('section_title') or ''}"
                              f"\n{hits[n - 1].body}" for n in cites)
        score = overlap(plain, cited_text)
        missing = sorted(numbers_in(plain) - numbers_in(cited_text) - {str(n) for n in cites})
        # An English answer from a Bangla-only act shares no words with it by
        # construction; there only the numbers can be checked.
        langs = {detect_lang(plain), detect_lang(" ".join(hits[n - 1].body for n in cites))}
        same_script = langs <= {"bn", "mixed"} or langs <= {"en", "mixed"}
        ent = by_claim.get(CITE_RE.sub("", sentence).strip())   # guardrails' key for it
        if ent is not None:
            ok, why = ent["supported"], "the cited section may not say this"
        elif missing:
            ok, why = False, "a number is not in the cited section: " + ", ".join(missing[:3])
        elif not same_script:
            ok, why = True, ""
        else:
            ok, why = score >= LINK_MIN_OVERLAP, "the cited section shares few words with this"
        row.update(status="linked" if ok else "check", overlap=round(score, 3))
        if not ok:
            row["why"] = why
        rows.append(row)
    return rows


def evidence_spans(rows: list[dict], hits: list[Hit], min_score: float = 0.25,
                   per_source: int = 3) -> dict[int, list[str]]:
    """{excerpt number: [clauses quoted from it]} — what to highlight in each source."""
    out: dict[int, list[str]] = {}
    for row in rows:
        for n in row.get("cites", []):
            clause, score = best_clause(row["text"], hits[n - 1].body)
            spans = out.setdefault(n, [])
            if clause and score >= min_score and clause not in spans and len(spans) < per_source:
                spans.append(clause)
    return out


def summarize(rows: list[dict], text: str, quotes: dict | None = None) -> dict:
    counts = {s: sum(r["status"] == s for r in rows) for s in ("linked", "check", "uncited")}
    n_quotes = (quotes or {}).get("n_quotes", len(QUOTE_RE.findall(text or "")))
    fabricated = len((quotes or {}).get("fabricated", []))
    return {"statements": len(rows), **counts,
            "quotes": n_quotes, "quotes_verbatim": max(n_quotes - fabricated, 0)}


def verdict(refused: bool, general: bool, off_topic: bool, rows: list[dict]) -> str:
    """One word for what kind of answer this is, so no reader mistakes one for another.

      grounded          every statement cites a section that plausibly says it
      partly_grounded   some statements are uncited or need checking
      general_guidance  the law text had nothing; general information, cites nothing
      not_found         the law text had nothing and the service says so
      off_topic         not a question about Bangladeshi law
    """
    if off_topic:
        return "off_topic"
    if general:
        return "general_guidance"
    if refused:
        return "not_found"
    if not rows or any(r["status"] != "linked" for r in rows):
        return "partly_grounded"
    return "grounded"


# ----------------------------------------------------------------- provenance

def latest_amendment_year(metadata: dict) -> int | None:
    years = [int(bn_to_ascii_digits(y)) for note in metadata.get("footnotes") or []
             for y in _YEAR.findall(note)]
    years = [y for y in years if 1800 <= y <= 2100]
    return max(years) if years else None


def act_url(metadata: dict) -> str | None:
    """The act's own page on the official site (its table of contents)."""
    url, aid = metadata.get("url") or "", metadata.get("act_id")
    if aid is None or "/act-" not in url:
        return None
    return url.split("/act-")[0] + f"/act-{aid}.html"


def day(ts: float | None) -> str | None:
    return time.strftime("%Y-%m-%d", time.gmtime(ts)) if ts else None


def provenance(metadata: dict, index_built: float | None = None) -> dict:
    """Where an excerpt comes from and how current it is.

    `as_of` is the day the page was copied from the official site, when the
    ingest recorded it (`fetched`), else the day the index was built, with
    `as_of_kind` saying which, so the UI never presents one as the other.
    """
    fetched = metadata.get("fetched")
    out = {"publisher": PUBLISHER, "act_url": act_url(metadata),
           "act_number": metadata.get("act_number"), "act_year": metadata.get("act_year"),
           "last_amended": latest_amendment_year(metadata),
           "as_of": fetched or day(index_built),
           "as_of_kind": "fetched" if fetched else ("index" if index_built else None)}
    if metadata.get("repealed") and metadata.get("repeal_note"):
        out["repeal_note"] = metadata["repeal_note"]
    return out


def acts_table(records: list[dict], index_built: float | None = None) -> list[dict]:
    """Every act in the index, with its source and how current our copy is.

    Section-level amendment years roll up to the act: the newest amendment any
    of its sections reflects is the act's "last amended".
    """
    acts: dict[int, dict] = {}
    for r in records:
        m = r.get("metadata") or {}
        aid = m.get("act_id")
        if aid is None:
            continue
        a = acts.setdefault(aid, {"act_id": aid, "title": m.get("act_title"),
                                  "act_number": m.get("act_number"), "year": m.get("act_year"),
                                  "language": m.get("language"), "repealed": bool(m.get("repealed")),
                                  "url": None, "sections": set(), "amended_sections": 0,
                                  "last_amended": None, "fetched": None})
        if m.get("type") == "act_overview":
            a["url"] = m.get("url") or a["url"]
            continue
        a["url"] = a["url"] or act_url(m)
        if m.get("section_id") is not None:
            a["sections"].add(m["section_id"])
        if m.get("part", 1) == 1 and m.get("amended"):
            a["amended_sections"] += 1
        y = latest_amendment_year(m)
        if y and (a["last_amended"] is None or y > a["last_amended"]):
            a["last_amended"] = y
        f = m.get("fetched")
        if f and (a["fetched"] is None or f > a["fetched"]):
            a["fetched"] = f
    built = day(index_built)
    rows = []
    for a in acts.values():
        a["sections"] = len(a["sections"])
        a["as_of"], a["as_of_kind"] = ((a["fetched"], "fetched") if a["fetched"] else
                                       (built, "index") if built else (None, None))
        del a["fetched"]
        rows.append(a)
    rows.sort(key=lambda a: (a["repealed"], str(a["title"] or "")))
    return rows
