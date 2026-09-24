#!/usr/bin/env python
"""Phase 3b: measure the WHOLE system — retrieval + answer + citations.

Costs one answering call per question, plus one or two judge calls. Run it on
every change you ship, not on every experiment.

  export RAG_LLM=anthropic ANTHROPIC_API_KEY=...
  python scripts/eval_e2e.py --label baseline --judge-provider openai
  python scripts/eval_e2e.py --label baseline-nojudge --no-judge   # deterministic only, free
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.dataset import load_corpus_keys, load_eval, validate  # noqa: E402
from evalkit.judge import deterministic_scores, judge_answer  # noqa: E402
from evalkit.runner import (  # noqa: E402
    print_summary,
    run_precomputed,
    run_retrieval,
    save,
    summarize,
)
from rag.agent import AgentConfig, LegalAgent  # noqa: E402
from rag.answer import answer_question, format_context  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.guardrails import GuardConfig  # noqa: E402
from rag.llm import get_llm  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline, load_records  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", default="data/eval/eval.jsonl")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--no-sandwich", action="store_true")
    add_retrieval_args(ap)
    ap.add_argument("--provider", help="answering LLM (default $RAG_LLM)")
    ap.add_argument("--llm-model")
    ap.add_argument("--judge-provider", help="judge LLM — use a DIFFERENT model than the answerer")
    ap.add_argument("--judge-model")
    ap.add_argument("--no-judge", action="store_true", help="deterministic metrics only")
    ap.add_argument("--min-score", type=float, help="abstain below this retrieval score")
    ap.add_argument("--min-hits", type=int, default=1)
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--allow-uncited", type=float, default=0.34)
    ap.add_argument("--agent", action="store_true", help="evaluate the agentic loop")
    ap.add_argument("--max-steps", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=1,
                    help="run each question N times and report the spread — one run of an "
                         "LLM metric is an anecdote")
    ap.add_argument("--limit", type=int, help="first N questions only (smoke test)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--results", default="results")
    args = ap.parse_args()

    items = load_eval(args.eval)
    keys = load_corpus_keys(args.chunks) if Path(args.chunks).exists() else None
    problems = validate(items, keys)
    if problems:
        for p in problems[:20]:
            print(f"  - {p}")
        sys.exit("fix the evaluation set first")
    if args.limit:
        items = items[: args.limit]

    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)
    llm = get_llm(args.provider, args.llm_model)
    judge = None if args.no_judge else get_llm(args.judge_provider, args.judge_model)
    retriever = build_pipeline(args, args.index, embedder, llm=llm)

    guard = GuardConfig(min_score=args.min_score, min_hits=args.min_hits,
                        max_uncited_ratio=args.allow_uncited, repair=not args.no_repair)
    agent = (LegalAgent(retriever, load_records(args.index, args.chunks), llm,
                        AgentConfig(max_steps=args.max_steps, per_call_k=args.k, guard=guard))
             if args.agent else None)
    search_kw = {}
    generation, answers, evidence = [], [], []
    for n, it in enumerate(items, 1):
      for repeat in range(args.repeats):
        ans = (agent.run(it.question) if agent else
               answer_question(it.question, retriever, llm, k=args.k,
                               sandwich=not args.no_sandwich, guard=guard, **search_kw))
        row = {"id": f"{it.id}#{repeat}" if args.repeats > 1 else it.id,
               **deterministic_scores(it, ans)}
        if agent:
            row["agent_steps"] = float(ans.checks.get("steps", 0))
            row["llm_calls"] = float(ans.llm_calls)
        if judge:
            row.update(judge_answer(it, ans, judge, format_context(ans.hits)))
        generation.append(row)
        evidence.append(ans.hits)
        answers.append({"id": it.id, "repeat": repeat, "question": it.question,
                        "answer": ans.text,
                        "refused": ans.refused, "gold": it.gold,
                        "sources": ans.sources, "latency_s": round(ans.latency_s, 2),
                        "failures": ans.failures, "repaired": ans.repaired,
                        "abstained": ans.abstained, "llm_calls": ans.llm_calls,
                        "trace": ans.checks.get("trace"), "stop_reason": ans.checks.get("stop_reason"),
                        "judge": {k: v for k, v in row.items() if k.startswith("_")}})
        print(f"[{n}/{len(items)}{'.' + str(repeat) if args.repeats > 1 else ''}] {it.id} "
              f"{'REFUSED' if ans.refused else 'answered'} "
              f"faith={row.get('faithfulness', '-')} corr={row.get('correctness', '-')}")

    if agent:
        # The agent's "retrieval" is everything it gathered across its steps.
        from evalkit.dataset import section_key
        retrieved = {}
        for a, hits in zip(answers, evidence, strict=False):
            retrieved.setdefault(a["id"], [section_key(h.metadata) for h in hits])
        run = run_precomputed(items, retrieved, [a["latency_s"] for a in answers], k=args.k)
    else:
        run = run_retrieval(items, retriever, k=args.k, **search_kw)
    config = {"k": args.k, "sandwich": not args.no_sandwich,
              "answer_llm": args.provider or "env",
              "judge_llm": args.judge_provider or ("none" if args.no_judge else "env"),
              "eval": args.eval, "agent": bool(agent), "max_steps": args.max_steps,
              "repeats": args.repeats,
              "min_score": args.min_score,
              "repair": not args.no_repair, **retriever.config.to_dict()}
    summary = summarize(args.label, config, items, run, generation=generation)
    print_summary(summary)
    path = save(summary, run, args.results, args.label, generation=generation)
    (Path(args.results) / f"{args.label}.answers.json").write_text(
        __import__("json").dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved {path} and {args.label}.answers.json "
          f"— read the answers file, that is your failure analysis")


if __name__ == "__main__":
    main()
