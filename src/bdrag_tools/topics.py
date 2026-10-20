#!/usr/bin/env python
"""What the topic table (rag/topics.py) resolves to in your index.

Each topic names an act and the sections a lawyer would open first. This prints,
for every topic, the act it found and each section's title, so a wrong number
shows up as a wrong title and a missing act as MISSING before anyone relies on it.

  bdrag topics                                  # data/index
  bdrag topics --index data/index --only wages,defamation
  bdrag topics --question "my boss has not paid my salary"
  bdrag topics --json results/topics.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rag.pipeline import load_records
from rag.refs import ActResolver
from rag.topics import TOPICS, TopicIndex, match_topics


def report(resolver: ActResolver, only: set[str] | None = None) -> list[dict]:
    index = TopicIndex(resolver)
    rows = []
    for topic in TOPICS:
        if only and topic.name not in only:
            continue
        for ref in topic.acts:
            aid = index.act_id(ref)
            row: dict[str, Any] = {"topic": topic.name, "phrases": list(ref.phrases), "act_id": aid,
                   "act_title": resolver.titles.get(aid) if aid is not None else None,
                   "sections": []}
            for num in ref.sections:
                parts = resolver.lookup(aid, num, max_parts=1) if aid is not None else []
                row["sections"].append({
                    "number": num,
                    "title": parts[0].metadata.get("section_title") if parts else None,
                    "chunk_id": parts[0].chunk_id if parts else None})
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--chunks", default="data/processed/chunks.jsonl")
    ap.add_argument("--only", help="comma-separated topic names")
    ap.add_argument("--question", help="show which topics a question triggers and what gets pinned")
    ap.add_argument("--json", help="also write the report here")
    args = ap.parse_args()

    resolver = ActResolver(load_records(args.index, args.chunks))
    if args.question:
        hits, acts = TopicIndex(resolver).resolve(args.question)
        print("topics:", ", ".join(t.name for t in match_topics(args.question)) or "none")
        print("search inside:", ", ".join(resolver.titles.get(a, str(a)) for a in acts) or "none")
        for h in hits:
            print(f"  pinned [{h.metadata['topic']}] {h.citation} — {h.metadata.get('section_title')}")
        return

    rows = report(resolver, set(args.only.split(",")) if args.only else None)
    missing = 0
    for r in rows:
        head = r["act_title"] or f"MISSING ({' / '.join(r['phrases'])})"
        print(f"{r['topic']:<20} {head}" + (f"  [act {r['act_id']}]" if r["act_id"] else ""))
        missing += r["act_id"] is None
        for s in r["sections"]:
            missing += r["act_id"] is not None and s["chunk_id"] is None
            print(f"{'':<22}s.{s['number']}: {s['title'] or ('(no title)' if s['chunk_id'] else 'MISSING')}")
    print(f"\n{len(rows)} topic acts, {missing} missing")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
