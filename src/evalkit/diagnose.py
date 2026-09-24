"""Where did it fail? — assigning blame to a stage, automatically.

"recall@5 is 0.63" tells you to work harder. This tells you *what* to work on,
by asking, for every failed question, how far the gold section got:

  not_in_corpus     the gold section is not in the index at all (an ingestion bug,
                    or a mislabelled question — check both)
  retrieval_miss    never appeared, even in the wide candidate pool
  ranking_miss      was in the pool but not in the top k (a reranker problem)
  citation_miss     was in the top k but the answer cited something else
                    (a prompting problem, not a retrieval one)
  answer_miss       cited correctly, but the answer was still wrong
                    (a reasoning or chunking problem)

Four counts, four different weekends of work. This is the report that turns a
failure list into a plan.
"""
from __future__ import annotations

from collections import Counter

from evalkit.dataset import EvalItem

STAGES = ["not_in_corpus", "retrieval_miss", "ranking_miss", "citation_miss",
          "answer_miss", "ok"]


def diagnose_one(item: EvalItem, candidates: list[str], top_k: list[str],
                 cited: list[str] | None = None, answer_correct: bool | None = None,
                 corpus_keys: set[str] | None = None) -> str:
    gold = set(item.gold)
    if not gold:
        return "ok"                                   # unanswerable: judged by refusal instead
    if corpus_keys is not None and not (gold & corpus_keys):
        return "not_in_corpus"
    if not (gold & set(candidates)):
        return "retrieval_miss"
    if not (gold & set(top_k)):
        return "ranking_miss"
    if cited is not None and not (gold & set(cited)):
        return "citation_miss"
    if answer_correct is False:
        return "answer_miss"
    return "ok"


def diagnose(items: list[EvalItem], per_question: dict[str, dict],
             corpus_keys: set[str] | None = None) -> dict:
    """per_question: {id: {"candidates": [...], "top_k": [...], "cited": [...],
                           "answer_correct": bool|None}}"""
    rows = []
    for it in items:
        data = per_question.get(it.id)
        if data is None:
            continue
        stage = diagnose_one(it, data.get("candidates", []), data.get("top_k", []),
                             data.get("cited"), data.get("answer_correct"), corpus_keys)
        rows.append({"id": it.id, "stage": stage, "type": it.type, "language": it.language,
                     "question": it.question})
    counts = Counter(r["stage"] for r in rows)
    failures = [r for r in rows if r["stage"] != "ok"]
    return {
        "counts": {s: counts.get(s, 0) for s in STAGES},
        "by_type": {t: dict(Counter(r["stage"] for r in rows if r["type"] == t))
                    for t in sorted({r["type"] for r in rows})},
        "by_language": {lang: dict(Counter(r["stage"] for r in rows if r["language"] == lang))
                        for lang in sorted({r["language"] for r in rows})},
        "failures": failures,
        "verdict": _verdict(counts, len(rows)),
    }


def _verdict(counts: Counter, total: int) -> str:
    if not total:
        return "nothing to diagnose"
    if counts.get("ok", 0) == total:
        return "no failures on this set — either you are done, or the set is too easy"
    worst = max(("not_in_corpus", "retrieval_miss", "ranking_miss", "citation_miss",
                 "answer_miss"), key=lambda s: counts.get(s, 0))
    share = counts.get(worst, 0) / total
    advice = {
        "not_in_corpus": "fix ingestion or the labels — the text is not indexed",
        "retrieval_miss": "work on retrieval: hybrid search, query expansion, chunking",
        "ranking_miss": "work on ranking: add or fine-tune the reranker, raise candidates",
        "citation_miss": "work on the prompt: the right text was in front of the model",
        "answer_miss": "work on chunking and reasoning: the model had the right text and still missed",
    }[worst]
    return f"biggest bucket: {worst} ({share:.0%} of questions) — {advice}"
