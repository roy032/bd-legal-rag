"""The real UI and API on the tiny test corpus with a canned model, for the
accessibility check (tests/a11y/axe.mjs). No index, no model download.

  python tests/a11y/serve.py --port 8765
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import uvicorn  # noqa: E402

from service.app import ServiceConfig, create_app  # noqa: E402
from test_rag import CORPUS  # noqa: E402
from test_service import fake_components  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    pipeline, llm, stream = fake_components()
    app = create_app(ServiceConfig(rate_per_min=100000, burst=1000), pipeline=pipeline,
                     llm=llm, stream_llm=stream, records=CORPUS)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
