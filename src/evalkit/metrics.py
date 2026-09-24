"""Retrieval metrics, plus the statistics that stop you fooling yourself.

Definitions (binary relevance, gold = set of section keys):
  hit@k       1 if any gold section appears in the top k
  recall@k    fraction of the gold sections found in the top k
  precision@k fraction of the top k that are gold
  MRR         1 / rank of the first gold section (0 if none)
  nDCG@k      rewards putting gold sections higher up

Always report an interval, never a bare mean: on 150 questions, a 2-point
difference is usually noise. `paired_bootstrap` compares two systems on the
SAME questions, which is far more sensitive than comparing two averages.
"""
from __future__ import annotations

import math
import random
from statistics import mean


def _ranks_of_gold(retrieved: list[str], gold: set[str]) -> list[int]:
    """1-based ranks at which gold items appear (deduplicated by section)."""
    seen, ranks, rank = set(), [], 0
    for key in retrieved:
        if key in seen:
            continue          # several chunks of one section count once
        seen.add(key)
        rank += 1
        if key in gold:
            ranks.append(rank)
    return ranks


def hit_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    return float(any(r <= k for r in _ranks_of_gold(retrieved, gold)))


def recall_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return float("nan")
    return len([r for r in _ranks_of_gold(retrieved, gold) if r <= k]) / len(gold)


def precision_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    unique = list(dict.fromkeys(retrieved))[:k]
    return sum(u in gold for u in unique) / max(len(unique), 1)


def mrr(retrieved: list[str], gold: set[str]) -> float:
    ranks = _ranks_of_gold(retrieved, gold)
    return 1.0 / min(ranks) if ranks else 0.0


def ndcg_at_k(retrieved: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return float("nan")
    dcg = sum(1.0 / math.log2(r + 1) for r in _ranks_of_gold(retrieved, gold) if r <= k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(len(gold), k)))
    return dcg / idcg if idcg else 0.0


def graded_ndcg_at_k(retrieved: list[str], grades: dict[str, int], k: int) -> float:
    """nDCG with graded relevance: 2 = answers the question, 1 = related, 0 = not.

    Binary nDCG cannot tell "found the wrong section" from "found a section that
    half-answers it"; graded nDCG can, and those are different failures."""
    if not grades:
        return float("nan")
    unique = list(dict.fromkeys(retrieved))[:k]
    dcg = sum((2 ** grades.get(key, 0) - 1) / math.log2(rank + 1)
              for rank, key in enumerate(unique, start=1))
    ideal = sorted(grades.values(), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(rank + 1) for rank, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


def evaluate_one(retrieved: list[str], gold: set[str], ks: tuple[int, ...] = (1, 3, 5, 10),
                 grades: dict[str, int] | None = None) -> dict:
    out = {"mrr": mrr(retrieved, gold)}
    if grades:
        for k in ks:
            out[f"gndcg@{k}"] = graded_ndcg_at_k(retrieved, grades, k)
    for k in ks:
        out[f"hit@{k}"] = hit_at_k(retrieved, gold, k)
        out[f"recall@{k}"] = recall_at_k(retrieved, gold, k)
        out[f"precision@{k}"] = precision_at_k(retrieved, gold, k)
        out[f"ndcg@{k}"] = ndcg_at_k(retrieved, gold, k)
    return out


# ------------------------------------------------------------------ statistics

def bootstrap_ci(values: list[float], confidence: float = 0.95, n_resamples: int = 2000,
                 seed: int = 0) -> tuple[float, float, float]:
    """(mean, low, high). Resample the questions with replacement."""
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    n = len(clean)
    means = sorted(mean(rng.choices(clean, k=n)) for _ in range(n_resamples))
    lo = means[int((1 - confidence) / 2 * n_resamples)]
    hi = means[min(int((1 + confidence) / 2 * n_resamples), n_resamples - 1)]
    return mean(clean), lo, hi


def aggregate(per_query: list[dict], confidence: float = 0.95) -> dict:
    """{metric: {mean, lo, hi, n}} over per-question scores."""
    if not per_query:
        return {}
    out = {}
    for metric in per_query[0]:
        vals = [q[metric] for q in per_query if metric in q]
        m, lo, hi = bootstrap_ci(vals, confidence)
        out[metric] = {"mean": m, "lo": lo, "hi": hi,
                       "n": len([v for v in vals if not math.isnan(v)])}
    return out


def paired_bootstrap(a: list[float], b: list[float], n_resamples: int = 2000,
                     seed: int = 0) -> dict:
    """Is B better than A on the same questions?

    Returns the mean difference, its confidence interval, and the share of
    resamples where B did not beat A ('p_not_better'). If the interval spans 0,
    say so in your README instead of claiming an improvement.
    """
    pairs = [(x, y) for x, y in zip(a, b, strict=False) if not (math.isnan(x) or math.isnan(y))]
    if not pairs:
        return {"diff": float("nan"), "lo": float("nan"), "hi": float("nan"), "p_not_better": 1.0}
    rng = random.Random(seed)
    diffs = sorted(mean(y - x for x, y in rng.choices(pairs, k=len(pairs)))
                   for _ in range(n_resamples))
    return {
        "diff": mean(y - x for x, y in pairs),
        "lo": diffs[int(0.025 * n_resamples)],
        "hi": diffs[int(0.975 * n_resamples) - 1],
        "p_not_better": sum(d <= 0 for d in diffs) / n_resamples,
        "n": len(pairs),
    }
