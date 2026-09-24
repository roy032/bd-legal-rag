"""Small (optionally gzipped) JSON / JSONL helpers for index files.

Chunk records and BM25 postings are mostly repeated Bangla/English text and
compress 4-6x. Readers accept both `name` and `name.gz`, so indexes written
before compression existed still load.
"""
from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _resolve(path: Path) -> Path | None:
    gz = path.with_name(path.name + ".gz")
    if gz.exists():
        return gz
    return path if path.exists() else None


def exists(path: str | Path) -> bool:
    return _resolve(Path(path)) is not None


def _open(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def write_jsonl(path: str | Path, rows: Iterable[dict], compress: bool = True) -> Path:
    path = Path(path)
    target = path.with_name(path.name + ".gz") if compress else path
    other = path if compress else path.with_name(path.name + ".gz")
    with _open(target, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if other.exists():            # never leave a stale twin next to the new file
        other.unlink()
    return target


def read_jsonl(path: str | Path) -> list[dict]:
    real = _resolve(Path(path))
    if real is None:
        raise FileNotFoundError(path)
    with _open(real, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path: str | Path, obj: Any, compress: bool = True) -> Path:
    path = Path(path)
    target = path.with_name(path.name + ".gz") if compress else path
    other = path if compress else path.with_name(path.name + ".gz")
    with _open(target, "w") as f:
        json.dump(obj, f, ensure_ascii=False)
    if other.exists():
        other.unlink()
    return target


def read_json(path: str | Path) -> Any:
    real = _resolve(Path(path))
    if real is None:
        raise FileNotFoundError(path)
    with _open(real, "r") as f:
        return json.load(f)
