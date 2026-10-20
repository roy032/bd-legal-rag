#!/usr/bin/env bash
# Pull the index (BDRAG_INDEX_REPO, set as a Space variable), warm the embedder,
# then serve on the port Spaces expects.
set -euo pipefail
cd /home/user/app
if [ -n "${BDRAG_INDEX_REPO:-}" ] && [ ! -f "$BDRAG_INDEX/index.json" ]; then
  python scripts/sync_index.py pull --repo "$BDRAG_INDEX_REPO" --index "$BDRAG_INDEX"
fi
python -m rag.cli doctor || true      # prints what is missing into the Space logs
exec uvicorn service.app:get_app --factory --host 0.0.0.0 --port 7860
