#!/usr/bin/env python
"""Shim: the code lives in src/bdrag_tools/feedback_to_eval.py (`bdrag feedback-to-eval --help`).

Kept so `python scripts/feedback_to_eval.py ...` works from a checkout without installing.
"""
try:
    from bdrag_tools.feedback_to_eval import main
except ImportError:                     # not installed: run from the checkout
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from bdrag_tools.feedback_to_eval import main

if __name__ == "__main__":
    main()
