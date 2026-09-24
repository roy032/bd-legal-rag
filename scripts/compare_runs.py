#!/usr/bin/env python
"""Turn result files into the ablation table for your README.

  python scripts/compare_runs.py results/*.json --baseline dense --metric recall@5
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from evalkit.report import markdown_table, paired_report  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", nargs="+")
    ap.add_argument("--baseline", help="label of the run to compare against")
    ap.add_argument("--metric", default="recall@5")
    ap.add_argument("--out", help="also write the markdown table here")
    args = ap.parse_args()

    runs = [json.loads(Path(p).read_text(encoding="utf-8"))
            for p in args.results if not p.endswith(".answers.json")]
    if not runs:
        sys.exit("no result files")

    table = markdown_table(runs)
    print(table)
    if args.baseline:
        print()
        print(paired_report(runs, args.baseline, args.metric))
    if args.out:
        Path(args.out).write_text(table + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
