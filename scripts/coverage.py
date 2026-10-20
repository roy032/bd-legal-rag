#!/usr/bin/env python
"""Shim: the code lives in src/bdrag_tools/coverage.py (`bdrag coverage --help`).

Kept so `python scripts/coverage.py ...` works from a checkout without installing.
"""
try:
    from bdrag_tools.coverage import main
except ImportError:                     # not installed: run from the checkout
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from bdrag_tools.coverage import main

if __name__ == "__main__":
    main()
