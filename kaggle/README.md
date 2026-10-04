# Building the index on a Kaggle GPU

## Automated (recommended)

```powershell
cd $HOME\Desktop\bd-legal-rag
.venv\Scripts\pip install kaggle              # once; token: kaggle.com -> Settings -> API -> Create New Token
.venv\Scripts\python scripts\finish.py
```

`scripts/finish.py` waits for (or starts) the Kaggle index build, installs the index
into `data/index`, runs the ablation, tuning, failure analysis and abstention
calibration, the Ollama answer evaluation if Ollama is installed, writes
`results/RESULTS.md` and the README "Results" section, runs the tests and commits.

## By hand

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
