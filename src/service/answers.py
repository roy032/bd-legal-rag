"""Where shared answers live.

A permalink (`/a/<id>`) is how an answer travels: pasted into a Messenger group,
a WhatsApp chat, a Facebook post. Kept only in memory, every such link died on
the next restart or deploy, after 500 newer answers, and on any replica but the
one that wrote it. A link that 404s a day after it was shared is worse than no
share button at all.

So answers go to a SQLite file next to the index (stdlib, one file, no server),
with a retention period: a stored answer quotes the law as it stood when it was
given, and the questions people ask are theirs, so nothing is kept forever.
Without a path the store stays in memory, which is what the tests and a
throwaway demo want.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("service")


class AnswerStore:
    def __init__(self, path: str = "", max_age_days: float = 90, max_memory: int = 500) -> None:
        self.path, self.max_memory = path, max_memory
        self.max_age_s = max_age_days * 86400 if max_age_days and max_age_days > 0 else None
        self._lock = threading.Lock()
        self._memory: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._durable = False
        self._puts = 0
        if path:
            try:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                with self._connect() as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    db.execute("CREATE TABLE IF NOT EXISTS answers ("
                               "id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL)")
                    db.execute("CREATE INDEX IF NOT EXISTS answers_created ON answers(created)")
                    db.commit()
                self._durable = True
                self.purge()
            except (OSError, sqlite3.Error):
                # A read-only disk must not stop the service; links then last until restart.
                log.exception("answer store %s unavailable; keeping shared answers in memory", path)
                self._durable = False

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
        try:
            yield db
        finally:
            db.close()

    @property
    def durable(self) -> bool:
        return self._durable

    def _expired(self, created: float) -> bool:
        return self.max_age_s is not None and time.time() - created > self.max_age_s

    def put(self, answer_id: str, payload: dict) -> None:
        created = float(payload.get("created") or time.time())
        with self._lock:
            if not self._durable:
                self._memory[answer_id] = (created, payload)
                while len(self._memory) > self.max_memory:
                    self._memory.popitem(last=False)
                return
            try:
                with self._connect() as db:
                    db.execute("INSERT OR REPLACE INTO answers VALUES (?, ?, ?)",
                               (answer_id, created, json.dumps(payload, ensure_ascii=False)))
                    db.commit()
            except sqlite3.Error:
                log.exception("could not store answer %s", answer_id)
                return
            self._puts += 1
        if self._puts % 200 == 0:
            self.purge()

    def get(self, answer_id: str) -> dict | None:
        with self._lock:
            if not self._durable:
                entry = self._memory.get(answer_id)
            else:
                try:
                    with self._connect() as db:
                        row = db.execute(
                            "SELECT created, payload FROM answers WHERE id = ?", (answer_id,)
                        ).fetchone()
                except sqlite3.Error:
                    log.exception("could not read answer %s", answer_id)
                    return None
                entry = (row[0], json.loads(row[1])) if row else None
        if entry is None or self._expired(entry[0]):
            return None
        return entry[1]

    def purge(self) -> int:
        """Delete answers past the retention period; returns how many went."""
        if self.max_age_s is None:
            return 0
        cutoff = time.time() - self.max_age_s
        with self._lock:
            if not self._durable:
                old = [k for k, (ts, _) in self._memory.items() if ts < cutoff]
                for k in old:
                    del self._memory[k]
                return len(old)
            try:
                with self._connect() as db:
                    n = db.execute("DELETE FROM answers WHERE created < ?", (cutoff,)).rowcount
                    db.commit()
                return n
            except sqlite3.Error:
                log.exception("could not purge old answers")
                return 0

    def close(self) -> None:
        # Connections are scoped to individual operations, so there is no
        # persistent handle to close. Keep this method for lifecycle callers.
        return

    def __len__(self) -> int:
        with self._lock:
            if not self._durable:
                return len(self._memory)
            with self._connect() as db:
                return db.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
