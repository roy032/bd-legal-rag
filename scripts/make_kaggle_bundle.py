#!/usr/bin/env python
"""Pack the code and the chunks for building the index on a Kaggle GPU.

    python scripts/make_kaggle_bundle.py        # -> kaggle_upload/ (git-ignored)

Writes bdrag-code.zip (the code) and chunks-partN.jsonl.gz (the chunks, split
into parts under 9 MB so any upload path accepts them). Upload all of them to
one private Kaggle dataset named "bdrag-bundle" and run kaggle/build_index_cell.py
there (kaggle/README.md). Embedding ~44k chunks with bge-m3 takes days on a laptop
CPU and about half an hour on a free Kaggle T4.
"""
from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ["src", "scripts", "pyproject.toml", "requirements.txt"]
SKIP = {"__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"}
PART_BYTES = 9_000_000        # compressed size per part


def main() -> list[Path]:
    chunks = ROOT / "data" / "processed" / "chunks.jsonl"
    if not chunks.exists():
        raise SystemExit(f"{chunks} not found — run scripts/ingest.py first")
    out = ROOT / "kaggle_upload"
    out.mkdir(exist_ok=True)
    for old in list(out.glob("chunks-part*.jsonl.gz")) + list(out.glob("bdrag-*.zip")):
        old.unlink()
    code = out / "bdrag-code.zip"
    with zipfile.ZipFile(code, "w", zipfile.ZIP_DEFLATED) as z:
        for name in CODE:
            p = ROOT / name
            for f in [p] if p.is_file() else sorted(q for q in p.rglob("*") if q.is_file()):
                if not SKIP & set(f.relative_to(ROOT).parts):
                    z.write(f, Path("bdrag") / f.relative_to(ROOT))
    # compress, then cut on line boundaries so each part is a valid .jsonl.gz
    raw = chunks.read_bytes().splitlines(keepends=True)
    ratio = len(gzip.compress(b"".join(raw[:2000]))) / max(1, sum(map(len, raw[:2000])))
    per_part = int(PART_BYTES / max(ratio, 1e-3) * 0.9)
    parts, buf, size = [], [], 0
    for line in raw:
        buf.append(line)
        size += len(line)
        if size >= per_part:
            parts.append(buf)
            buf, size = [], 0
    if buf:
        parts.append(buf)
    written = [code]
    for i, p in enumerate(parts, 1):
        f = out / f"chunks-part{i}.jsonl.gz"
        f.write_bytes(gzip.compress(b"".join(p), compresslevel=9))
        written.append(f)
    for f in written:
        print(f"{f.name:28s} {f.stat().st_size / 1e6:5.1f} MB")
    print(f"{len(raw)} chunks in {len(parts)} part(s) -> {out}")
    return written


if __name__ == "__main__":
    main()
