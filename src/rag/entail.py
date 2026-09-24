"""Is the claim actually supported, or does it merely carry a citation?

Phase 5 checked that every sentence ends with `[n]`. That is attribution
theatre: a model can cite excerpt 2 for a sentence excerpt 2 does not support.
This module scores the real question — does the cited text entail the claim? —
and it is the difference between "cites sources" and "is grounded".

Two implementations behind one interface:

  NLIEntailer      a multilingual natural-language-inference model
                   (e.g. MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli).
                   Correct, ~100 ms per claim on CPU, needs a download.
  LexicalEntailer  content-word coverage of the claim by the cited text.
                   No dependency, deterministic, catches the blatant cases
                   (a claim about a fine cited to a definition), misses
                   paraphrase and negation. Use it as the floor, not the goal.

Negation is the failure both share: "shall not exceed" and "shall exceed" look
almost identical lexically, and small NLI models are unreliable on legal
negation. Check a sample by hand before believing the number.
"""
from __future__ import annotations

from typing import Protocol

from .lexical import tokenize

STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "for", "and", "or", "is", "are", "be", "shall", "may",
    "any", "such", "this", "that", "under", "by", "with", "as", "at", "on", "it",
    "এই", "ও", "এবং", "বা", "যে", "করা", "হইবে", "হবে", "করিতে", "জন্য", "এর", "একটি", "না",
}


class Entailer(Protocol):
    name: str

    def score(self, premise: str, claim: str) -> float: ...


class LexicalEntailer:
    """Share of the claim's content words that appear in the premise."""

    name = "lexical"

    def score(self, premise: str, claim: str) -> float:
        claim_tokens = [t for t in tokenize(claim, stem=True) if t not in STOPWORDS]
        if not claim_tokens:
            return 1.0
        premise_tokens = set(tokenize(premise, stem=True))
        return sum(t in premise_tokens for t in claim_tokens) / len(claim_tokens)


class NLIEntailer:
    """Real entailment. `pip install transformers torch` and a multilingual NLI model."""

    def __init__(self, model_name: str = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
                 device: str | None = None) -> None:
        from transformers import pipeline as hf_pipeline  # lazy: heavy

        self.name = model_name
        self.pipe = hf_pipeline("text-classification", model=model_name, device=device,
                                top_k=None, truncation=True)

    def score(self, premise: str, claim: str) -> float:
        out = self.pipe({"text": premise[:2000], "text_pair": claim[:500]})
        scores = out[0] if isinstance(out[0], list) else out
        for row in scores:
            if str(row["label"]).lower().startswith("entail"):
                return float(row["score"])
        return 0.0


def get_entailer(kind: str = "lexical", **kw) -> Entailer | None:
    if kind in ("none", None, ""):
        return None
    if kind == "nli":
        return NLIEntailer(**kw)
    return LexicalEntailer()


def check_claims(claims: list[tuple[str, list[int]]], hits, entailer: Entailer,
                 threshold: float = 0.55) -> dict:
    """claims: [(sentence, [cited excerpt numbers])] -> per-claim entailment report."""
    rows = []
    for sentence, cited in claims:
        premises = [hits[n - 1].body for n in cited if 1 <= n <= len(hits)]
        best = max((entailer.score(p, sentence) for p in premises), default=0.0)
        rows.append({"claim": sentence, "cited": cited, "score": round(best, 3),
                     "supported": best >= threshold})
    supported = [r for r in rows if r["supported"]]
    return {
        "entailer": entailer.name,
        "threshold": threshold,
        "claims": rows,
        "support_rate": len(supported) / len(rows) if rows else 1.0,
        "unsupported": [r["claim"] for r in rows if not r["supported"]],
    }
