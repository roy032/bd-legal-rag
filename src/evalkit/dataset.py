"""The evaluation set.

One JSON object per line:

{
  "id": "q001",
  "question": "হত্যার শাস্তি কী?",
  "language": "bn",                       # bn | en | mixed
  "type": "single",                       # single | multi | exact_ref | unanswerable | paraphrase
  "gold": ["11:3300"],                    # "act_id:section_id" — see note below
  "gold_grades": {"11:3300": 2, "11:3301": 1},   # optional: 2 = answers it, 1 = related
  "reference_answer": "মৃত্যুদণ্ড বা যাবজ্জীবন কারাদণ্ড।",
  "note": "optional: why this question is here"
}

Gold labels point at SECTIONS, not chunks. Chunk ids change every time you
re-chunk; section ids don't. That one decision keeps an evaluation set you
spent a week writing usable for the rest of the project.

An 'unanswerable' item has gold == [] — the corpus genuinely cannot answer it,
and the correct behaviour is to refuse. A system with no unanswerable items in
its evaluation set is one that has never been tested for hallucination.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LANGUAGES = {"bn", "en", "mixed"}
TYPES = {"single", "multi", "exact_ref", "unanswerable", "paraphrase"}


@dataclass
class EvalItem:
    id: str
    question: str
    language: str
    type: str
    gold: list[str] = field(default_factory=list)
    reference_answer: str = ""
    note: str = ""
    # Added after the fields above on purpose: positional construction in older
    # code and tests keeps working.
    gold_grades: dict[str, int] = field(default_factory=dict)

    def grades(self) -> dict[str, int]:
        """Graded relevance, defaulting every gold section to 2 (fully relevant).

        Binary labels are cheap and coarse: a section that gives half the answer
        scores the same as one about a different act. Grading is optional here so
        you can add it to the questions where it matters instead of relabelling
        everything."""
        base = dict.fromkeys(self.gold, 2)
        base.update({k: int(v) for k, v in (self.gold_grades or {}).items()})
        return base

    @property
    def answerable(self) -> bool:
        return self.type != "unanswerable"


def section_key(metadata: dict) -> str:
    """The unit of ground truth: 'act_id:section_id'."""
    return f"{metadata.get('act_id')}:{metadata.get('section_id')}"


def load_eval(path: str | Path) -> list[EvalItem]:
    items = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON — {e}") from e
            items.append(EvalItem(**{k: d[k] for k in d if k in EvalItem.__annotations__}))
    return items


def load_corpus_keys(chunks_path: str | Path) -> set[str]:
    keys = set()
    with open(chunks_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                keys.add(section_key(json.loads(line)["metadata"]))
    return keys


def validate(items: list[EvalItem], corpus_keys: set[str] | None = None) -> list[str]:
    """Return a list of problems. An evaluation set with bad labels is worse
    than none: it makes every later number a lie."""
    problems: list[str] = []
    seen_ids: set[str] = set()
    seen_questions: dict[str, str] = {}
    for it in items:
        where = f"[{it.id}]"
        if not it.id:
            problems.append("an item has no id")
        if it.id in seen_ids:
            problems.append(f"{where} duplicate id")
        seen_ids.add(it.id)
        if not it.question.strip():
            problems.append(f"{where} empty question (template not filled in?)")
        norm_q = " ".join(it.question.split()).lower()
        if norm_q in seen_questions:
            problems.append(f"{where} duplicate question, same as {seen_questions[norm_q]}")
        seen_questions[norm_q] = it.id
        if it.language not in LANGUAGES:
            problems.append(f"{where} language must be one of {sorted(LANGUAGES)}")
        if it.type not in TYPES:
            problems.append(f"{where} type must be one of {sorted(TYPES)}")
        if it.answerable and not it.gold:
            problems.append(f"{where} answerable item with no gold sections")
        if not it.answerable and it.gold:
            problems.append(f"{where} unanswerable item must have gold == []")
        for key, grade in (it.gold_grades or {}).items():
            if grade not in (0, 1, 2):
                problems.append(f"{where} grade for '{key}' must be 0, 1 or 2")
            if grade == 2 and key not in it.gold:
                problems.append(f"{where} '{key}' graded 2 but missing from gold")
        if it.type == "multi" and len(it.gold) < 2:
            problems.append(f"{where} multi-hop item needs at least 2 gold sections")
        if it.answerable and not it.reference_answer.strip():
            problems.append(f"{where} no reference answer (needed to score correctness)")
        for g in it.gold:
            if not (isinstance(g, str) and g.count(":") == 1):
                problems.append(f"{where} gold '{g}' is not in 'act_id:section_id' form")
            elif corpus_keys is not None and g not in corpus_keys:
                problems.append(f"{where} gold '{g}' is not in the corpus")
    return problems


def slice_stats(items: list[EvalItem]) -> dict:
    return {
        "n": len(items),
        "by_language": dict(Counter(i.language for i in items)),
        "by_type": dict(Counter(i.type for i in items)),
        "answerable": sum(i.answerable for i in items),
        "unanswerable": sum(not i.answerable for i in items),
        "multi_gold": sum(len(i.gold) > 1 for i in items),
    }


# What a defensible evaluation set looks like. Print it, aim at it, report the gap.
TARGET_MIX = {
    "n": "150-200 questions",
    "language": "~45% bn, ~45% en, ~10% mixed/code-switched",
    "type": "~50% single, ~15% multi, ~15% exact_ref, ~10% unanswerable, ~10% paraphrase",
    "rule": "written by hand from the real text — not generated by a model",
}
