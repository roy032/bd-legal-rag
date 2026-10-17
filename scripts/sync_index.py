#!/usr/bin/env python
"""Move a built index through a Hugging Face dataset repo.

Building the index takes hours on a laptop; serving it anywhere else (a free
Hugging Face Space, a second machine, a cloud session) should take a download.

  # On the machine that built it (once per rebuild). Needs `huggingface-cli login`
  # or HF_TOKEN with write access. --private keeps the dataset private.
  python scripts/sync_index.py push --repo <you>/bdrag-index --private

  # Anywhere you want to serve it (HF_TOKEN needed only for a private repo):
  python scripts/sync_index.py pull --repo <you>/bdrag-index

Only the files the service reads are moved: data/index (vectors, records, BM25).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

INDEX_FILES = ["index.json", "vectors.npy", "records.jsonl*", "bm25*"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["push", "pull"])
    ap.add_argument("--repo", required=True, help="dataset repo id, e.g. roy032/bdrag-index")
    ap.add_argument("--index", default="data/index")
    ap.add_argument("--private", action="store_true", help="create the dataset as private (push)")
    ap.add_argument("--revision", help="branch, tag or commit to pull")
    args = ap.parse_args()
    try:
        import huggingface_hub as hub  # pip install -e ".[hub]"
    except ImportError:
        sys.exit('huggingface_hub is not installed: pip install -e ".[hub]"')

    index = Path(args.index)
    if args.action == "push":
        if not (index / "index.json").exists():
            sys.exit(f"no index at {index}; build it first (python scripts/build_index.py --bm25)")
        api = hub.HfApi()
        api.create_repo(args.repo, repo_type="dataset", private=args.private, exist_ok=True)
        api.upload_folder(repo_id=args.repo, repo_type="dataset", folder_path=str(index),
                          allow_patterns=INDEX_FILES, commit_message="Update index")
        print(f"pushed {index} to https://huggingface.co/datasets/{args.repo}")
    else:
        path = hub.snapshot_download(repo_id=args.repo, repo_type="dataset", local_dir=str(index),
                                     allow_patterns=INDEX_FILES, revision=args.revision)
        print(f"index ready in {path}")


if __name__ == "__main__":
    main()
