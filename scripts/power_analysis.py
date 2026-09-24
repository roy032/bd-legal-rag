#!/usr/bin/env python
"""How many questions do you need before a difference means anything?

The honest answer to "is 0.63 better than 0.58?" depends on how many questions
you measured and how correlated the two systems are. This simulates paired
comparisons at different set sizes and reports the smallest difference you could
reliably detect — which is also the number you should refuse to celebrate below.

  python scripts/power_analysis.py --baseline-rate 0.6 --n 50 100 150 200
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.metrics import paired_bootstrap  # noqa: E402


def detectable(n: int, base_rate: float, lift: float, trials: int = 200, seed: int = 0) -> float:
    """Share of simulated experiments where the paired test would call the lift real."""
    rng = random.Random(seed)
    wins = 0
    for _ in range(trials):
        a = [1 if rng.random() < base_rate else 0 for _ in range(n)]
        # A system that is better fixes some of the baseline's failures.
        b = [x if x == 1 else (1 if rng.random() < lift / (1 - base_rate) else 0) for x in a]
        res = paired_bootstrap(a, b, n_resamples=400, seed=rng.randrange(10_000))
        wins += res["lo"] > 0
    return wins / trials


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline-rate", type=float, default=0.6, help="e.g. current recall@5")
    ap.add_argument("--n", type=int, nargs="+", default=[50, 100, 150, 200])
    ap.add_argument("--lifts", type=float, nargs="+", default=[0.03, 0.05, 0.08, 0.12])
    args = ap.parse_args()

    print(f"baseline rate {args.baseline_rate:.2f} — probability the paired test calls a real "
          f"improvement 'better' (want >= 0.80)\n")
    header = "   n  " + "".join(f"  +{lift:.2f} " for lift in args.lifts)
    print(header)
    for n in args.n:
        row = f"{n:>4}  "
        for lift in args.lifts:
            row += f"   {detectable(n, args.baseline_rate, lift):.2f} "
        print(row)
    print("\nRead it as: at 150 questions you can reliably detect roughly a 5-8 point gain, "
          "and anything smaller needs a bigger set — or should be reported as 'within noise'.")


if __name__ == "__main__":
    main()
