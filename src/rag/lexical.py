"""BM25 over Bangla + English legal text, written out rather than imported.

Why bother when dense embeddings exist: embeddings are bad at exact tokens.
"ধারা ৩০২", "304A", "Form VII", a defined term quoted verbatim — these are
matched by the *string*, and that is what BM25 is for. In a legal corpus that
covers a large share of real questions.

Okapi BM25:

    score(q, d) = Σ_t IDF(t) · f(t,d)·(k1+1) / ( f(t,d) + k1·(1-b + b·|d|/avgdl) )
    IDF(t)      = ln( 1 + (N - df + 0.5) / (df + 0.5) )

Tokenisation is the part that actually decides your Bangla numbers:
  * Bangla digits are folded to ASCII, so "৩০২" and "302" are one token.
  * '।' and '৷' are punctuation, not letters.
  * Optional light suffix stripping (গুলি/গুলো/টি/দের/কে/ের …) — Bangla is
    agglutinative, so "ধারায়" and "ধারার" should reach "ধারা". It is crude,
    so it is a flag you ablate, not a default you assume.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ingest.textutils import bn_to_ascii_digits, nfc, normalize

from .filters import matches
from .store import Hit

TOKEN_RE = re.compile(r"[0-9a-zঀ-৿]+")

# Longest first, so "গুলোর" strips before "র".
BN_SUFFIXES = tuple(nfc(s) for s in (
    "গুলোর", "গুলির", "গুলো", "গুলি", "দেরকে", "দের", "টিকে", "টাকে", "টির", "টার",
    "খানা", "খানি", "টুকু", "য়ের", "েরা", "ের", "েতে", "তে", "কে", "রা", "টি", "টা", "য়", "র", "ে",
))


def tokenize(text: str, stem: bool = False, min_len: int = 1) -> list[str]:
    text = bn_to_ascii_digits(normalize(text).lower())
    tokens = TOKEN_RE.findall(text)
    if stem:
        tokens = [_strip_suffix(t) for t in tokens]
    return [t for t in tokens if len(t) >= min_len]


def _strip_suffix(token: str) -> str:
    if len(token) < 4 or not any("ঀ" <= c <= "৿" for c in token):
        return token          # never touch English or short words
    for suf in BN_SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            return token[: -len(suf)]
    return token


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75, stem: bool = False,
                 field: str = "text") -> None:
        self.k1, self.b, self.stem, self.field = k1, b, stem, field
        self.records: list[dict] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)  # term -> [(doc, tf)]
        self.doc_len: list[int] = []
        self.avgdl = 0.0

    def __len__(self) -> int:
        return len(self.records)

    # ---------------- build ----------------
    def add(self, records: Iterable[dict]) -> None:
        for rec in records:
            doc_id = len(self.records)
            self.records.append(rec)
            tokens = tokenize(rec[self.field], stem=self.stem)
            self.doc_len.append(len(tokens))
            for term, tf in Counter(tokens).items():
                self.postings[term].append((doc_id, tf))
        self.avgdl = sum(self.doc_len) / max(len(self.doc_len), 1)

    def idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        if df == 0:
            return 0.0
        return math.log(1 + (len(self.records) - df + 0.5) / (df + 0.5))

    # ---------------- search ----------------
    def score_all(self, query: str) -> dict[int, float]:
        scores: dict[int, float] = defaultdict(float)
        for term in tokenize(query, stem=self.stem):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf(term)
            for doc_id, tf in postings:
                dl = self.doc_len[doc_id] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1e-9))
                scores[doc_id] += idf * tf * (self.k1 + 1) / denom
        return scores

    def search(self, query: str, k: int = 10, filters: dict[str, Any] | None = None,
               where: Callable[[dict], bool] | None = None) -> list[Hit]:
        scores = self.score_all(query)
        if filters or where:
            scores = {i: s for i, s in scores.items()
                      if (not filters or matches(self.records[i]["metadata"], filters))
                      and (not where or where(self.records[i]["metadata"]))}
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        return [
            Hit(chunk_id=self.records[i]["chunk_id"], score=float(s),
                text=self.records[i]["text"], body=self.records[i]["body"],
                metadata=self.records[i]["metadata"])
            for i, s in top
        ]

    # ---------------- persistence ----------------
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        (path / "bm25.json").write_text(json.dumps({
            "k1": self.k1, "b": self.b, "stem": self.stem, "field": self.field,
            "doc_len": self.doc_len, "avgdl": self.avgdl,
            "postings": dict(self.postings),
        }, ensure_ascii=False), encoding="utf-8")
        with open(path / "bm25_records.jsonl", "w", encoding="utf-8") as f:
            for r in self.records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> BM25Index:
        path = Path(path)
        d = json.loads((path / "bm25.json").read_text(encoding="utf-8"))
        idx = cls(k1=d["k1"], b=d["b"], stem=d["stem"], field=d["field"])
        idx.doc_len = d["doc_len"]
        idx.avgdl = d["avgdl"]
        idx.postings = defaultdict(list, {t: [tuple(x) for x in p] for t, p in d["postings"].items()})
        with open(path / "bm25_records.jsonl", encoding="utf-8") as f:
            idx.records = [json.loads(line) for line in f]
        return idx
