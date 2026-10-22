"""Keeping the service up when the answering model is slow or down.

A local 4B model on a laptop CPU takes 20-120 s per answer and serves one at a
time; a free hosted model has a quota and goes away without notice. Three small
mechanisms decide what a visitor sees then, instead of a request that hangs:

  Admission     at most N answers run at once and M more wait; past that the
                service says "busy, retry in a few seconds" (503) straight away.
                Twenty queued answers on one CPU would each take twenty times as
                long, so every one of them would time out.
  CircuitBreaker after a few model failures in a row, stop calling the model for
                a cooldown and serve the retrieved provisions at once, rather than
                making every visitor wait for the same timeout. One trial call
                after the cooldown decides whether to close it again.
  SingleFlight  identical questions arriving together (a shared link, a refresh)
                run the model once; the others wait for that answer.

All three are in-process. With several replicas each limits its own share, which
is what you want for a model running on the same machine.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

T = TypeVar("T")


class Busy(Exception):
    """Raised when admission is refused; carries a retry hint in seconds."""

    def __init__(self, retry_after_s: float) -> None:
        super().__init__("too many answers in progress")
        self.retry_after_s = retry_after_s


class Admission:
    """Bounded concurrency with a bounded queue.

    `slot()` is entered in the worker thread that runs the model: it waits for one
    of `max_inflight` slots, but only if fewer than `max_queue` are already
    waiting; otherwise it raises Busy immediately. `max_inflight=0` turns it off.
    Counting happens in the thread that does the work, so a request that never
    starts (the client went away) cannot leak a place in the queue.
    """

    def __init__(self, max_inflight: int = 2, max_queue: int = 8,
                 retry_after_s: float = 10.0) -> None:
        self.max_inflight, self.max_queue = max_inflight, max_queue
        self.retry_after_s = retry_after_s
        self._sem = threading.Semaphore(max(max_inflight, 1))
        self._lock = threading.Lock()
        self.inflight = self.waiting = 0
        self.rejected = 0

    def full(self) -> bool:
        """Would a new answer be refused right now? A cheap check on the event loop,
        so a refusal is a fast 503 instead of a worker thread started for nothing."""
        if self.max_inflight <= 0:
            return False
        with self._lock:
            return self.inflight + self.waiting >= self.max_inflight + self.max_queue

    @contextmanager
    def slot(self):
        """Run one answer: wait for a slot, or raise Busy if the queue is full."""
        if self.max_inflight <= 0:
            yield
            return
        with self._lock:
            if self.inflight + self.waiting >= self.max_inflight + self.max_queue:
                self.rejected += 1
                raise Busy(self.retry_after_s)
            self.waiting += 1
        self._sem.acquire()
        with self._lock:
            self.waiting = max(self.waiting - 1, 0)
            self.inflight += 1
        try:
            yield
        finally:
            with self._lock:
                self.inflight -= 1
            self._sem.release()

    def stats(self) -> dict:
        with self._lock:
            return {"inflight": self.inflight, "waiting": self.waiting,
                    "max_inflight": self.max_inflight, "max_queue": self.max_queue,
                    "rejected": self.rejected}


class CircuitBreaker:
    """closed -> open after `threshold` consecutive failures -> half-open after
    `cooldown_s` (one trial call) -> closed on success, open again on failure."""

    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, threshold: int = 3, cooldown_s: float = 30.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold, self.cooldown_s, self._clock = threshold, cooldown_s, clock
        self._lock = threading.Lock()
        self.failures = 0
        self.opened_at: float | None = None
        self._trial = False
        self.trips = 0

    @property
    def state(self) -> str:
        with self._lock:
            return self._state()

    def _state(self) -> str:
        if self.opened_at is None:
            return self.CLOSED
        if self._clock() - self.opened_at >= self.cooldown_s:
            return self.HALF_OPEN
        return self.OPEN

    def allow(self) -> str | None:
        """May this request call the model? None = no; otherwise "closed" or "trial".
        In half-open only one trial runs at a time; its caller must end it with
        success(), failure() or release_trial()."""
        if self.threshold <= 0:
            return self.CLOSED
        with self._lock:
            state = self._state()
            if state == self.CLOSED:
                return self.CLOSED
            if state == self.HALF_OPEN and not self._trial:
                self._trial = True
                return "trial"
            return None

    def retry_after(self) -> float:
        with self._lock:
            if self.opened_at is None:
                return 0.0
            return max(self.cooldown_s - (self._clock() - self.opened_at), 1.0)

    def success(self) -> None:
        with self._lock:
            self.failures, self.opened_at, self._trial = 0, None, False

    def failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self._trial or (self.opened_at is None and self.failures >= self.threshold):
                self.trips += 1
                self.opened_at = self._clock()
            self._trial = False

    def release_trial(self) -> None:
        """A trial call that ended without a verdict (e.g. it was cached or refused
        before the model ran) must not keep the breaker half-open forever."""
        with self._lock:
            self._trial = False


class SingleFlight:
    """Collapse concurrent calls with the same key into one execution.

    The first caller runs `fn`; callers arriving while it runs wait and get the
    same result (or the same exception). Nothing is kept afterwards, so this is
    not a cache: it only removes duplicate work that overlaps in time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls: dict[str, _Call] = {}
        self.shared = 0

    def do(self, key: str, fn: Callable[[], T]) -> tuple[T, bool]:
        """Returns (result, shared) where shared is True for a caller that waited."""
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if call is None:
                call = self._calls[key] = _Call()
            else:
                self.shared += 1
        if not leader:
            call.done.wait()
            error = call.error
            if isinstance(error, BaseException):
                raise error
            return call.result, True
        try:
            call.result = fn()
        except BaseException as e:
            call.error = e
            raise
        finally:
            with self._lock:
                self._calls.pop(key, None)
            call.done.set()
        return call.result, False


class _Call:
    __slots__ = ("done", "error", "result")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
