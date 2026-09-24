"""Generation quality.

Two kinds of check, and the difference matters:

DETERMINISTIC (free, exact, run on every answer)
  refusal_correct      unanswerable question -> refused; answerable -> answered
  citation_validity    every [n] points at a real excerpt
  citation_precision   share of cited excerpts that are gold sections
  gold_cited           the gold section was actually cited, not merely retrieved
  citation_coverage    share of factual sentences that carry a citation
  quote_fidelity       share of quoted spans that appear verbatim in a cited excerpt
  language_match       Bangla question answered in Bangla
  guard_repaired       the answer needed a corrective re-prompt
  clean_first_pass     the first answer passed every check

LLM-AS-JUDGE (costs money, approximate, needs spot-checking)
  faithfulness   is every claim supported by the excerpts shown? (hallucination)
  correctness    does it match the reference answer? (0 / 0.5 / 1)

Judge with a different model than the one that answered, keep temperature 0,
and hand-check ~20 judgements yourself. A judge you have never audited is just
a second opinion from the same kind of machine.
"""
from __future__ import annotations

import json
import re

from evalkit.dataset import EvalItem, section_key

FAITHFULNESS_PROMPT = """You are grading a legal answer for FAITHFULNESS only.

Excerpts shown to the answering system:
---
{context}
---
Answer:
---
{answer}
---

Is every factual claim in the answer supported by the excerpts? Ignore whether
the answer is complete or helpful; judge only support. A refusal ("NOT_FOUND")
is faithful by definition.

Reply with JSON only:
{{"faithful": true|false, "unsupported_claims": ["..."], "reason": "one sentence"}}"""

CORRECTNESS_PROMPT = """You are grading a legal answer against a reference answer.

Question: {question}
Reference answer: {reference}
System answer: {answer}

Score:
  1   = same substance as the reference (wording may differ)
  0.5 = partially correct, or correct but missing a key part
  0   = wrong, or says it cannot answer when the reference answers it

Reply with JSON only:
{{"score": 1|0.5|0, "reason": "one sentence"}}"""

JSON_RE = re.compile(r"\{.*\}", re.S)


def _parse_json(text: str) -> dict:
    m = JSON_RE.search(text or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def deterministic_scores(item: EvalItem, answer, ) -> dict:
    """`answer` is a rag.answer.Answer."""
    gold = set(item.gold)
    retrieved_keys = [section_key(h.metadata) for h in answer.hits]
    cited_keys = [section_key(answer.hits[n - 1].metadata) for n in answer.cited
                  if 1 <= n <= len(answer.hits)]

    scores = {
        "refusal_correct": float(answer.refused != item.answerable),
        "citation_validity": float(not answer.invalid_citations),
        "n_citations": float(len(answer.cited)),
    }
    checks = getattr(answer, "checks", {}) or {}
    if checks and not answer.refused:
        cov, quotes = checks.get("coverage", {}), checks.get("quotes", {})
        scores["citation_coverage"] = 1.0 - cov.get("uncited_ratio", 0.0)
        scores["quote_fidelity"] = quotes.get("fidelity", 1.0)
        scores["language_match"] = float(checks.get("language_ok", True))
        scores["clean_first_pass"] = float(not getattr(answer, "repaired", False)
                                           and not checks.get("failures"))
    scores["guard_repaired"] = float(getattr(answer, "repaired", False))
    scores["abstained"] = float(getattr(answer, "abstained", False))
    if item.answerable:
        scores["gold_retrieved"] = float(bool(gold & set(retrieved_keys)))
        scores["gold_cited"] = float(bool(gold & set(cited_keys)))
        scores["citation_precision"] = (
            sum(c in gold for c in cited_keys) / len(cited_keys) if cited_keys else 0.0
        )
    return scores


def judge_answer(item: EvalItem, answer, judge_llm, context: str) -> dict:
    """LLM-as-judge. `judge_llm` is a rag.llm LLM callable."""
    out: dict = {}
    f = _parse_json(judge_llm("You grade strictly and reply with JSON only.",
                              FAITHFULNESS_PROMPT.format(context=context, answer=answer.text)))
    out["faithfulness"] = float(bool(f.get("faithful")))
    out["_unsupported"] = f.get("unsupported_claims", [])
    out["_faithfulness_reason"] = f.get("reason", "")

    if item.answerable and item.reference_answer:
        c = _parse_json(judge_llm("You grade strictly and reply with JSON only.",
                                  CORRECTNESS_PROMPT.format(question=item.question,
                                                            reference=item.reference_answer,
                                                            answer=answer.text)))
        try:
            out["correctness"] = float(c.get("score", 0))
        except (TypeError, ValueError):
            out["correctness"] = 0.0
        out["_correctness_reason"] = c.get("reason", "")
    return out
