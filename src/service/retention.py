"""Housekeeping: nothing a visitor wrote is kept longer than the privacy page says.

Shared answers already expire (service/answers.py), but the query log and the
feedback log each hold the visitor's question too, and before this they grew
forever: a privacy promise the disk did not keep, and on a small Space volume a
slow disk-fill. Both are append-only JSONL with a `ts` on every row, so the rows
are in time order and pruning is "drop the head of the file".

A background thread does it every few hours, together with the answer-store purge
and the index-age gauge, so an operator does not need a cron job to stay inside
the policy. Appends and prunes share one lock: a row written while the file is
being rewritten would otherwise land in the old file and vanish.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("service")

LOG_LOCK = threading.Lock()


def append_jsonl(path: str, row: dict) -> None:
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with LOG_LOCK, open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:                        # logging must never break a response
        log.warning("could not append to %s", path)


def _ts(line: str) -> float | None:
    try:
        row = json.loads(line)
    except ValueError:
        return None
    ts = row.get("ts") if isinstance(row, dict) else None
    return float(ts) if isinstance(ts, (int, float)) else None


def prune_jsonl(path: str, max_age_days: float, now: float | None = None) -> int:
    """Delete rows older than `max_age_days`; returns how many went. Rows without a
    readable `ts` are kept (they are not ours to judge). The file is rewritten to a
    temporary file and swapped in, so a crash mid-prune leaves the old file whole."""
    if not path or not max_age_days or max_age_days <= 0 or not os.path.exists(path):
        return 0
    cutoff = (now if now is not None else time.time()) - max_age_days * 86400
    tmp = f"{path}.prune"
    with LOG_LOCK:
        try:
            with open(path, encoding="utf-8") as f:
                first = f.readline()
                head_ts = _ts(first)
                if head_ts is None or head_ts >= cutoff:
                    return 0                 # oldest row is in date: nothing to do, no rewrite
                dropped = 0
                with open(tmp, "w", encoding="utf-8") as out:
                    for line in [first, *f]:
                        ts = _ts(line)
                        if ts is not None and ts < cutoff:
                            dropped += 1
                        else:
                            out.write(line)
            os.replace(tmp, path)
            return dropped
        except OSError:
            log.exception("could not prune %s", path)
            with contextlib.suppress(OSError):
                os.remove(tmp)
            return 0


class Housekeeper:
    """Runs `tasks` (name -> callable returning rows deleted) now and then every
    `interval_s` on a daemon thread. A failing task is logged and retried next round."""

    def __init__(self, tasks: dict[str, Callable[[], int]], interval_s: float = 6 * 3600,
                 on_result: Callable[[str, int], None] | None = None) -> None:
        self.tasks, self.interval_s, self.on_result = tasks, interval_s, on_result
        self.last_run: float | None = None
        self.deleted: dict[str, int] = dict.fromkeys(tasks, 0)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, task in self.tasks.items():
            try:
                n = int(task() or 0)
            except Exception:
                log.exception("housekeeping task %s failed", name)
                continue
            out[name] = n
            self.deleted[name] += n
            if self.on_result:
                self.on_result(name, n)
            if n:
                log.info(json.dumps({"event": "retention", "store": name, "deleted": n}))
        self.last_run = time.time()
        return out

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.interval_s)

    def start(self) -> None:
        if self._thread is None and self.tasks:
            self._thread = threading.Thread(target=self._loop, name="housekeeping", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def stats(self) -> dict:
        return {"last_run": self.last_run, "interval_s": self.interval_s,
                "deleted": dict(self.deleted)}
