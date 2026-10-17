#!/usr/bin/env python
"""Turn thumbs-down answers from the service into draft evaluation questions.

Every "No" a visitor clicks is a question the system got wrong, in the visitor's own
words: the best material there is for the evaluation set. This writes them as drafts
in the eval format, without gold sections (only a person who reads the law can pick
those), next to what the system cited and the visitor's comment.

  bdrag feedback-to-eval                                  # data/feedback.jsonl
  bdrag feedback-to-eval --since 2026-10-01 --out data/eval/feedback_drafts.jsonl

Review each draft: fill "gold" with act_id:section_id keys and "reference_answer",
or delete it; then move the finished ones into an eval file and run `bdrag eval`.
Questions already in an eval file, or already drafted, are skipped.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from evalkit.dataset import load_eval
from ingest.textutils import nfc
from rag.query import script_language


def norm(q: str) -> str:
    return " ".join(nfc(q).lower().split())


def known_questions(eval_dir: Path) -> set[str]:
    seen: set[str] = set()
    for path in eval_dir.glob("*.jsonl"):
        try:
            seen |= {norm(it.question) for it in load_eval(path)}
        except Exception:                    # drafts without gold do not load as an eval set
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    seen.add(norm(json.loads(line).get("question", "")))
    return seen


def drafts(rows: list[dict], seen: set[str], since: float = 0.0) -> list[dict]:
    out: list[dict] = []
    for r in rows:
        q = (r.get("question") or "").strip()
        if r.get("rating") != "down" or not q or r.get("ts", 0) < since or norm(q) in seen:
            continue
        seen.add(norm(q))
        out.append({
            "id": f"fb-{r.get('id') or len(out)}", "question": q,
            "language": script_language(q), "type": "single", "gold": [],
            "reference_answer": "",
            "note": "from visitor feedback; needs gold sections and a reference answer",
            "visitor_comment": r.get("comment") or "", "system_cited": r.get("sources") or [],
            "system_answer": (r.get("answer") or "")[:600], "failures": r.get("failures") or [],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feedback", default="data/feedback.jsonl")
    ap.add_argument("--eval-dir", default="data/eval")
    ap.add_argument("--out", default="data/eval/feedback_drafts.jsonl")
    ap.add_argument("--since", help="only feedback on or after this date (YYYY-MM-DD)")
    args = ap.parse_args()

    path = Path(args.feedback)
    if not path.exists():
        raise SystemExit(f"no feedback yet at {path} (the service writes it when visitors click Yes/No)")
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    since = time.mktime(time.strptime(args.since, "%Y-%m-%d")) if args.since else 0.0
    new = drafts(rows, known_questions(Path(args.eval_dir)), since)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", encoding="utf-8") as f:
        for d in new:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    down = sum(r.get("rating") == "down" for r in rows)
    print(f"{len(rows)} feedback rows, {down} thumbs-down, {len(new)} new drafts -> {out}")


if __name__ == "__main__":
    main()
