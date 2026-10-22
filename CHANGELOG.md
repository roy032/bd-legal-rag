# Changelog

Newest first. Measured numbers live in [results/](results/RESULTS.md); what is still
open is in [IMPROVEMENTS.md](IMPROVEMENTS.md).

## Unreleased

### Quality and safety (no laptop index needed)
- Citation precision in end-to-end reports: `citation_precision` (cited sections that
  are gold) is now undefined rather than 0 when nothing is cited, and a new
  `citation_support` also credits a cited excerpt that entails the claim (free lexical
  entailer by default, `--support-entailer nli` for the model). Both are printed by
  question type, and `bdrag compare --metric citation_precision` runs the paired test
  against the last run. Generation metrics are sliced by type and language.
- Fix: a generation metric the first question did not have (`gold_cited` when the first
  question was unanswerable) was silently left out of the summary.
- Red team: `data/eval/redteam.jsonl`, 52 probes (prompt injection, prompt leaks,
  quoting-tag breakout, personal data, and 14 legal questions that look like attacks)
  in Bangla, English and romanised Bangla. `bdrag redteam` runs the static checks in CI
  and, with `--provider ollama`, checks what the model says.
- Injection patterns in Bangla and romanised Bangla; imperative only, so "what if I
  disobey a court order" is not flagged. A question can no longer close its own
  `<user_question>` tag.
- Personal data (`BDRAG_REDACT_PII`, on by default): phone, NID, card and passport numbers
  and emails are replaced before the model, the cache, the logs and feedback see them.

### Observability and delivery
- Optional OpenTelemetry export of the request spans (`BDRAG_OTEL_ENDPOINT`, `otel` extra).
- Read-only root filesystem in Compose and in the CI smoke test; SBOM (SPDX, CycloneDX)
  attached to each GitHub release and kept per CI run.

### Accessibility
- axe-core (WCAG 2.1 A/AA) in CI on the home page, settings and an answer, in Bangla
  and English, light and dark, plus a keyboard-only pass (`tests/a11y/`).
- Fixed what it found: uncited sources were dimmed below the AA contrast ratio; the
  feedback box had no label; screen-reader labels were English only and now follow the
  page language; the example tabs support arrow keys with one tab stop; Enter on a
  citation moves focus to its source; the answer is `aria-busy` while it streams, so a
  screen reader reads it once instead of token by token; the theme button reports its
  state.

### Service
- Probes: `GET /livez` (the process answers) and `GET /readyz` (200 once the index and
  models are loaded; never starts the load). `/health` is unchanged.
- Admission control (`BDRAG_MAX_INFLIGHT`, `BDRAG_MAX_QUEUE`): past the limit a question
  gets the matching sections at once with `503` and `Retry-After`, instead of queueing
  behind a CPU-bound model until it times out.
- Circuit breaker on the answering model (`BDRAG_BREAKER_FAILURES`,
  `BDRAG_BREAKER_COOLDOWN`): after repeated failures the service stops calling it for a
  cooldown and answers from retrieval at once; one trial answer closes it again.
- Identical questions arriving together run the model once (single-flight).
- Streamed answers are cached too, and shared with `/ask`; a repeated question replays
  the final answer instead of generating it again.
- Prometheus histograms (`_bucket`/`_sum`/`_count`) instead of window quantiles, gauges for
  answers running and waiting, the circuit and readiness, and time to first token.
  Metrics are labelled by route template, so permalinks and scanners no longer add series.
- `LOG_FORMAT=json` structured logs carrying the request id; a caller's `X-Request-Id` is
  kept only if it is short and plain. Request bodies over `BDRAG_MAX_BODY` get `413`;
  `/feedback` is rate limited; `/metrics` can require a token (`BDRAG_METRICS_TOKEN`).
- `BDRAG_BURST` sets the rate limiter's burst.

### Delivery
- CI runs on Python 3.10 and 3.12 with a pip cache and cancels superseded runs; the
  coverage floor is 80%.
- The retrieval gate compares recall@5, MRR and nDCG@5 question by question with a
  committed baseline (`results/baselines/sample.json`) instead of a 0.8 floor.
- Docker smoke test: the image is built, started on the sample index, must pass
  `/readyz`, hold p95 under 1 s over 400 searches (`bdrag loadtest --slo-p95-ms`),
  degrade `/ask` to retrieval without a model and write JSON logs.
- CodeQL (Python and JavaScript), Dependabot (pip, Actions, Docker), pre-commit hooks
  (`make precommit`).
- Compose: gemma4:e4b by default, no Anthropic key, readiness healthcheck, dropped
  capabilities, pinned Qdrant, optional Redis profile.

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
