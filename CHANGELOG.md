# Changelog

Newest first. Measured numbers live in [results/](results/RESULTS.md); what is still
open is in [IMPROVEMENTS.md](IMPROVEMENTS.md).

## Unreleased

### Retrieval
- The topic table now also catches unpaid wages, a purchase gone wrong and defamation
  when people describe them in their own words ("my boss hasn't paid me", "the seller
  won't take it back", "telling everyone I am a thief"), not only with the trigger
  words. Each new entry needs a second word that places it (a job, a faulty purchase,
  spreading a lie), so none of the 171 committed eval questions changes topic.
- `data/eval/eval_gaps.jsonl`: 13 paraphrased gap questions (English and Bangla),
  written before the new entries. `bdrag measure-upgrades` runs it and now measures
  `served` with the topic table, as the service runs it (use `--redo`).

## 1.1.0 — 2026-10-20

Combines the work that was spread across pull requests #1 to #6 into one branch.

### Answers
- Situation and advice questions get answers that apply the cited law to the facts,
  with a legal-aid note (prompt v5, then v6 with a situation shape and uncited
  practical tips that are checked for smuggled law).
- Topic table (`src/rag/topics.py`, `BDRAG_TOPICS`): everyday situations such as unpaid
  salary, dismissal, defamation, rent, dowry, cheque bounce, arrest and road accidents
  add the sections that govern them. Checked on the full index: recall@5 0.907 → 0.936,
  MRR 0.775 → 0.804, no question worse ([notes](results/topics-full-index-2026-10-19.md)).
- Labelled general-guidance fallback (`BDRAG_GENERAL_FALLBACK`) when the indexed laws
  have nothing on the question; it cites nothing and ends with the legal-aid note.
- The requested section is labelled in the prompt; amendment year shown on excerpts.

### Retrieval
- `--translate` / `BDRAG_TRANSLATE`: search the question in both languages and fuse.
- Reranker over the top N only (`--rerank-top`), bf16/int8 precision, per-query cache.
- `--rewrite colloquial` for informal questions.

### Models
- Free answering backends: `RAG_LLM=compat` (any OpenAI-compatible server) and the
  `groq`, `gemini` and `hf` presets. `gemma4:e4b` on Ollama is the suggested local
  model ([comparison](docs/reports/free-llm-run/README.md)).
- Ollama keep-alive and warm-up, `RAG_EXCERPT_CHARS`, model picker (`BDRAG_MODELS`).

### Ingestion and tools
- PDF and scanned-PDF ingest with Bangla OCR (`bdrag pdf`, `ben+eng` Tesseract).
- `bdrag doctor`, `bdrag coverage`, `bdrag feedback-to-eval`, `bdrag measure-upgrades`,
  `bdrag topics`, `bdrag sync` (index to and from a Hugging Face dataset repo).
- Every script moved into the package as a `bdrag` subcommand; `scripts/` keeps wrappers.

### Service and UI
- Redesigned web UI: Bangla typeface, side-by-side sources, dark mode, mobile layout,
  shared answer links fixed, embeds inside a Hugging Face Space.
- Daily answer cap (`BDRAG_DAILY_LIMIT`) and a free HF Space deployment (`deploy/hf-space/`).

### Evaluation
- 8 checked scenario questions (`eval_scenarios.jsonl`), 16 drafted v2 questions
  awaiting review, judge calibration that saves the judge's verdicts.
- `QdrantStore` verified against `NumpyStore` in embedded mode.

### Fixes
- CI: `httpx2` for Starlette's test client; mypy is blocking and clean.
- Agent: parses function-call actions, fetches every named section, recovers from
  guessed act ids; Ollama reached on 127.0.0.1.

## 1.0.0 — 2026-10-12

First release: ingestion of bdlaws.minlaw.gov.bd, dense + BM25 retrieval with
reference resolution, cited answers with guardrails, agent mode, evaluation on the
full corpus (86 answerable test questions), HTTP API and streaming UI.
