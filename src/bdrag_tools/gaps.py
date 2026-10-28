#!/usr/bin/env python
"""What visitors asked that the service could not answer well: the next content work.

Reads the query log and the feedback log the service writes and lists the
questions that were refused, answered only with labelled general guidance,
failed a guardrail, or got a thumbs-down, grouped by question and ranked by how
many different visitors hit them. Each row names the topic-table entry the
question matched; "none" is a question no topic catches, which is where a new
entry in rag/topics.py (or a missing act in the index) pays off first.

  bdrag gaps                                          # data/queries.jsonl + data/feedback.jsonl
  bdrag gaps --since 2026-10-01 --out results/gaps.md
  bdrag gaps --json results/gaps.json --top 50
  bdrag gaps --public data/coverage/public_gaps.json   # for the /coverage page

Questions are already redacted for phone, NID and card numbers by the service.
The report still holds what people asked: keep it out of public places.

--public writes the one part that may be published, for the service's
"What we can't answer yet" page (/coverage): only questions that at least
--min-visitors different visitors asked (default 3, so no one person's question
is shown), redacted again, clipped, with no comments, dates or counts per visitor.
Read the file before you deploy it; drop any line that still says too much.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

from ingest.textutils import nfc
from rag.pii import redact
from rag.query import script_language
from rag.topics import match_topics


def norm(q: str) -> str:
    return " ".join(nfc(q).lower().strip(" ?।!.").split())


def read_jsonl(path: str) -> list[dict]:
    p = Path(path)
    if not path or not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _since(value: str | None) -> float:
    if not value:
        return 0.0
    import calendar

    return float(calendar.timegm(time.strptime(value, "%Y-%m-%d")))


def reasons(row: dict) -> list[str]:
    out = []
    if row.get("refused"):
        out.append("refused")
    if row.get("general"):
        out.append("general guidance")
    if row.get("failures"):
        out.append("guardrail")
    if row.get("rating") == "down":
        out.append("thumbs down")
    return out


def analyse(queries: list[dict], feedback: list[dict], since: float = 0.0) -> dict:
    queries = [r for r in queries if float(r.get("ts") or 0) >= since]
    feedback = [r for r in feedback if float(r.get("ts") or 0) >= since]
    groups: dict[str, dict] = {}
    for row in [*queries, *feedback]:
        why = reasons(row)
        question = (row.get("question") or "").strip()
        if not why or not question:
            continue
        g = groups.setdefault(norm(question), {
            "question": question, "count": 0, "visitors": set(), "reasons": defaultdict(int),
            "last_seen": 0.0, "comments": []})
        g["count"] += 1
        if row.get("client"):
            g["visitors"].add(row["client"])
        for r in why:
            g["reasons"][r] += 1
        g["last_seen"] = max(g["last_seen"], float(row.get("ts") or 0))
        if row.get("comment"):
            g["comments"].append(str(row["comment"])[:200])
    out = []
    for g in groups.values():
        topics = [t.name for t in match_topics(g["question"])]
        out.append({"question": g["question"], "count": g["count"],
                    "visitors": max(len(g["visitors"]), 1),
                    "reasons": dict(g["reasons"]), "topics": topics,
                    "language": script_language(g["question"]),
                    "last_seen": time.strftime("%Y-%m-%d", time.gmtime(g["last_seen"])),
                    "comments": g["comments"][:3]})
    out.sort(key=lambda r: (-r["visitors"], -r["count"], r["question"]))
    total = len(queries)
    latencies = sorted(float(r.get("latency_s") or 0) for r in queries)

    def share(key: str) -> float:
        return round(sum(1 for r in queries if r.get(key)) / total, 3) if total else 0.0

    summary = {
        "answers": total,
        "visitors": len({r.get("client") for r in queries if r.get("client")}),
        "refused": share("refused"), "general_guidance": share("general"),
        "guardrail_failures": share("failures"),
        "thumbs_down": sum(1 for r in feedback if r.get("rating") == "down"),
        "thumbs_up": sum(1 for r in feedback if r.get("rating") == "up"),
        "p95_latency_s": latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]
        if latencies else None,
        "no_topic": sum(1 for r in out if not r["topics"]),
    }
    return {"summary": summary, "gaps": out}


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def markdown(report: dict, top: int = 30) -> str:
    s = report["summary"]
    lines = [
        "# Questions the service could not answer well", "",
        f"{s['answers']} answers to {s['visitors']} visitors. Refused {s['refused']:.0%}, "
        f"general guidance only {s['general_guidance']:.0%}, failed a guardrail "
        f"{s['guardrail_failures']:.0%}. Feedback: {s['thumbs_up']} up, {s['thumbs_down']} down."
        + (f" p95 answer time {s['p95_latency_s']:.0f} s." if s["p95_latency_s"] is not None else ""),
        "",
        f"{len(report['gaps'])} distinct questions below; {s['no_topic']} match no topic-table entry "
        "(start there: add a topic in rag/topics.py, or the act is missing from the index).", "",
        "| # | Visitors | Times | Why | Topic | Lang | Last seen | Question |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for n, g in enumerate(report["gaps"][:top], 1):
        why = ", ".join(f"{k} ×{v}" if v > 1 else k for k, v in g["reasons"].items())
        lines.append(f"| {n} | {g['visitors']} | {g['count']} | {why} | "
                     f"{', '.join(g['topics']) or '**none**'} | {g['language']} | {g['last_seen']} | "
                     f"{_cell(g['question'][:160])} |")
    commented = [g for g in report["gaps"][:top] if g["comments"]]
    if commented:
        lines += ["", "## What visitors said", ""]
        for g in commented:
            lines.append(f"- *{_cell(g['question'][:100])}*: " + " / ".join(_cell(c) for c in g["comments"]))
    advice = ("Turn the ones that should have been answered into eval questions with "
              "`bdrag feedback-to-eval`, then fix and measure with `bdrag eval`.")
    lines += ["", advice, ""]
    return "\n".join(lines)


def public_report(report: dict, min_visitors: int = 3, top: int = 50,
                  max_chars: int = 200) -> dict:
    """The publishable part of a report: questions several different visitors asked."""
    items = []
    for g in report["gaps"]:
        if g["visitors"] < min_visitors:
            continue
        question = " ".join(redact(g["question"])[0].split())
        if len(question) > max_chars:
            question = question[:max_chars].rsplit(" ", 1)[0] + " …"
        why = "unanswered" if {"refused", "general guidance"} & set(g["reasons"]) else "answered badly"
        items.append({"question": question, "language": g["language"], "why": why,
                      "topics": g["topics"], "visitors": g["visitors"]})
        if len(items) >= top:
            break
    s = report["summary"]
    return {"generated": time.strftime("%Y-%m-%d", time.gmtime()), "min_visitors": min_visitors,
            "summary": {"answers": s["answers"], "refused": s["refused"],
                        "general_guidance": s["general_guidance"]},
            "questions": items}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag gaps", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", default="data/queries.jsonl")
    ap.add_argument("--feedback", default="data/feedback.jsonl")
    ap.add_argument("--since", help="YYYY-MM-DD (UTC)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", help="write the markdown report here instead of printing it")
    ap.add_argument("--json", help="also write the full report as JSON")
    ap.add_argument("--public", help="also write the publishable list for /coverage here")
    ap.add_argument("--min-visitors", type=int, default=3,
                    help="--public: a question appears only after this many different visitors asked it")
    args = ap.parse_args(argv)
    report = analyse(read_jsonl(args.queries), read_jsonl(args.feedback), _since(args.since))
    text = markdown(report, args.top)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {len(report['gaps'])} questions")
    else:
        print(text)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.public:
        pub = public_report(report, max(args.min_visitors, 2), args.top)
        Path(args.public).parent.mkdir(parents=True, exist_ok=True)
        Path(args.public).write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {args.public}: {len(pub['questions'])} questions asked by "
              f">= {pub['min_visitors']} visitors. Read it before you deploy it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
