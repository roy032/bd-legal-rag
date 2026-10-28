#!/usr/bin/env python
"""Back up, verify and restore what the service writes: shared answers and the logs.

The index can be rebuilt from bdlaws; the shared answers cannot. A link someone
pasted into a WhatsApp group points at a row in data/answers.sqlite3, and one dead
disk loses every such link. This takes a consistent copy while the service runs
(SQLite's online backup, not a file copy of a database in WAL mode), checks it,
and keeps the last N.

  bdrag backup                                   # data/ -> data/backups/bdrag-<time>.tar.gz
  bdrag backup --out /mnt/usb/bdrag --keep 30
  bdrag backup --verify data/backups/bdrag-20261027T020000Z.tar.gz
  bdrag backup --restore data/backups/bdrag-20261027T020000Z.tar.gz --to data

Each archive holds a manifest.json with a SHA-256 and a row count per file, so
--verify catches a truncated upload as well as a corrupt database. --restore
refuses to overwrite existing files unless --force is given. Schedule it nightly
(cron, Task Scheduler, or the compose file's comment) and copy the archive off
the machine; a backup on the same disk only protects against mistakes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
from pathlib import Path

DATABASES = ("answers.sqlite3",)
LOGS = ("queries.jsonl", "feedback.jsonl")
PREFIX = "bdrag-"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_sqlite(path: Path) -> bytes:
    """A consistent copy of a live database, via the online backup API."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / path.name
        src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        return target.read_bytes()


def check_sqlite(data: bytes) -> tuple[bool, int]:
    """(integrity_check passed, rows in the answers table)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "check.sqlite3"
        path.write_bytes(data)
        db = sqlite3.connect(path)
        try:
            ok = db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            try:
                rows = db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
            except sqlite3.Error:
                rows = 0
            return ok, rows
        finally:
            db.close()


def _lines(data: bytes) -> int:
    return sum(1 for line in data.splitlines() if line.strip())


def create(data_dir: Path, out_dir: Path, keep: int = 14, now: float | None = None) -> Path:
    files: dict[str, bytes] = {}
    for name in DATABASES:
        if (data_dir / name).exists():
            files[name] = snapshot_sqlite(data_dir / name)
    for name in LOGS:
        if (data_dir / name).exists():
            files[name] = (data_dir / name).read_bytes()
    if not files:
        raise SystemExit(f"nothing to back up in {data_dir} (looked for {', '.join(DATABASES + LOGS)})")
    manifest: dict = {"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                      "source": str(data_dir), "files": {}}
    for name, blob in files.items():
        entry: dict = {"sha256": _sha256(blob), "bytes": len(blob)}
        if name.endswith(".sqlite3"):
            ok, rows = check_sqlite(blob)
            if not ok:
                raise SystemExit(f"{name}: the snapshot failed its integrity check; not writing a backup")
            entry["rows"] = rows
        else:
            entry["rows"] = _lines(blob)
        manifest["files"][name] = entry
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    archive = out_dir / f"{PREFIX}{stamp}.tar.gz"
    partial = archive.with_suffix(".partial")
    with tarfile.open(partial, "w:gz") as tar:
        for name, blob in [("manifest.json", json.dumps(manifest, indent=2).encode()), *files.items()]:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(blob), int(now or time.time()), 0o600
            tar.addfile(info, io.BytesIO(blob))
    os.replace(partial, archive)                 # a reader never sees half an archive
    prune(out_dir, keep)
    return archive


def prune(out_dir: Path, keep: int) -> list[Path]:
    if keep <= 0:
        return []
    old = sorted(out_dir.glob(f"{PREFIX}*.tar.gz"))[:-keep]
    for path in old:
        path.unlink()
    return old


def _read(archive: Path) -> tuple[dict, dict[str, bytes]]:
    files: dict[str, bytes] = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            # Only plain files with plain names: an archive is data, never a path to write.
            if not member.isfile() or "/" in member.name or member.name.startswith("."):
                raise SystemExit(f"{archive}: unexpected member {member.name!r}")
            f = tar.extractfile(member)
            files[member.name] = f.read() if f else b""
    if "manifest.json" not in files:
        raise SystemExit(f"{archive}: no manifest.json")
    return json.loads(files.pop("manifest.json")), files


def verify(archive: Path) -> list[str]:
    """Problems found; empty means the archive is whole."""
    try:
        manifest, files = _read(archive)
    except (tarfile.TarError, EOFError, OSError, ValueError) as e:   # truncated upload, not gzip
        return [f"{archive.name}: unreadable ({type(e).__name__}: {e})"]
    problems = []
    for name, entry in manifest.get("files", {}).items():
        blob = files.get(name)
        if blob is None:
            problems.append(f"{name}: missing")
            continue
        if _sha256(blob) != entry.get("sha256"):
            problems.append(f"{name}: checksum mismatch")
        if name.endswith(".sqlite3") and not check_sqlite(blob)[0]:
            problems.append(f"{name}: integrity check failed")
    for name in files:
        if name not in manifest.get("files", {}):
            problems.append(f"{name}: not in the manifest")
    return problems


def restore(archive: Path, to: Path, force: bool = False) -> list[Path]:
    problems = verify(archive)
    if problems:
        raise SystemExit(f"{archive} failed verification: " + "; ".join(problems))
    _, files = _read(archive)
    to.mkdir(parents=True, exist_ok=True)
    clash = [n for n in files if (to / n).exists()]
    if clash and not force:
        raise SystemExit(f"would overwrite {', '.join(clash)} in {to}; stop the service and pass --force")
    written = []
    for name, blob in files.items():
        tmp = to / f".{name}.restore"
        tmp.write_bytes(blob)
        os.replace(tmp, to / name)
        for side in ("-wal", "-shm"):            # stale WAL from the old database would be replayed
            (to / f"{name}{side}").unlink(missing_ok=True)
        written.append(to / name)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag backup", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data", help="directory the service writes to (default: data)")
    ap.add_argument("--out", default="data/backups", help="where archives go (default: data/backups)")
    ap.add_argument("--keep", type=int, default=14, help="archives to keep; 0 = all (default: 14)")
    ap.add_argument("--verify", metavar="ARCHIVE", help="check an archive and exit")
    ap.add_argument("--restore", metavar="ARCHIVE", help="verify, then unpack into --to")
    ap.add_argument("--to", default="data", help="restore target (default: data)")
    ap.add_argument("--force", action="store_true", help="let --restore overwrite existing files")
    args = ap.parse_args(argv)
    if args.verify:
        problems = verify(Path(args.verify))
        for p in problems:
            print(f"❌ {p}")
        if not problems:
            print(f"✅ {args.verify}: every file matches its checksum")
        return 1 if problems else 0
    if args.restore:
        for path in restore(Path(args.restore), Path(args.to), args.force):
            print(f"restored {path}")
        return 0
    archive = create(Path(args.data), Path(args.out), args.keep)
    manifest, _ = _read(archive)
    summary = ", ".join(f"{n} ({e['rows']} rows)" for n, e in manifest["files"].items())
    print(f"wrote {archive}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
