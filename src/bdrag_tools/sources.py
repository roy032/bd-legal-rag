#!/usr/bin/env python
"""Rules, regulations, SROs, orders and court judgments: list, fetch, ingest.

The documents are listed in data/sources/manifest.jsonl (see ingest/sources.py
for the fields). Only official government hosts are accepted.

  bdrag sources check                          # validate the manifest (CI runs this)
  bdrag sources list                           # what is listed, fetched and ingested
  bdrag sources discover --division HCD AD     # add the Supreme Court's latest judgments
  bdrag sources fetch                          # download what is missing (polite, cached)
  bdrag sources ingest                         # -> data/processed/source_chunks.jsonl
  bdrag index --bm25                           # picks the new chunks up, embeds only them

Ingest needs the pdf extra (pip install -e ".[pdf]"); scanned gazettes also need
Tesseract with the Bangla pack, as for `bdrag pdf`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from ingest.sources import (
    DIVISIONS,
    KINDS,
    SC_LIST,
    append_manifest,
    load_manifest,
    local_path,
    official,
    parse_sc_list,
    source_act_id,
    validate,
)

MANIFEST = "data/sources/manifest.jsonl"
RAW = "data/raw/sources"
OUT = "data/processed/source_chunks.jsonl"
MAX_BYTES = 40 * 1024 * 1024


def _session():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = os.environ.get(
        "BDRAG_USER_AGENT",
        "bd-legal-rag/1.0 research crawler (+https://github.com/roy032/bd-legal-rag)")
    return s


def cmd_check(args) -> int:
    try:
        rows = load_manifest(args.manifest)
    except ValueError as e:
        print(e)
        return 1
    bad = 0
    for r in rows:
        for err in validate(r):
            print(f"{args.manifest}:{r['_line']}: {r.get('id')}: {err}")
            bad += 1
    print(f"{len(rows)} entries, {bad} problems")
    return 1 if bad else 0


def _ingested(out: str) -> Counter:
    p = Path(out)
    if not p.exists():
        return Counter()
    ids: Counter = Counter()
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids[json.loads(line)["metadata"].get("source_id")] += 1
    return ids


def cmd_list(args) -> int:
    rows = load_manifest(args.manifest)
    chunks = _ingested(args.out)
    by_kind: Counter = Counter()
    for r in rows:
        path = local_path(r, args.raw)
        state = f"{chunks[r['id']]} chunks" if chunks.get(r["id"]) else (
            "fetched" if path.exists() else "listed")
        by_kind[(r.get("kind"), "ingested" if chunks.get(r["id"]) else state)] += 1
        if args.verbose:
            print(f"{r.get('kind', '?'):<10} {state:<12} {r['id']:<40} {r.get('title', '')[:70]}")
    for kind in KINDS:
        counts = {s: n for (k, s), n in by_kind.items() if k == kind}
        if counts:
            print(f"{kind:<10} " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    print(f"{len(rows)} documents in {args.manifest}; {sum(chunks.values())} chunks in {args.out}")
    return 0


def cmd_discover(args) -> int:
    session = _session()
    found = []
    for div in args.division:
        url = SC_LIST.format(div=DIVISIONS[div])
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        resp.encoding = resp.encoding or "utf-8"
        rows = parse_sc_list(resp.text, div)[: args.limit]
        print(f"{div}: {len(rows)} judgments listed on {url}")
        found.extend(rows)
        time.sleep(args.delay)
    added = append_manifest(args.manifest, found)
    print(f"added {added} new entries to {args.manifest} (already listed: {len(found) - added})")
    return 0


def cmd_fetch(args) -> int:
    rows = [r for r in load_manifest(args.manifest) if not validate(r)]
    rows = [r for r in rows if r.get("url") and (not args.only or r["id"] in args.only)
            and (not args.kind or r["kind"] in args.kind)]
    session = _session()
    got = failed = 0
    for r in rows[: args.limit or None]:
        path = local_path(r, args.raw)
        if path.exists() and not args.refresh:
            continue
        if not official(r["url"]):
            print(f"skip {r['id']}: not an official host")
            continue
        try:
            resp = session.get(r["url"], timeout=120)
            resp.raise_for_status()
            data = resp.content
            if len(data) > MAX_BYTES:
                raise ValueError(f"{len(data) // 1_048_576} MB is over the limit")
            if path.suffix == ".pdf" and not data.startswith(b"%PDF"):
                raise ValueError("not a PDF (the site sent an error page?)")
        except Exception as e:
            print(f"FAILED {r['id']}: {e}")
            failed += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        got += 1
        print(f"{r['id']}: {len(data) // 1024} KB -> {path}")
        time.sleep(args.delay)
    print(f"fetched {got}, failed {failed}")
    return 1 if failed and not got else 0


def cmd_ingest(args) -> int:
    from ingest.chunk import act_overview_chunk, chunk_section
    from ingest.judgment import judgment_chunks
    from ingest.pdf import build_act, extract_pages

    rows = [r for r in load_manifest(args.manifest) if not validate(r)]
    rows = [r for r in rows if (not args.only or r["id"] in args.only)
            and (not args.kind or r["kind"] in args.kind)]
    out = Path(args.out)
    kept: list[dict] = []
    if out.exists():
        kept = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    redo = {r["id"] for r in rows}
    kept = [c for c in kept if c["metadata"].get("source_id") not in redo]
    new: list[dict] = []
    missing = 0
    for r in rows:
        path = local_path(r, args.raw)
        if not path.exists():
            missing += 1
            continue
        doc_id = source_act_id(r["id"])
        pages = extract_pages(path, ocr=args.ocr, lang=args.lang)
        meta = {k: v for k, v in r.items() if not k.startswith("_")}
        if r["kind"] == "judgment":
            chunks = judgment_chunks(pages, doc_id, meta, max_chars=args.max_chars)
        else:
            act, sections, extras = build_act(pages, doc_id, r["title"], source=r.get("url") or "")
            act.doc_type = r["kind"]
            act.act_number = r.get("citation")
            act.date = r.get("date")
            if r.get("parent_act"):
                act.preamble = f"Made under: {r['parent_act']}"
            chunks = [act_overview_chunk(act)]
            for sec in sections:
                for c in chunk_section(act, sec, max_chars=args.max_chars):
                    c.metadata.update(extras[sec.section_id])
                    chunks.append(c)
            for c in chunks:
                c.metadata.update({"source": r["kind"], "source_id": r["id"],
                                   "parent_act": r.get("parent_act"), "citation": r.get("citation"),
                                   "date": r.get("date")})
        if not chunks:
            print(f"{r['id']}: no text (scanned? try --ocr always)")
            continue
        print(f"{r['id']}: {r['kind']}, {len(pages)} pages -> {len(chunks)} chunks")
        new.extend(c.to_dict() for c in chunks)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for row in kept + new:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if missing:
        print(f"{missing} listed documents are not downloaded yet: run `bdrag sources fetch`")
    print(f"{len(kept) + len(new)} chunks in {out}. Next: bdrag index --bm25")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag sources", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--raw", default=RAW, help="where downloaded documents are kept")
    ap.add_argument("--out", default=OUT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the manifest")
    p = sub.add_parser("list", help="counts by kind and state")
    p.add_argument("-v", "--verbose", action="store_true", help="one line per document")
    p = sub.add_parser("discover", help="add the Supreme Court's listed judgments")
    p.add_argument("--division", nargs="+", choices=sorted(DIVISIONS), default=["HCD", "AD"])
    p.add_argument("--limit", type=int, default=50, help="per division")
    p.add_argument("--delay", type=float, default=2.0)
    for name in ("fetch", "ingest"):
        p = sub.add_parser(name)
        p.add_argument("--only", nargs="+", help="these ids only")
        p.add_argument("--kind", nargs="+", choices=KINDS)
        if name == "fetch":
            p.add_argument("--limit", type=int, default=0)
            p.add_argument("--refresh", action="store_true")
            p.add_argument("--delay", type=float, default=2.0)
        else:
            p.add_argument("--ocr", choices=["auto", "always", "never"], default="auto")
            p.add_argument("--lang", default="ben+eng")
            p.add_argument("--max-chars", type=int, default=1800)
    args = ap.parse_args(argv)
    return {"check": cmd_check, "list": cmd_list, "discover": cmd_discover,
            "fetch": cmd_fetch, "ingest": cmd_ingest}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
