# Runbook — from downloaded pages to evaluated system (Windows)

Every command runs in PowerShell from the repository folder with the virtual
environment's Python:

```powershell
cd $HOME\Desktop\bd-legal-rag
$py = ".venv\Scripts\python"
```

The whole sequence after the download: re-parse (under an hour), build the index
(hours on a CPU, resumable), then evaluation (an hour or two with a local
model). Nothing below needs the network except the one-time model downloads.

## 1. Re-parse the downloaded pages

The scrape stored every page in `data/raw/`. Parsing again from that cache
applies every parser fix made since the download started. Without `--offline`
the few pages that failed during the download are fetched again; everything
else comes from the cache.

```powershell
& $py scripts/ingest.py --out data/processed      # retries failed pages; --offline to skip them
& $py scripts/ingest.py --compact-cache           # gzip any pages still stored as plain .html
```

Check `data/processed/stats.json`: act and section counts, languages, and the
number of omitted sections. `failures.jsonl` lists pages that still could not
be fetched or parsed (a few dozen at most; running the command again retries them).

## 2. Build the index

bge-m3 (≈2.3 GB, downloaded once from Hugging Face) embeds every chunk. On a
CPU this is the slow step. It checkpoints every 2,000 chunks, so if it is
interrupted just run the same command again and it continues.

```powershell
& $py scripts/build_index.py --chunks data/processed/chunks.jsonl --out data/index --bm25
```

Later rebuilds (after `ingest.py --update`) reuse the stored vector of every
chunk whose text did not change and only embed the new ones.

## 3. Retrieval evaluation (no language model needed)

```powershell
& $py scripts/eval_retrieval.py --label hybrid-final
& $py scripts/tune.py                                   # fusion weights, on data/eval/tune.jsonl only
& $py scripts/ablate.py --out results/ablation.md       # every component on/off, paired tests
& $py scripts/failure_report.py --out results/failures.json
& $py scripts/calibrate_guard.py                        # prints the abstention threshold
```

Put the threshold that `calibrate_guard.py` recommends into `BDRAG_MIN_SCORE`.

## 4. End-to-end evaluation with Ollama (free, local)

Install Ollama from ollama.com, then pull an answering model and a *different*
judging model (a model grading its own answers is biased toward them):

```powershell
ollama pull qwen2.5:7b       # answers   (~4.7 GB)
ollama pull llama3.1:8b      # judge     (~4.9 GB)
```

Short on disk? `qwen2.5:3b` (~1.9 GB) answers acceptably; or run with
`--no-judge` for the deterministic metrics only (citation validity, abstention,
refusal on unanswerable questions).

```powershell
$env:OLLAMA_NUM_CTX = "8192"
& $py scripts/eval_e2e.py --provider ollama --llm-model qwen2.5:7b `
    --judge-provider ollama --judge-model llama3.1:8b --label e2e-qwen7b
& $py scripts/calibrate_judge.py results/e2e-qwen7b.answers.json --sample 30   # grade 30 yourself
& $py scripts/calibrate_judge.py results/e2e-qwen7b.answers.json --report      # judge vs. you
```

Try `--limit 5` first to check that everything is wired up.

## 5. Run the service

```powershell
$env:RAG_LLM = "ollama"; $env:RAG_MODEL = "qwen2.5:7b"; $env:OLLAMA_NUM_CTX = "8192"
$env:BDRAG_MIN_SCORE = "<value from calibrate_guard>"
& $py -m uvicorn service.app:get_app --factory --app-dir src --port 8000
```

Open http://localhost:8000. `$env:BDRAG_VERIFY_LIVE = "1"` adds the live
check of every cited section against bdlaws (slower; needs the network).

## 6. Keeping the corpus current

```powershell
& $py scripts/ingest.py --update --out data/processed
& $py scripts/build_index.py --chunks data/processed/chunks.jsonl --out data/index --bm25
```

`--update` re-reads the site's index and downloads only new acts and the acts
that new amending acts point at.
