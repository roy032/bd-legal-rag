"""Run a configuration over the evaluation set and save a result file."""
from __future__ import annotations

import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from evalkit.dataset import EvalItem, section_key, slice_stats
from evalkit.metrics import aggregate, evaluate_one

KS = (1, 3, 5, 10)


def run_retrieval(items: list[EvalItem], retriever, k: int = 10, **search_kw) -> dict:
    """Retrieve for every question; score only the answerable ones."""
    per_query, records = [], []
    latencies = []
    for it in items:
        t0 = time.perf_counter()
        hits = retriever.search(it.question, k=k, **search_kw)
        latencies.append(time.perf_counter() - t0)
        keys = [section_key(h.metadata) for h in hits]
        rec: dict[str, object] = {
            "id": it.id, "question": it.question, "language": it.language, "type": it.type,
            "gold": it.gold, "retrieved": keys,
            "top_chunks": [h.chunk_id for h in hits[:5]],
            "scores": [round(h.score, 4) for h in hits[:5]]}
        if it.answerable:
            m = evaluate_one(keys, set(it.gold), ks=tuple(kk for kk in KS if kk <= k),
                             grades=it.gold_grades and it.grades())
            per_query.append({"id": it.id, "language": it.language, "type": it.type, **m})
            rec["metrics"] = m
        records.append(rec)
    return {"per_query": per_query, "records": records, "latencies": latencies}


def run_precomputed(items: list[EvalItem], retrieved: dict[str, list[str]],
                    latencies: list[float], k: int = 10) -> dict:
    """Score retrieval that already happened — e.g. the evidence an agent gathered."""
    per_query, records = [], []
    for it in items:
        keys = retrieved.get(it.id, [])
        rec: dict[str, object] = {
            "id": it.id, "question": it.question, "language": it.language, "type": it.type,
            "gold": it.gold, "retrieved": keys, "top_chunks": [], "scores": []}
        if it.answerable:
            m = evaluate_one(keys, set(it.gold), ks=tuple(kk for kk in KS if kk <= max(k, 1)),
                             grades=it.gold_grades and it.grades())
            per_query.append({"id": it.id, "language": it.language, "type": it.type, **m})
            rec["metrics"] = m
        records.append(rec)
    return {"per_query": per_query, "records": records, "latencies": latencies or [0.0]}


def by_slice(per_query: list[dict], field: str) -> dict:
    out = {}
    for value in sorted({q[field] for q in per_query}):
        rows = [{k: v for k, v in q.items() if k not in ("id", "language", "type")}
                for q in per_query if q[field] == value]
        out[value] = aggregate(rows)
    return out


def summarize(label: str, config: dict, items: list[EvalItem], run: dict,
              generation: list[dict] | None = None) -> dict:
    per_query = run["per_query"]
    lat = sorted(run["latencies"])
    summary = {
        "label": label,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config,
        "dataset": slice_stats(items),
        "overall": aggregate([{k: v for k, v in q.items() if k not in ("id", "language", "type")}
                              for q in per_query]),
        "by_language": by_slice(per_query, "language"),
        "by_type": by_slice(per_query, "type"),
        "latency_s": {"median": lat[len(lat) // 2] if lat else 0.0,
                      "p95": lat[int(len(lat) * 0.95)] if lat else 0.0},
        "env": {"python": platform.python_version()},
    }
    if generation:
        summary["generation"] = aggregate(
            [{k: v for k, v in g.items() if not k.startswith("_") and k != "id"} for g in generation])
    return summary


def save(summary: dict, run: dict, out_dir: str | Path, label: str,
         generation: list[dict] | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{label}.json"
    payload = {**summary, "per_query": run["per_query"], "records": run["records"]}
    if generation:
        payload["generation_per_query"] = generation
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def fmt(stat: dict) -> str:
    """0.842 [0.78, 0.90]"""
    return f"{stat['mean']:.3f} [{stat['lo']:.2f}, {stat['hi']:.2f}]"


def print_summary(summary: dict) -> None:
    print(f"\n=== {summary['label']} ===")
    print(json.dumps(summary["config"], ensure_ascii=False))
    print(f"questions: {summary['dataset']['n']} "
          f"({summary['dataset']['answerable']} answerable)")
    ks = sorted(int(m.split("@")[1]) for m in summary["overall"] if m.startswith("recall@"))
    main_metric = f"recall@{ks[-1]}" if ks else "mrr"
    for metric in [f"recall@{k}" for k in ks] + ["mrr", f"ndcg@{ks[-1]}" if ks else "",
                                                 f"precision@{ks[-1]}" if ks else ""]:
        if metric in summary["overall"]:
            print(f"  {metric:<12} {fmt(summary['overall'][metric])}")
    for field in ("by_language", "by_type"):
        print(f"  --- {field.replace('by_', 'by ')} ({main_metric}) ---")
        for value, stats in summary[field].items():
            if main_metric in stats:
                print(f"    {value:<14} {fmt(stats[main_metric])}  (n={stats[main_metric]['n']})")
    if "generation" in summary:
        print("  --- generation ---")
        for metric, stat in summary["generation"].items():
            print(f"    {metric:<20} {fmt(stat)}")
    print(f"  retrieval latency: median {summary['latency_s']['median']*1000:.0f} ms, "
          f"p95 {summary['latency_s']['p95']*1000:.0f} ms")
