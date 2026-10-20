#!/usr/bin/env python
"""Shim: the code lives in src/bdrag_tools/sync_index.py (`bdrag sync --help`).

Kept so `python scripts/sync_index.py ...` keeps working in docs, the Makefile and
the Kaggle cells, which run from a checkout without installing the package.
"""
try:
    from bdrag_tools.sync_index import main
except ImportError:                     # not installed: run from the checkout
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from bdrag_tools.sync_index import main

if __name__ == "__main__":
    main()
