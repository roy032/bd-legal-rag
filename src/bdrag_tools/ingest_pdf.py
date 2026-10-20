#!/usr/bin/env python
"""Acts that only exist as PDF (including scanned ones) -> chunks.

Writes data/processed/pdf_chunks.jsonl, which scripts/build_index.py picks up
next to chunks.jsonl. Re-running with the same PDF replaces that act's chunks
instead of adding a second copy. The HTML ingest rewrites chunks.jsonl from
scratch, so PDF chunks live in their own file and survive it.

Needs:  pip install -e ".[pdf]"   and Tesseract with the Bangla pack for scanned pages
        (Windows: the UB-Mannheim installer, tick "Bengali"; Debian: tesseract-ocr-ben).

Examples
  python scripts/ingest_pdf.py gazette.pdf --title "পল্লী সঞ্চয় ব্যাংক আইন, ২০১৪"
  python scripts/ingest_pdf.py data/pdf/*.pdf --ocr always --show 2
  python scripts/build_index.py --bm25        # embeds only the new chunks
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ingest.chunk import act_overview_chunk, chunk_section
from ingest.pdf import build_act, default_act_id, extract_pages


def _ocr_ready(lang: str) -> str | None:
    """None when OCR can run; otherwise a one-line reason."""
    try:
        import pytesseract
        have = set(pytesseract.get_languages(config=""))
    except Exception as e:  # missing module or binary
        return f"OCR unavailable ({type(e).__name__}: {e}); install pytesseract and Tesseract"
    missing = set(lang.split("+")) - have
    return f"Tesseract has no {sorted(missing)} language data" if missing else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+")
    ap.add_argument("--title", help="act title (one PDF only); default: the first line of text")
    ap.add_argument("--act-id", type=int, help="id to file the act under (one PDF only)")
    ap.add_argument("--ocr", choices=["auto", "always", "never"], default="auto",
                    help="auto: OCR only pages with no text layer")
    ap.add_argument("--lang", default="ben+eng", help="Tesseract languages")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--max-chars", type=int, default=1800)
    ap.add_argument("--out", default="data/processed/pdf_chunks.jsonl")
    ap.add_argument("--show", type=int, default=0, help="print the first N chunks of each act")
    args = ap.parse_args()
    if len(args.pdfs) > 1 and (args.title or args.act_id):
        sys.exit("--title and --act-id apply to a single PDF")
    if args.ocr != "never" and (why := _ocr_ready(args.lang)):
        print(f"warning: {why}; scanned pages will be skipped", file=sys.stderr)
        args.ocr = "never"

    out = Path(args.out)
    kept: list[dict] = []
    if out.exists():
        kept = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines() if ln.strip()]
    new: list[dict] = []
    for pdf in args.pdfs:
        act_id = args.act_id or default_act_id(pdf)
        pages = extract_pages(pdf, ocr=args.ocr, lang=args.lang, dpi=args.dpi)
        act, sections, extras = build_act(pages, act_id, args.title, source=Path(pdf).name)
        chunks = [act_overview_chunk(act)]
        chunks[0].metadata["source"] = "pdf"
        for sec in sections:
            for c in chunk_section(act, sec, max_chars=args.max_chars):
                c.metadata.update(extras[sec.section_id])
                chunks.append(c)
        n_ocr = sum(p.ocr for p in pages)
        empty = sum(not p.text.strip() for p in pages)
        print(f"{pdf}: act {act_id} '{act.title}' ({act.language}) — {len(pages)} pages "
              f"({n_ocr} OCR, {empty} empty), {len(sections)} sections, {len(chunks)} chunks")
        kept = [c for c in kept if c["metadata"].get("act_id") != act_id]
        new.extend(c.to_dict() for c in chunks)
        for c in chunks[: args.show]:
            print("-" * 80 + f"\n{c.chunk_id}\n{c.text[:800]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for row in kept + new:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(kept) + len(new)} chunks in {out}. Next: python scripts/build_index.py --bm25")


if __name__ == "__main__":
    main()
