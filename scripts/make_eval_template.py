#!/usr/bin/env python
"""Bootstrap an evaluation set you then fill in BY HAND.

It samples sections from the corpus, pre-fills the gold label and prints the
section text beside it, so your job is only to read the provision and write a
question a real person would ask. That is the part no script can do for you:
questions written by a model test the model, not the law.

  python scripts/make_eval_template.py --n 60 --out data/eval/todo.jsonl
  # ...fill in "question" and "reference_answer" in that file...
  python scripts/make_eval_template.py --validate data/eval/todo.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import (  # noqa: E402
    TARGET_MIX,
    load_corpus_keys,
    load_eval,
    section_key,
    slice_stats,
    validate,
)

TEMPLATE_TYPES = ["single", "single", "single", "exact_ref", "paraphrase", "multi"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--out", default="data/eval/todo.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--min-chars", type=int, default=200, help="skip trivially short sections")
    ap.add_argument("--validate", metavar="EVAL_FILE", help="check an eval file instead")
    args = ap.parse_args()

    if args.validate:
        items = load_eval(args.validate)
        keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
        problems = validate(items, keys)
        print(json.dumps(slice_stats(items), ensure_ascii=False, indent=2))
        print("\ntarget mix:")
        for k, v in TARGET_MIX.items():
            print(f"  {k}: {v}")
        if problems:
            print(f"\n{len(problems)} problems:")
            for p in problems[:50]:
                print(f"  - {p}")
            sys.exit(1)
        print("\nno problems found.")
        return

    with open(args.chunks, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    sections: dict[str, dict] = {}
    for c in chunks:
        m = c["metadata"]
        if m.get("type") != "section" or len(c["body"]) < args.min_chars:
            continue
        sections.setdefault(section_key(m), c)
    if not sections:
        sys.exit(f"no usable sections in {args.chunks}")

    rng = random.Random(args.seed)
    picked = rng.sample(sorted(sections), min(args.n, len(sections)))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for i, key in enumerate(picked, 1):
            c = sections[key]
            m = c["metadata"]
            f.write(json.dumps({
                "id": f"q{i:03d}",
                "question": "",                       # <- you write this
                "language": m.get("language", "bn"),
                "type": TEMPLATE_TYPES[i % len(TEMPLATE_TYPES)],
                "gold": [key],
                "reference_answer": "",               # <- and this, from the text below
                "note": f"{m['act_title']} {m.get('section_number','')} — {m.get('section_title','')}",
                "_source_text": c["body"][:600],      # remove once written; ignored by the loader
            }, ensure_ascii=False) + "\n")

    print(f"wrote {len(picked)} template rows to {out}")
    print("\nNow, for each row:")
    print("  1. read _source_text and write the question a person would actually ask")
    print("  2. write a one or two sentence reference_answer from the text")
    print("  3. fix 'type' if it doesn't fit; multi-hop rows need a second gold section")
    print("  4. delete _source_text")
    print("\nThen add by hand, because sampling cannot produce them:")
    print("  - ~10% unanswerable questions (gold: [], type: unanswerable)")
    print("  - paraphrases that avoid the words used in the section")
    print("  - questions that name a section number, e.g. 'ধারা ৩০২ কী বলে?'")
    print("  - code-switched questions (Bangla question about an English act)")


if __name__ == "__main__":
    main()
