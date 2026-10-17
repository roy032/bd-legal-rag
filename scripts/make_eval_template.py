#!/usr/bin/env python
"""Shim: the code lives in src/bdrag_tools/make_eval_template.py (`bdrag template --help`).

Kept so `python scripts/make_eval_template.py ...` keeps working in docs, the Makefile and
the Kaggle cells, which run from a checkout without installing the package.
"""
try:
    from bdrag_tools.make_eval_template import main
except ImportError:                     # not installed: run from the checkout
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from bdrag_tools.make_eval_template import main

if __name__ == "__main__":
    main()
