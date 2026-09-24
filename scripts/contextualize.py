#!/usr/bin/env python
"""Contextual retrieval: give every chunk a sentence of context before embedding.

A chunk that reads "(2) The fine shall not exceed fifty thousand taka." matches
almost nothing, because the words that make it findable — which act, which
offence — are in the section around it. This asks a cheap model, once per chunk,
to write one line of context, and prepends it to the embedded text.

It costs one call per chunk at build time and nothing at query time. Published
results elsewhere report double-digit recall gains; whether that holds on Bangla
statutes is exactly the kind of question your ablation table can answer.

  export RAG_LLM=ollama          # a cheap local model is ideal for this
  python scripts/contextualize.py --in data/processed/chunks.jsonl \
         --out data/processed/chunks_ctx.jsonl
  python scripts/build_index.py --chunks data/processed/chunks_ctx.jsonl --out data/index_ctx --bm25
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.llm import get_llm  # noqa: E402

PROMPT = """Here is a chunk from a Bangladeshi Act:

<chunk>
{chunk}
</chunk>

It comes from: {context}

Write ONE short sentence, in the same language as the chunk, that situates this
chunk for search: which act, which provision, and what it is about. No preamble,
no quotation marks, just the sentence."""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default="data/processed/chunks.jsonl")
    ap.add_argument("--out", default="data/processed/chunks_ctx.jsonl")
    ap.add_argument("--provider", help="default $RAG_LLM — use a cheap model")
    ap.add_argument("--limit", type=int, help="first N chunks (try it before paying for all)")
    ap.add_argument("--skip-short", type=int, default=200,
                    help="chunks shorter than this keep their existing header only")
    args = ap.parse_args()

    llm = get_llm(args.provider)
    rows = [json.loads(line) for line in Path(args.inp).read_text(encoding="utf-8").splitlines()
            if line.strip()]
    if args.limit:
        rows = rows[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = enriched = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows, 1):
            m = row["metadata"]
            if len(row["body"]) >= args.skip_short and m.get("type") == "section":
                context = (f"{m.get('act_title')} — {m.get('chapter') or ''} "
                           f"section {m.get('section_number')} ({m.get('section_title')})")
                try:
                    line = llm("You write one-line search context for legal text.",
                               PROMPT.format(chunk=row["body"][:1500], context=context)).strip()
                except Exception as e:
                    line = ""
                    print(f"  [{i}] context failed: {e}")
                if line:
                    row["text"] = f"{line}\n\n{row['text']}"
                    row["metadata"] = {**m, "contextualized": True}
                    enriched += 1
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
            if i % 100 == 0:
                print(f"  {i}/{len(rows)}")
    print(f"wrote {written} chunks ({enriched} contextualised) to {out_path}")
    print("Now build a second index from it and compare — that is the whole point.")


if __name__ == "__main__":
    main()
