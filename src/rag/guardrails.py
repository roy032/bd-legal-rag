"""Checks that run on every answer, before the user sees it.

A RAG system fails in four ways that a good prompt alone does not prevent:

  1. It answers from a context that never contained the answer.
     -> support_gate: if retrieval is weak, refuse before calling the model at all.
  2. It states things no excerpt supports.
     -> citation_coverage: every factual sentence must carry a [n].
  3. It invents a quotation. In legal text this is the worst failure: a
     fabricated "operative wording" looks exactly like the real thing.
     -> quote_fidelity: every quoted span must appear verbatim in a cited excerpt.
  4. It answers a Bangla question in English.
     -> language_match.

Everything here is deterministic and free. The LLM judge from Phase 3 grades
quality; these checks enforce a contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.textutils import detect_lang, normalize

from .entail import Entailer, check_claims
from .store import Hit

# Sentence enders in both scripts: Bangla dari, full stop, ?, !, newline.
SENTENCE_SPLIT = re.compile(r"(?<=[।?!.])\s+|\n+")
CITE_RE = re.compile(r"\[(\d{1,2})\]")
# “...” (used throughout the Bangla statutes), "...", «...», '...'
QUOTE_RE = re.compile(r"[“\"«]([^”\"»]{8,300})[”\"»]")
# Sentences that assert nothing: headings, "Sources:", a bare citation line.
TRIVIAL_RE = re.compile(r"^[\s\-–•*#>\d.)\[\]]*$")


@dataclass
class GuardConfig:
    min_score: float | None = None      # abstain if no hit scores at least this
    min_hits: int = 1                   # ...and at least this many do
    require_citations: bool = True
    max_uncited_ratio: float = 0.34     # share of factual sentences without a [n]
    check_quotes: bool = True
    check_language: bool = True
    repair: bool = True                 # one corrective re-prompt when a check fails
    entailer: Entailer | None = None    # set to check that cited text SUPPORTS each claim
    entail_threshold: float = 0.55
    min_support_rate: float = 0.7       # share of claims that must be entailed
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------- pre-generation

def support_gate(hits: list[Hit], cfg: GuardConfig) -> tuple[bool, str]:
    """Decide whether the retrieved context is worth answering from.

    NOTE: scores are not comparable across backends — cosine sits near 0.5,
    BM25 in the tens, fused RRF scores near 0.03. Calibrate min_score for the
    pipeline you actually run (scripts/calibrate_guard.py), or leave it None.
    """
    if not hits:
        return False, "nothing retrieved"
    if cfg.min_score is None:
        return True, ""
    strong = [h for h in hits if h.score >= cfg.min_score]
    if len(strong) < cfg.min_hits:
        return False, (f"weak retrieval: {len(strong)} hit(s) at or above "
                       f"{cfg.min_score} (top score {hits[0].score:.3f})")
    return True, ""


# -------------------------------------------------------------- post-generation

def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text or "") if s.strip()]


def factual_sentences(text: str) -> list[str]:
    """Sentences that make a claim — skip headings, list bullets, source lines."""
    out = []
    for s in split_sentences(text):
        if TRIVIAL_RE.match(s) or s.lower().startswith(("sources:", "source:", "সূত্র:")):
            continue
        if len(s) < 12 and not CITE_RE.search(s):
            continue                      # "Yes." / "ঠিক আছে।" — no claim to support
        out.append(s)
    return out


def citation_coverage(text: str, n_hits: int) -> dict:
    """How much of the answer is actually attributed, and where it isn't."""
    sentences = factual_sentences(text)
    uncited = [s for s in sentences if not CITE_RE.search(s)]
    nums = [int(n) for n in CITE_RE.findall(text or "")]
    return {
        "n_sentences": len(sentences),
        "uncited": uncited,
        "uncited_ratio": len(uncited) / len(sentences) if sentences else 0.0,
        "cited": sorted({n for n in nums if 1 <= n <= n_hits}),
        "invalid": sorted({n for n in nums if not 1 <= n <= n_hits}),
    }


def _searchable(s: str) -> str:
    return re.sub(r"\s+", " ", normalize(s)).strip().lower()


def quote_fidelity(text: str, hits: list[Hit], cited_only: bool = True,
                   cited: list[int] | None = None) -> dict:
    """Every quoted span must appear verbatim in an excerpt that was shown.

    Checked against the cited excerpts by default; a quote that only appears in
    an uncited excerpt is still a miscitation.
    """
    quotes = [q.strip() for q in QUOTE_RE.findall(text or "")]
    if not quotes:
        return {"n_quotes": 0, "fabricated": [], "fidelity": 1.0}
    if cited_only and cited:
        pool = [hits[n - 1] for n in cited if 1 <= n <= len(hits)]
    else:
        pool = hits
    haystack = " ".join(_searchable(h.body) for h in pool)
    fabricated = [q for q in quotes if _searchable(q) not in haystack]
    return {
        "n_quotes": len(quotes),
        "fabricated": fabricated,
        "fidelity": 1 - len(fabricated) / len(quotes),
    }


def language_match(question: str, answer: str) -> bool:
    q, a = detect_lang(question), detect_lang(answer)
    if "unknown" in (q, a) or "mixed" in (q, a):
        return True                       # don't punish what we can't classify
    return q == a


def claims_with_citations(text: str, n_hits: int) -> list[tuple[str, list[int]]]:
    """Each factual sentence paired with the excerpt numbers it cites."""
    out = []
    for sentence in factual_sentences(text):
        cited = [int(n) for n in CITE_RE.findall(sentence) if 1 <= int(n) <= n_hits]
        if cited:
            out.append((CITE_RE.sub("", sentence).strip(), cited))
    return out


def run_checks(question: str, text: str, hits: list[Hit], cfg: GuardConfig) -> dict:
    cov = citation_coverage(text, len(hits))
    quotes = quote_fidelity(text, hits, cited=cov["cited"])
    lang_ok = language_match(question, text) if cfg.check_language else True
    entailment = None
    if cfg.entailer is not None:
        entailment = check_claims(claims_with_citations(text, len(hits)), hits, cfg.entailer,
                                  threshold=cfg.entail_threshold)
    failures = []
    if entailment and entailment["support_rate"] < cfg.min_support_rate:
        failures.append("unsupported_claims")
    if cfg.require_citations and cov["uncited_ratio"] > cfg.max_uncited_ratio:
        failures.append("uncited_sentences")
    if cov["invalid"]:
        failures.append("invalid_citations")
    if cfg.check_quotes and quotes["fabricated"]:
        failures.append("fabricated_quotes")
    if not lang_ok:
        failures.append("language_mismatch")
    return {"coverage": cov, "quotes": quotes, "language_ok": lang_ok,
            "entailment": entailment, "failures": failures}


def repair_instruction(checks: dict) -> str:
    """The corrective message for the single re-prompt."""
    parts = ["Your previous answer failed these checks. Rewrite it, changing nothing else:"]
    cov, quotes = checks["coverage"], checks["quotes"]
    if "uncited_sentences" in checks["failures"]:
        listed = "; ".join(f'"{s[:80]}"' for s in cov["uncited"][:3])
        parts.append(f"- These sentences carry no citation: {listed}. "
                     f"Add the excerpt number they come from, or delete them.")
    if "invalid_citations" in checks["failures"]:
        parts.append(f"- You cited {cov['invalid']}, which do not exist. "
                     f"Use only the numbers shown.")
    if "fabricated_quotes" in checks["failures"]:
        listed = "; ".join(f'"{q[:80]}"' for q in quotes["fabricated"][:3])
        parts.append(f"- These quotations do not appear in the excerpts: {listed}. "
                     f"Quote the exact words from an excerpt, or paraphrase without quotation marks.")
    if "language_mismatch" in checks["failures"]:
        parts.append("- Answer in the same language as the question.")
    if "unsupported_claims" in checks["failures"]:
        listed = "; ".join(f'"{c[:80]}"' for c in (checks.get("entailment") or {})
                           .get("unsupported", [])[:3])
        parts.append(f"- The excerpt you cited does not support these statements: {listed}. "
                     f"Cite the excerpt that actually says it, or remove the statement.")
    parts.append("If the excerpts genuinely do not support an answer, reply with "
                 "NOT_FOUND: <what is missing>.")
    return "\n".join(parts)
