# bd-legal-rag — build the bge-m3 + BM25 index on a Kaggle GPU (one cell, ~30 min on a T4).
# Settings: Accelerator GPU T4, Internet ON. Input: your private "bdrag-bundle" dataset
# (bdrag-code.zip + chunks-part*.jsonl.gz from scripts/make_kaggle_bundle.py).
# Afterwards: Output tab -> download bdrag_index.zip -> unzip into bd-legal-rag\data\ (creates data\index).
import glob
import gzip
import os
import shutil
import subprocess
import sys

hits = glob.glob("/kaggle/input/**/scripts/build_index.py", recursive=True)
assert hits, "Attach the bdrag-bundle dataset (Add Input -> Your Datasets)"
src = os.path.dirname(os.path.dirname(hits[0]))
shutil.copytree(src, "/kaggle/working/bdrag", dirs_exist_ok=True)
os.chdir("/kaggle/working/bdrag")

parts = sorted(glob.glob("/kaggle/input/**/chunks-part*.jsonl.gz", recursive=True),
               key=lambda p: int(p.rsplit("part", 1)[1].split(".")[0]))
assert parts, "chunks-part*.jsonl.gz not found in the bdrag-bundle dataset"
os.makedirs("data/processed", exist_ok=True)
with open("data/processed/chunks.jsonl", "wb") as out:
    for p in parts:
        with gzip.open(p, "rb") as f:
            shutil.copyfileobj(f, out)
with open("data/processed/chunks.jsonl", encoding="utf-8") as f:
    print(len(parts), "parts ->", sum(1 for _ in f), "chunks")

subprocess.run("nvidia-smi --query-gpu=name --format=csv,noheader", shell=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "sentence-transformers"], check=True)
subprocess.run([sys.executable, "scripts/build_index.py", "--chunks", "data/processed/chunks.jsonl",
                "--out", "/kaggle/working/index", "--bm25", "--batch-size", "64", "--fp16",
                "--checkpoint-every", "4000"], check=True)
subprocess.run("cd /kaggle/working && zip -qr bdrag_index.zip index && ls -lh bdrag_index.zip index",
               shell=True, check=True)
