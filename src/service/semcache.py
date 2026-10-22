"""Answer cache for paraphrases, gated hard.

The exact cache (cache.py) keys on the question text, so "what is the punishment
for murder" and "What sentence does someone get for murder?" each cost a full
answer: 20 to 115 s on a CPU model. This cache finds an earlier answer for a
question that means the same thing, and serves it in milliseconds.

Serving the answer to a *different* legal question would be worse than slow, so
a match must pass every gate:

  scope      same settings as the exact key (model, k, index, retrieval config,
             agent, requested language): a different pipeline is a different answer
  script     Bangla, Latin or mixed: the answer is written in the question's language
  numbers    the same digits, Bangla or ASCII ("section 302" never matches "304")
  negation   the same count of not / no / without / না / নয় / ছাড়া ...
             ("পরিশোধ করলে" vs "না করলে" flips the answer)
  topics     the same everyday situations from rag/topics.py
  evidence   the dense top-k sections of the two questions overlap (Jaccard), so
             the model would have been shown the same provisions
  similarity cosine of the query embeddings at or above the threshold

The threshold is per embedding model. `bdrag semcache` measures it on
data/eval/paraphrases.jsonl (60 paraphrases, 48 near misses such as "murder" vs
"attempted murder", "demanding" vs "giving" dowry) plus every pair of eval
questions with different gold sections, and prints the lowest value with no
false merge. The value in TUNED came from that run; an embedder not listed there
gets no semantic cache unless BDRAG_SEMANTIC_CACHE names a threshold.

A served answer carries `cache_match` (the earlier question and the similarity),
and the page says it answered a similar question, so a wrong merge is visible.
"""
from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from ingest.textutils import bn_to_ascii_digits, nfc

# bge-m3, measured 2026-10-22 with `bdrag semcache --model BAAI/bge-m3`
# (docs/reports/semantic-cache-2026-10-22.md). Highest near miss: 0.958.
TUNED: dict[str, float] = {"BAAI/bge-m3": 0.965}
DEFAULT_OVERLAP = 0.6           # top-5 sections: at least 4 of 5 shared

_WORD = re.compile(r"[\wঀ-৿']+")
_NEGATIONS = frozenset(nfc(w) for w in {
    "not", "no", "never", "without", "cannot", "nor", "neither", "none", "unless",
    "না", "নয়", "নেই", "নাই", "ছাড়া", "বিনা", "ব্যতীত", "নি",
    "na", "nai", "nei", "noy", "chara", "charai", "bina",
})
_BN = re.compile(r"[ঀ-৿]")
_LATIN = re.compile(r"[A-Za-z]")
_DIGITS = re.compile(r"\d+")


def script(question: str) -> str:
    """'bn', 'latin' or 'mixed' (a Bangla question with an English act name is mixed)."""
    bn, latin = len(_BN.findall(question)), len(_LATIN.findall(question))
    if not bn:
        return "latin"
    if not latin:
        return "bn"
    return "bn" if bn >= 4 * latin else "latin" if latin >= 4 * bn else "mixed"


def numbers(question: str) -> frozenset[str]:
    return frozenset(n.lstrip("0") or "0" for n in _DIGITS.findall(bn_to_ascii_digits(question)))


def negations(question: str) -> int:
    words = _WORD.findall(nfc(question).lower())
    return (sum(w in _NEGATIONS for w in words)
            + sum(w.endswith("n't") for w in words)
            # Bangla past negative attaches -নি to the verb: দেয়নি, করেনি, পায়নি.
            + sum(len(w) > 3 and w.endswith("নি") and _BN.match(w) is not None for w in words))


def signature(question: str, scope: str, topics: Iterable[str] = ()) -> tuple:
    """Everything that must be equal before similarity is even looked at."""
    return (scope, script(question), numbers(question), negations(question),
            frozenset(topics))


def overlap(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def resolve_threshold(setting: str, embedder_name: str | None) -> float | None:
    """BDRAG_SEMANTIC_CACHE: 'auto' (the tuned value for this embedder, else off),
    'off', or a number. None means disabled."""
    s = (setting or "auto").strip().lower()
    if s in ("off", "0", "false", "no", "none", ""):
        return None
    if s == "auto":
        return TUNED.get(embedder_name or "")
    value = float(s)
    if not 0.0 < value <= 1.0:
        raise ValueError(f"BDRAG_SEMANTIC_CACHE must be in (0, 1], got {setting!r}")
    return value


@dataclass(frozen=True)
class Probe:
    """What one question contributes: computed once, used to look up and to add."""
    question: str
    vector: np.ndarray
    sig: tuple
    evidence: frozenset


@dataclass(frozen=True)
class Match:
    key: str                    # the exact-cache key of the earlier answer
    question: str
    similarity: float
    overlap: float


@dataclass
class _Entry:
    key: str
    probe: Probe
    ts: float


class SemanticCache:
    """Maps a question to the exact-cache key of an earlier, equivalent question.

    It stores no answers: the answer lives once, in the exact cache, so TTL,
    eviction and the Redis backend all keep working, and an evicted answer is
    simply a miss here too."""

    def __init__(self, threshold: float, min_overlap: float = DEFAULT_OVERLAP,
                 max_size: int = 512, ttl_s: float | None = 3600) -> None:
        self.threshold, self.min_overlap = threshold, min_overlap
        self.max_size, self.ttl_s = max_size, ttl_s
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = self.misses = 0

    def lookup(self, probe: Probe) -> Match | None:
        now = time.time()
        best: Match | None = None
        with self._lock:
            for key, e in list(self._entries.items()):
                if self.ttl_s is not None and now - e.ts > self.ttl_s:
                    del self._entries[key]
                    continue
                if e.probe.sig != probe.sig:
                    continue
                sim = float(np.dot(e.probe.vector, probe.vector))
                if sim < self.threshold or (best is not None and sim <= best.similarity):
                    continue
                ov = overlap(e.probe.evidence, probe.evidence)
                if ov < self.min_overlap:
                    continue
                best = Match(key, e.probe.question, sim, ov)
            if best is None:
                self.misses += 1
            else:
                self.hits += 1
                self._entries.move_to_end(best.key)
        return best

    def add(self, key: str, probe: Probe) -> None:
        with self._lock:
            self._entries[key] = _Entry(key, probe, time.time())
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"threshold": self.threshold, "min_overlap": self.min_overlap,
                "size": len(self._entries), "hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0}


def evidence(hits) -> frozenset:
    """The sections a list of hits points at: (act_id, section_id) pairs."""
    return frozenset((h.metadata.get("act_id"), h.metadata.get("section_id")) for h in hits)
