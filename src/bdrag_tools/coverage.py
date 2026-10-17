#!/usr/bin/env python
"""Which acts in the site's index have no text in the corpus, and why.

Run it before spending a day on OCR: it tells you how many acts are image-only
(a scanned PDF and no section text), how many failed to download, and how many
were skipped as repealed. Works offline from the page cache the ingest left.

  bdrag coverage                          # data/raw + data/processed/chunks.jsonl
  bdrag coverage --list scanned           # print the scanned acts' ids and titles
  bdrag coverage --json results/coverage.json

Then feed the scanned ones to `bdrag pdf` (ingest_pdf.py) with their PDFs.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from ingest.fetch import BASE_URL, Fetcher
from ingest.parse import parse_act, parse_index
from rag import jsonio

INDEX_URL = f"{BASE_URL}/laws-of-bangladesh-chronological-index.html"
REPEALED = re.compile(r"\[\s*(?:রহিত|Repealed)\s*\]", re.I)
PDF_LINK = re.compile(r"""href=["']([^"']+\.pdf)["']""", re.I)


def classify(html: str | None, act_id: int, in_corpus: bool, repealed: bool) -> tuple[str, list[str]]:
    """One of: indexed, repealed, not_downloaded, scanned, no_sections, unparsed, not_ingested.

    not_ingested: the page has sections but none reached the chunks (an ingest run
    limited by --limit/--year-from, or one that stopped early).
    """
    if in_corpus:
        return "indexed", []
    if repealed:
        return "repealed", []
    if html is None:
        return "not_downloaded", []
    pdfs = PDF_LINK.findall(html)
    try:
        sections = parse_act(html, act_id).sections
    except Exception:
        return ("scanned" if pdfs else "unparsed"), pdfs
    if pdfs and not sections:
        return "scanned", pdfs
    return ("no_sections" if not sections else "not_ingested"), pdfs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", default="data/raw")
    ap.add_argument("--chunks", nargs="+", default=["data/processed/chunks.jsonl",
                                                     "data/processed/pdf_chunks.jsonl"])
    ap.add_argument("--online", action="store_true", help="download act pages missing from the cache")
    ap.add_argument("--list", choices=["scanned", "not_downloaded", "no_sections", "unparsed",
                                       "not_ingested"],
                    help="print the acts in one bucket")
    ap.add_argument("--json", help="write every act's bucket here")
    args = ap.parse_args()

    fetcher = Fetcher(cache_dir=args.cache, offline=not args.online)
    refs = parse_index(fetcher.get(INDEX_URL))
    corpus: set[int] = set()
    for path in args.chunks:
        try:
            chunks = jsonio.read_jsonl(path)
        except FileNotFoundError:
            continue
        corpus |= {int(c["metadata"]["act_id"]) for c in chunks
                   if c.get("metadata", {}).get("act_id") is not None}

    rows: list[dict] = []
    for r in refs:
        try:
            html = fetcher.get(r.url)
        except (FileNotFoundError, RuntimeError):
            html = None
        bucket, pdfs = classify(html, r.act_id, r.act_id in corpus, bool(REPEALED.search(r.title)))
        rows.append({"act_id": r.act_id, "title": r.title, "bucket": bucket, "pdfs": pdfs[:3]})

    counts = Counter(row["bucket"] for row in rows)
    print(f"{len(rows)} acts in the site's index")
    for bucket in ("indexed", "repealed", "scanned", "no_sections", "unparsed", "not_ingested",
                   "not_downloaded"):
        print(f"  {bucket:15s} {counts.get(bucket, 0)}")
    if counts.get("scanned"):
        print("\nscanned acts can be added with `bdrag pdf <file.pdf>` (Tesseract ben+eng)")
    if args.list:
        for row in rows:
            if row["bucket"] == args.list:
                print(f"{row['act_id']}\t{row['title']}\t{' '.join(row['pdfs'])}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
