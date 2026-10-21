#!/usr/bin/env python
"""Prompt-injection and personal-data red team (evalkit/redteam.py).

  bdrag redteam                                   # static checks, free, what CI runs
  bdrag redteam --provider ollama --llm-model gemma4:e4b --index data/index
                                                  # also check what the model says

Exits 1 when a static check fails, and with --strict when a model answer does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evalkit.redteam import load_set, output_failures, static_failures, summarize


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default="data/eval/redteam.jsonl")
    ap.add_argument("--provider", help="answering model; omit (or echo) for static checks only")
    ap.add_argument("--llm-model")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--strict", action="store_true", help="fail on model answers too")
    ap.add_argument("--json-out", help="write every row's result here")
    args = ap.parse_args()

    items = load_set(args.set)
    answer = None
    system_prompt = ""
    if args.provider and args.provider != "echo":
        from rag.answer import SYSTEM, answer_question
        from rag.embed import embedder_for
        from rag.guardrails import GuardConfig
        from rag.llm import LLMError, get_llm
        from rag.pii import redact
        from rag.pipeline import RetrievalConfig, build_pipeline

        system_prompt = SYSTEM
        llm = get_llm(args.provider, args.llm_model)
        retriever = build_pipeline(RetrievalConfig(), args.index,
                                   embedder_for("dense", args.embedder, args.model, args.index),
                                   llm=llm)

        def answer(question: str) -> str:
            # As the service does: personal data is replaced before anything sees it.
            try:
                return answer_question(redact(question)[0], retriever, llm, k=args.k,
                                       guard=GuardConfig()).text
            except LLMError as e:
                return f"[model error: {e}]"

    results, static_bad, output_bad = [], 0, 0
    for it in items:
        failures = static_failures(it)
        static_bad += bool(failures)
        text = None
        if answer is not None:
            text = answer(it.question)
            # The answer is checked for the original personal data, not the placeholder.
            model_fail = output_failures(it, text, system_prompt)
            output_bad += bool(model_fail)
            failures += model_fail
        results.append({"id": it.id, "attack": it.attack, "language": it.language,
                        "failures": failures, "answer": text})
        print(f"{it.id} {it.attack:<12} {'ok' if not failures else 'FAIL: ' + '; '.join(failures)}")

    summary = summarize(results)
    print(f"\n{summary['passed']}/{summary['n']} passed  "
          + "  ".join(f"{k} {v}" for k, v in summary["by_attack"].items()))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"summary": summary, "results": results},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    if static_bad or (args.strict and output_bad):
        sys.exit(1)


if __name__ == "__main__":
    main()
