# Changelog

Newest first. Measured numbers live in [results/](results/RESULTS.md); what is still
open is in [IMPROVEMENTS.md](IMPROVEMENTS.md).

## Unreleased

### Published accuracy scorecard
- **`/accuracy`**, a public page in English and Bangla (linked from the footer), plus
  [docs/ACCURACY.md](docs/ACCURACY.md) and a table at the top of the README, all rendered
  from one file, `src/service/static/scorecard.json` (also served as JSON). Five blocks:
  retrieval, answers and citations, red team (input checks), red team (model output) and a
  lawyer's grades. A block nobody has measured is shown as "not measured yet" with its
  command; the known weak spots are listed on the page.
- **`bdrag scorecard add <block> <result file>`** is the only way a number gets in: it reads
  a `bdrag eval`, `bdrag e2e`, `bdrag redteam --json-out` or `bdrag review score --json`
  file, records its date and setup, copies the per-question rows to `results/published/`
  and re-renders. `bdrag scorecard check` runs in CI and fails when a page is stale or the
  red-team block no longer matches today's checks.
- `bdrag e2e` now records `answer_model` and `judge_model` in the result file.

### Lawyer review of the answers
- **`bdrag review`**, the kit for the launch audit's top open item: nobody qualified had
  read the answers. `bdrag review sheet <run>.answers.json --n 50` takes a sample balanced
  across language and question type and writes `review.html`, a single page a reviewer
  opens in any browser: the answer, the cited sections with links to bdlaws, the drafted
  reference answer (marked as unchecked), and a five-question rubric in English and Bangla
  (right law, right sections, accurate, safe, clear; "should it have answered" when the
  service declined). Grades are kept in the browser as they go and come back as a CSV
  from a Download button; `grades.csv` is the same sheet for a spreadsheet.
- `bdrag review score grades.csv` reports each criterion with a 95% interval, by
  language, lists every unsafe or inaccurate answer with the reviewer's notes, and exits
  1 unless the launch bar is met: no answer unsafe, at least 85% fully accurate, at least
  30 graded. `--judge-labels` hands the verdicts to `bdrag calibrate-judge`, so the
  judge model is measured against a lawyer. Rubric for the reviewer:
  [docs/review/RUBRIC.md](docs/review/RUBRIC.md).
- The page now states the scope under the answer box: Acts from the Laws of Bangladesh
  website only, no court decisions, rules, SROs or gazette notifications yet.

### Operations: retention, backups, freshness, alerts
- **Retention for the logs.** The query and feedback logs hold visitors' questions and
  used to grow forever. Rows older than `BDRAG_LOG_DAYS` (90, the same as shared
  answers) are deleted by a background task that runs at startup and every
  `BDRAG_HOUSEKEEPING_S` (6 h), together with the shared-answer purge.
  `retention_deleted_total{store}` counts what went; `/stats` shows the policy and the
  last run. Appends and prunes share a lock, so no row is lost mid-rewrite.
- **`bdrag backup`**: a consistent copy of `answers.sqlite3` taken while the service
  runs (SQLite online backup), plus the logs, in one `.tar.gz` with a SHA-256 manifest;
  keeps the newest 14. `--verify` checks checksums and the database's integrity;
  `--restore` verifies first and will not overwrite without `--force`.
- **Index age.** `index.json` records `built_at`; `/health`, `/readyz` and `/stats` report
  it, `/metrics` exports `index_age_seconds`, and `bdrag doctor` warns past
  `BDRAG_INDEX_MAX_AGE_DAYS` (45). Older indexes fall back to the file's date.
- **`bdrag gaps`**: the questions that were refused, got general guidance only, failed a
  guardrail or got a thumbs-down, grouped and ranked by distinct visitors, with the
  topic-table entry each matched (or none). The query log now records `general`.
- **SLOs and alerts as code** in `deploy/monitoring/`: availability 99.5% with
  multi-window burn-rate alerts, `/search` p95 under 1 s, answers p95 under 120 s, model
  circuit open, shedding, daily cap, stale index. `promtool check` and `promtool test
  rules` run in CI; a unit test fails if a rule names a metric the service does not
  export. `docker compose --profile monitoring up` starts Prometheus with them.
- **`bdrag probe`** and an uptime workflow: every 30 minutes (once `BDRAG_URL` is set as a
  repository variable) the live service is checked like a visitor would hit it; one
  issue labelled `uptime` stays open while it fails and closes itself on recovery. The
  Docker CI job runs the same probe against the built image.
- `bdrag <tool>` now exits with the tool's status, so `bdrag backup --verify` and
  `bdrag semcache` fail a script when they fail.

### Launch pages and privacy
- `/privacy` (and `/terms`): what is kept and for how long, who sees a question, the
  not-legal-advice terms and the 16430 legal-aid line, in English and Bangla, linked
  from the footer. Review it before a public launch; it describes the default settings.
- `/robots.txt` keeps shared answers and the API out of search engines;
  `/manifest.webmanifest` lets a phone add the app to its home screen.
- The query log stores a salted hash of the client instead of its IP address; the salt
  lives only as long as the process.
- The accessibility check covers the privacy page and the follow-up states.

### Follow-up questions
- The web app has a **Follow up** button under each answer. `/ask` and `/ask/stream` take
  `follow_up_of` (an answer id); the server reads up to three earlier turns from its own
  answer store, rewrites the follow-up into a standalone question (`rag/chat.py`), and
  retrieves and answers with that. The reply keeps the visitor's words as `question`
  and adds `searched_for` and `parent`; the page shows both. A request cannot supply a
  history of its own, and an unknown id is answered as a plain question.

### Shared links that last
- Shared answers are stored in SQLite (`BDRAG_ANSWERS_DB`, default
  `data/answers.sqlite3`) instead of a 500-entry dict in memory, so a link pasted into a
  chat still works after a restart, a deploy, or 500 newer answers. Deleted after
  `BDRAG_ANSWER_DAYS` (90). Falls back to memory if the file cannot be opened.
- A shared link's page carries the question as its title and the answer's opening as
  the link-preview text, and `noindex`. The page shows the date the answer was given.

### Faster repeat questions
- Paraphrase cache (`BDRAG_SEMANTIC_CACHE`, `auto` by default): a reworded question gets
  the earlier answer in milliseconds instead of a new 20 to 115 second answer. Gated on
  the settings, script, numbers, negations, topic and the top-5 sections of both
  questions, then on bge-m3 similarity at 0.965. That threshold merged 40 of 60
  paraphrases and 0 of 8,250 near misses (`data/eval/paraphrases.jsonl` plus every eval
  pair with different gold sections). The page names the question the answer was for.
- `bdrag semcache` measures the threshold for an embedder and fails when a near miss
  would merge; with `--index` it also applies the section-overlap gate.
- Query embeddings are memoised, so one request no longer embeds the same question for
  each act it searches.

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
