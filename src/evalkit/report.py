"""Turn result files into the table and the verdicts you put in a README."""
from __future__ import annotations

from evalkit.metrics import paired_bootstrap

GEN_METRICS = ("faithfulness", "correctness", "refusal_correct", "gold_cited",
               "citation_coverage", "quote_fidelity", "clean_first_pass")


def cell(stats: dict, metric: str) -> str:
    s = stats.get(metric)
    return f"{s['mean']:.3f} [{s['lo']:.2f}–{s['hi']:.2f}]" if s else "—"


def describe(config: dict) -> str:
    """Short human label for what this run actually did."""
    bits = [config.get("mode", "?")]
    if config.get("expand_refs"):
        bits.append("+refs")
    if config.get("multi_query"):
        bits.append(f"+mq{config['multi_query']}")
    if config.get("hyde"):
        bits.append("+hyde")
    if config.get("rerank", "none") != "none":
        bits.append(f"+rerank({config['rerank']})")
    if config.get("max_parts_per_section"):
        bits.append(f"+dedupe{config['max_parts_per_section']}")
    for key, tag in (("synonyms", "+syn"), ("transliterate", "+translit"), ("route", "+route"),
                     ("resolve_refs", "+resolve"), ("boost_in_force", "+in-force"),
                     ("parent_context", "+parent")):
        if config.get(key):
            bits.append(tag)
    if config.get("mmr_lambda") is not None:
        bits.append(f"+mmr{config['mmr_lambda']}")
    return " ".join(bits)


def markdown_table(runs: list[dict], metrics=("recall@5", "recall@10", "mrr", "ndcg@5"),
                   sort: bool = True) -> str:
    """sort=True puts the best recall@5 first; an ablation passes sort=False to
    keep its rows in order, since each row adds one thing to the row above."""
    gen = sorted({m for r in runs for m in r.get("generation", {}) if m in GEN_METRICS})
    head = ["run", "pipeline", "k", *metrics, *gen, "p95 latency (ms)"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    ordered = sorted(runs, key=lambda x: -(x["overall"].get("recall@5", {}).get("mean", 0))) if sort else runs
    for r in ordered:
        row = [r["label"], describe(r.get("config", {})), str(r["config"].get("k", ""))]
        row += [cell(r["overall"], m) for m in metrics]
        row += [cell(r.get("generation", {}), m) for m in gen]
        row.append(f"{r['latency_s']['p95'] * 1000:.0f}")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def paired_report(runs: list[dict], baseline_label: str, metric: str = "recall@5") -> str:
    base = next((r for r in runs if r["label"] == baseline_label), None)
    if base is None:
        return f"(no run labelled '{baseline_label}')"
    bscores = {q["id"]: q.get(metric) for q in base["per_query"]}
    if all(v is None for v in bscores.values()):
        return f"(baseline has no {metric} — was it run with a smaller k?)"
    out = [f"Paired comparison on {metric} vs '{baseline_label}' (same questions, 2000 resamples):"]
    for r in runs:
        if r["label"] == baseline_label:
            continue
        rscores = {q["id"]: q.get(metric) for q in r["per_query"]}
        ids = [i for i in bscores if bscores[i] is not None and rscores.get(i) is not None]
        if not ids:
            out.append(f"  {r['label']:<26} skipped — no {metric} in this run")
            continue
        res = paired_bootstrap([bscores[i] for i in ids], [rscores[i] for i in ids])
        verdict = "better" if res["lo"] > 0 else "worse" if res["hi"] < 0 else "within noise"
        out.append(f"  {r['label']:<26} {res['diff']:+.3f} "
                   f"[{res['lo']:+.3f}, {res['hi']:+.3f}]  {verdict}  (n={res['n']})")
    return "\n".join(out)
