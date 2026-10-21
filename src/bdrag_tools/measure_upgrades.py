#!/usr/bin/env python
"""Measure the October 2026 upgrades on the full index, on this machine, for free.

  bdrag measure-upgrades                    # retrieval variants + scenario answers
  bdrag measure-upgrades --e2e full         # also answer all 86 test questions (hours on CPU)
  bdrag measure-upgrades --e2e none         # retrieval only

Retrieval, on the test set (eval.jsonl), the scenario set (eval_scenarios.jsonl) and
the paraphrased gap set (eval_gaps.jsonl):
  served          the configuration the service uses today
  +translate      also search the question in the other language (one local model call)
  +rerank         bge-reranker-v2-m3 over the top 20 (int8, or bf16 where the CPU has it)
  +both
End to end: the answering model (default gemma4:e4b on Ollama) on the scenario set;
judged by a free hosted model when GROQ_API_KEY is set, deterministic metrics otherwise.

Results written before 2026-10-20 measured `served` without the topic table, which
the service has used since 1.1.0: re-run with --redo.

Writes results/upg-*.json and a table in results/UPGRADES.md. Needs data/index,
data/processed/chunks.jsonl and Ollama running with the model pulled.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SERVED = ["--mode", "dense", "--expand-refs", "--synonyms", "--transliterate", "--resolve-refs",
          "--boost-in-force", "--topics", "--max-parts-per-section", "2"]
VARIANTS = {
    "served": [],
    "translate": ["--translate"],
    "rerank": ["--rerank", "cross", "--rerank-top", "20"],
    "both": ["--translate", "--rerank", "cross", "--rerank-top", "20"],
}
SETS = {"test": "data/eval/eval.jsonl", "scenarios": "data/eval/eval_scenarios.jsonl",
        "gaps": "data/eval/eval_gaps.jsonl"}


def run(args: list[str]) -> bool:
    print("$ " + " ".join(args), flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run(args, env=env).returncode == 0


def load(results: Path, label: str) -> dict | None:
    p = results / f"{label}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cell(summary: dict | None, metric: str) -> str:
    if not summary or metric not in summary.get("overall", {}):
        return "-"
    s = summary["overall"][metric]
    return f"{s['mean']:.3f} [{s['lo']:.2f}–{s['hi']:.2f}]"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--provider", default=os.environ.get("RAG_LLM") or "ollama")
    ap.add_argument("--llm-model", default=os.environ.get("RAG_MODEL") or "gemma4:e4b")
    ap.add_argument("--precision", default="auto", help="reranker precision: auto | int8 | bf16 | fp32")
    ap.add_argument("--e2e", choices=["scenarios", "full", "none"], default="scenarios")
    ap.add_argument("--results", default="results")
    ap.add_argument("--redo", action="store_true", help="re-run variants that already have results")
    args = ap.parse_args()

    results = Path(args.results)
    if not Path(args.index, "index.json").exists():
        sys.exit(f"no index in {args.index}: build it or `bdrag sync pull` it first")
    py = sys.executable
    common = ["--index", args.index, "--chunks", args.chunks, "--results", args.results]
    llm = ["--provider", args.provider, "--llm-model", args.llm_model]

    for set_name, path in SETS.items():
        for name, extra in VARIANTS.items():
            label = f"upg-{set_name}-{name}"
            if load(results, label) and not args.redo:
                continue
            if "--rerank" in extra:
                extra = [*extra, "--rerank-precision", args.precision]
            run([py, "-m", "bdrag_tools.eval_retrieval", "--eval", path, "-k", "10",
                 "--label", label, *common, *SERVED, *extra, *llm])

    e2e_sets = {"none": [], "scenarios": ["scenarios"], "full": ["scenarios", "test"]}[args.e2e]
    judge = (["--judge-provider", "groq"] if os.environ.get("GROQ_API_KEY") else ["--no-judge"])
    for set_name in e2e_sets:
        label = f"upg-e2e-{set_name}-{args.llm_model.replace(':', '-').replace('/', '-')}"
        if load(results, label) and not args.redo:
            continue
        run([py, "-m", "bdrag_tools.eval_e2e", "--eval", SETS[set_name], "-k", "5", "--label", label,
             *common, *SERVED, "--translate", *llm, *judge])

    lines = [f"# Upgrade measurements ({time.strftime('%Y-%m-%d')})", "",
             "Retrieval, k=10, 95% bootstrap intervals. `served` is today's service configuration.", ""]
    for set_name in SETS:
        lines += [f"## {set_name}", "", "| variant | recall@5 | recall@10 | MRR | p95 latency (s) |",
                  "|---|---|---|---|---|"]
        for name in VARIANTS:
            s = load(results, f"upg-{set_name}-{name}")
            p95 = f"{s['latency_s']['p95']:.1f}" if s else "-"
            lines.append(f"| {name} | {cell(s, 'recall@5')} | {cell(s, 'recall@10')} | "
                         f"{cell(s, 'mrr')} | {p95} |")
        lines.append("")
    for set_name in e2e_sets:
        s = load(results, f"upg-e2e-{set_name}-{args.llm_model.replace(':', '-').replace('/', '-')}")
        if not s or "generation" not in s:
            continue
        lines += [f"## Answers on {set_name} ({args.llm_model})", "", "| metric | value |", "|---|---|"]
        for metric, stat in s["generation"].items():
            lines.append(f"| {metric} | {stat['mean']:.3f} [{stat['lo']:.2f}–{stat['hi']:.2f}] |")
        lines.append("")
    out = results / "UPGRADES.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
