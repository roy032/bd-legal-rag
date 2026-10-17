#!/usr/bin/env python
"""Shim: the code lives in src/bdrag_tools/measure_upgrades.py (`bdrag measure-upgrades --help`).

Kept so `python scripts/measure_upgrades.py ...` works from a checkout without installing.
"""
try:
    from bdrag_tools.measure_upgrades import main
except ImportError:                     # not installed: run from the checkout
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from bdrag_tools.measure_upgrades import main

if __name__ == "__main__":
    main()
