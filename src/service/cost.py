"""Estimated model spend, per request and in aggregate.

Exact accounting needs the provider's usage numbers, which `llm.py` does not
surface (it returns text). An estimate from character counts is accurate to
within a few percent for planning, and answers the question every reviewer asks:
"what does this cost to run?"

Prices are per million tokens and change constantly — override them with
BDRAG_PRICES (JSON) rather than trusting the defaults.
"""
from __future__ import annotations

import json
import os

# {model_substring: (input_per_mtok_usd, output_per_mtok_usd)}
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "haiku": (0.80, 4.00),
    "sonnet": (3.00, 15.00),
    "opus": (15.00, 75.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "ollama": (0.0, 0.0),
    "echo": (0.0, 0.0),
}
CHARS_PER_TOKEN = 3.2        # Bangla is denser per character than English; measure yours


def prices() -> dict[str, tuple[float, float]]:
    override = os.environ.get("BDRAG_PRICES")
    if not override:
        return DEFAULT_PRICES
    try:
        return {k: tuple(v) for k, v in json.loads(override).items()}
    except Exception:
        return DEFAULT_PRICES


def estimate_tokens(text: str) -> int:
    return max(int(len(text or "") / CHARS_PER_TOKEN), 1)


def estimate_cost(model: str, input_chars: int, output_chars: int) -> float:
    table = prices()
    rate = next((v for k, v in table.items() if k in (model or "").lower()), (0.0, 0.0))
    return (estimate_tokens("x" * input_chars) / 1e6 * rate[0]
            + estimate_tokens("x" * output_chars) / 1e6 * rate[1])


def project_monthly(cost_per_query: float, queries_per_day: int = 200) -> float:
    return cost_per_query * queries_per_day * 30
