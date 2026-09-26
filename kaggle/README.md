# Building the index on a Kaggle GPU

Embedding all ~44k chunks with bge-m3 runs at about 0.1 chunks/second on a
laptop CPU (days). On a free Kaggle T4 it takes roughly half an hour.

1. Pack code + chunks (after `scripts/ingest.py`):
   ```powershell
   .venv\Scripts\python scripts\make_kaggle_bundle.py     # -> kaggle_upload\ (code zip + chunk parts)
   ```
2. kaggle.com → **Datasets → New Dataset** → upload every file in `kaggle_upload\`
   (`bdrag-code.zip` and `chunks-part*.jsonl.gz`), title `bdrag-bundle`, **Private** →
   Create. (Later: **New Version** of the same dataset.)
3. **Code → New Notebook**. Right panel: **Accelerator: GPU T4**, **Internet: On**,
   **Add Input → Your Datasets → bdrag-bundle**.
4. Replace the starter cell with the contents of `kaggle/build_index_cell.py` and run it
   (or **Save Version → Save & Run All**).
5. **Output** tab → download `bdrag_index.zip` → unzip into `bd-legal-rag\data\`
   so that `data\index\` holds `vectors.npy`, `records.jsonl.gz`, `bm25.json.gz`, `index.json`.

The index records which embedder built it, so the laptop loads bge-m3 for
queries automatically (query embedding on a CPU takes well under a second).
