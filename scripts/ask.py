#!/usr/bin/env python
"""Phase 2b: ask a question.

  export RAG_LLM=anthropic ANTHROPIC_API_KEY=...        # or openai / ollama
  python scripts/ask.py "ভাড়াটিয়া উচ্ছেদের নিয়ম কী?"
  python scripts/ask.py "What is the punishment for murder?" -k 8 --show-context
  python scripts/ask.py --interactive
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag.agent import AgentConfig, LegalAgent  # noqa: E402
from rag.answer import answer_question, format_context  # noqa: E402
from rag.chat import ChatSession  # noqa: E402
from rag.embed import get_embedder  # noqa: E402
from rag.guardrails import GuardConfig  # noqa: E402
from rag.llm import get_llm  # noqa: E402
from rag.pipeline import add_retrieval_args, build_pipeline, load_records  # noqa: E402

DISCLAIMER = "Informational only — this is not legal advice. Always verify against the official text."


def render(ans, show_context: bool) -> str:
    out = [ans.text, ""]
    if show_context:
        out += ["--- retrieved context ---", format_context(ans.hits), ""]
    if ans.sources:
        out.append("Sources:")
        out += [f"  [{s['n']}] {s['citation']}  ({s['score']})  {s['url']}" for s in ans.sources]
    if ans.checks.get("rewritten_query"):
        out.append(f"  (searched for: {ans.checks['rewritten_query']})")
    if ans.failures:
        out.append(f"  !! guardrail failures: {', '.join(ans.failures)}")
        for sentence in ans.checks.get("coverage", {}).get("uncited", [])[:3]:
            out.append(f"     uncited: {sentence[:100]}")
        for quote in ans.checks.get("quotes", {}).get("fabricated", [])[:3]:
            out.append(f"     not in any excerpt: \u201c{quote[:100]}\u201d")
    if ans.repaired:
        out.append("  (answer was re-prompted once to fix a failed check)")
    if ans.abstained:
        out.append("  (refused before calling the model — retrieval was too weak)")
    uncited = [n for n in range(1, len(ans.hits) + 1) if n not in ans.cited]
    if uncited and not ans.refused:
        out.append(f"  (retrieved but not cited: {uncited})")
    if ans.invalid_citations:
        out.append(f"  !! hallucinated citation numbers: {ans.invalid_citations}")
    out.append(f"\n{ans.latency_s:.2f}s · {DISCLAIMER}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question", nargs="*")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--embedder", choices=["auto", "st", "hashing"], default="auto",
                    help="auto = the embedder the index was built with")
    ap.add_argument("--model", default="BAAI/bge-m3")
    ap.add_argument("--provider", help="anthropic | openai | ollama | echo (default: $RAG_LLM)")
    ap.add_argument("--llm-model", help="override $RAG_MODEL")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--language", choices=["bn", "en"], help="restrict to acts in this language")
    ap.add_argument("--act-id", type=int)
    add_retrieval_args(ap)
    ap.add_argument("--no-sandwich", action="store_true", help="keep plain relevance order")
    ap.add_argument("--min-score", type=float,
                    help="abstain when retrieval is weaker than this (calibrate it — "
                         "cosine, BM25 and fused scores live on different scales)")
    ap.add_argument("--min-hits", type=int, default=1)
    ap.add_argument("--no-repair", action="store_true", help="skip the corrective re-prompt")
    ap.add_argument("--allow-uncited", type=float, default=0.34,
                    help="tolerated share of sentences without a citation")
    ap.add_argument("--agent", action="store_true",
                    help="let the model search repeatedly and follow cross-references")
    ap.add_argument("--max-steps", type=int, default=5, help="agent action budget")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl",
                    help="fallback source of chunk records for exact section lookup")
    ap.add_argument("--show-trace", action="store_true", help="print what the agent did")
    ap.add_argument("--show-context", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    embedder = get_embedder(args.embedder, model=args.model, index_dir=args.index)
    llm = get_llm(args.provider, args.llm_model)
    retriever = build_pipeline(args, args.index, embedder, llm=llm)
    guard = GuardConfig(min_score=args.min_score, min_hits=args.min_hits,
                        max_uncited_ratio=args.allow_uncited, repair=not args.no_repair)

    agent = (LegalAgent(retriever, load_records(args.index, args.chunks), llm,
                        AgentConfig(max_steps=args.max_steps, per_call_k=args.k, guard=guard))
             if args.agent else None)

    session = ChatSession(retriever, llm, k=args.k, guard=guard,
                          sandwich=not args.no_sandwich,
                          search_kw={"language": args.language, "act_id": args.act_id})

    def run(q: str, use_history: bool = False) -> None:
        if agent:
            ans = agent.run(q)
            if args.show_trace:
                for t in ans.checks.get("trace", []):
                    print(f"  step {t['step']}: {t.get('tool', t['type'])} "
                          f"{t.get('args', '')} -> +{t.get('new_excerpts', 0)}")
                print(f"  stopped: {ans.checks.get('stop_reason')} · "
                      f"{ans.llm_calls} LLM calls · {ans.checks.get('evidence', 0)} excerpts\n")
            print(render(ans, args.show_context))
            return
        ans = (session.ask(q) if use_history else
               answer_question(q, retriever, llm, k=args.k, sandwich=not args.no_sandwich,
                               guard=guard, language=args.language, act_id=args.act_id))
        if args.json:
            print(json.dumps({"question": q, "answer": ans.text, "refused": ans.refused,
                              "abstained": ans.abstained, "repaired": ans.repaired,
                              "failures": ans.failures, "sources": ans.sources,
                              "llm_calls": ans.llm_calls,
                              "latency_s": round(ans.latency_s, 3)},
                             ensure_ascii=False, indent=2))
        else:
            print(render(ans, args.show_context))

    if args.interactive:
        print("Ask a question (blank line to quit; follow-ups understand the conversation).")
        while (q := input("\n> ").strip()):
            run(q, use_history=True)
    elif args.question:
        run(" ".join(args.question))
    else:
        ap.error("give a question or use --interactive")


if __name__ == "__main__":
    main()
