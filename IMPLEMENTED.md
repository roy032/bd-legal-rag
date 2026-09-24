# Implementation ledger

Every item from `IMPROVEMENTS.md`, and what happened to it. "Done" means
implemented **and** covered by a test that runs offline in this repository.
"Partial" and "Not done" say why, in one line, without dressing it up.

Suite: **202 tests**, ruff clean, every `src/` module exercised.

## Tier 0 — defects in the first release

| # | Item | Status | Where |
|---|---|---|---|
| 1 | Blocking work on the event loop | **Done** — `run_in_threadpool` on every blocking call | `service/app.py` |
| 2 | Cache keyed by index path, not content | **Done** — `index_fingerprint()` in the cache key, test proves invalidation | `rag/pipeline.py`, `service/app.py` |
| 3 | No LLM timeout | **Done** — per-provider timeout, bounded retries with jitter, typed `LLMError` | `rag/llm.py` |
| 4 | `sys.path` hack across packages | **Done** — installable package, `pyproject.toml`, bridge module deleted | `pyproject.toml` |
| 5 | Streaming duplicated the answer logic | **Done** — one generator; `answer_question` consumes it | `rag/answer.py` |
| 6 | Parent–child retrieval promised but missing | **Done** — `ParentIndex`, `--parent-context` | `rag/parent.py` |
| 7 | `QdrantStore` never run | **Not done** — no Qdrant server in this environment; code unchanged and still unverified | — |
| 8 | Judge and answerer share a default model | **Done** — `eval_e2e` refuses a same-provider judge unless forced | `scripts/eval_e2e.py` |
| 9 | `follow_refs` same-act only | **Done** — `act_refs` captured at parse time, followed across acts | `ingest/parse.py`, `rag/tools.py` |
| 10 | `/metrics` missing HELP/TYPE | **Done** | `service/metrics.py` |
| 11 | `ablate.py` fabricated a Namespace | **Done** — `RetrievalConfig` is the interface | `rag/pipeline.py` |
| 12 | Private `_match` imported across modules | **Done** — shared `filters.matches` | `rag/filters.py` |

## Tier 1 — the five highest-value additions

| Item | Status | Notes |
|---|---|---|
| Tune weights/`rrf_k`/`k` on a held-out split | **Done** — `scripts/tune.py`, refuses to run on a file that looks like your reported set | needs your data to produce numbers |
| Romanised Bangla ("Banglish") | **Done** — lexicon + optional phonetic fallback, `--transliterate` | phonetic layer off by default, and the code says why |
| Per-claim entailment instead of citation counting | **Done (lexical)** / **Partial (NLI)** — `LexicalEntailer` tested; `NLIEntailer` written, no model download available here |
| Failure taxonomy assigning blame to a stage | **Done** — `evalkit/diagnose.py`, `scripts/failure_report.py` | five buckets, each with the work it implies |
| Feedback capture as future evaluation data | **Done** — `/feedback`, UI buttons, JSONL with question, answer and sources |

## Data and ingestion

| Item | Status |
|---|---|
| Cross-act references captured and followed | **Done** |
| Data card | **Done** — `docs/DATA_CARD.md` (counts to fill from your run) |
| Schedules, forms, appendices | **Not done** — needs real pages to parse against |
| Amendment footnote → inline marker linking | **Not done** — same reason; the heuristic detection remains |
| Point-in-time law (versions over time) | **Not done** — a project of its own, and it needs the corpus first |
| Rules, SROs, gazette notifications | **Not done** — scope decision, not a technical blocker |
| Subsection/clause tree parsing | **Not done** |
| Table extraction, OCR fallback | **Not done** — needs real scanned/table pages |
| Incremental re-crawl with ETag | **Not done** — the page cache already makes re-runs cheap |
| Ingestion quality monitor | **Partial** — `stats.json` reports the numbers to watch; no alerting |

## Chunking and indexing

| Item | Status |
|---|---|
| Chunk-size sweep | **Done** — `scripts/sweep_chunking.py`, re-chunks and re-indexes end to end |
| Parent–child retrieval | **Done** |
| Contextual retrieval (LLM context line per chunk) | **Done** — `scripts/contextualize.py` |
| int8 quantisation with exact rescoring | **Done** — `--quantize`, test proves top-k is preserved on the sample |
| Index fingerprinting | **Done** |
| Multi-field embeddings, sparse vectors in Qdrant, incremental indexing | **Not done** — the first two need a Qdrant; the third needs a corpus large enough to care |
| Exact vs approximate recall study | **Not done** — needs Qdrant |

## Retrieval

| Item | Status |
|---|---|
| Query routing by type | **Done** — `--route` |
| Legal synonym expansion | **Done** — `--synonyms` |
| MMR diversity | **Done** — `--mmr-lambda` |
| In-force boosting | **Done** — `--boost-in-force` |
| Romanised input | **Done** — `--transliterate` |
| Better Bangla stemming | **Partial** — candidate-stem matching for synonyms; the BM25 stemmer is still crude and still a flag |
| Typo tolerance | **Not done** — adversarial set includes typo questions so you can measure the gap first |
| Fine-tuning embedder / reranker | **Not done** — needs your labels and a GPU |
| ONNX / quantised reranker | **Not done** — no model runtime here |

## Generation

| Item | Status |
|---|---|
| Entailment-based faithfulness | **Done (lexical)**, **Partial (NLI)** |
| Calibrated confidence | **Done** — computed and surfaced; the code states it is uncalibrated until you plot it |
| Scope handling (advice / off-topic) | **Done** — legal-aid notice, off-topic refusal without a model call |
| Prompt-injection resistance | **Done** — user text quoted as content, prompt rule, adversarial tests |
| Prompt registry with versions | **Done** — recorded in every answer and result file |
| Model routing (cheap → strong) | **Done** — `routed_llm` |
| Structured claim output (JSON) | **Partial** — claims are extracted and scored from the text; the model is not asked for JSON |
| Answer template (operative text → plain language → caveats) | **Partial** — amended/advice caveats are automatic; the layout is not enforced |

## Evaluation

| Item | Status |
|---|---|
| Graded relevance + graded nDCG | **Done** |
| Failure taxonomy | **Done** |
| Judge calibration with Cohen's kappa | **Done** — `scripts/calibrate_judge.py` (needs your judgements) |
| Power analysis | **Done** — `scripts/power_analysis.py` |
| Variance across repeats | **Done** — `--repeats` |
| Adversarial set | **Done** — 8 questions, wired into CI |
| Cost/latency budgets in CI | **Partial** — latency is reported per run; no hard budget assertion yet |
| Inter-annotator agreement | **Not done** — needs a second human |
| Retrieval ↔ answer correlation study | **Not done** — needs a real run to correlate |

## Agent

| Item | Status |
|---|---|
| Parallel tool calls | **Done** |
| `compare_sections`, `list_acts` | **Done** |
| Cross-act following | **Done** |
| Native tool-calling adapter | **Done (unit-tested)** — never run against a live API from here, and the module says so |
| Router: single-shot vs agent | **Done** — `wants_agent()` in the service |
| Trace visualisation | **Done** — in the UI and in `--show-trace` |
| Self-consistency sampling | **Not done** — deliberate: expensive, and unproven for this task |

## Service and production

| Item | Status |
|---|---|
| Graceful degradation when the model fails | **Done** — 503 with retrieval results |
| API keys with per-key quotas | **Done** |
| Redis cache + distributed limiting | **Done** — behind the same interfaces, falls back automatically |
| Span tracing | **Done** — `service/tracing.py`, structured span logs |
| Query analytics | **Done** — JSONL log per query |
| Answer permalinks | **Done** — `/a/{id}` |
| Security headers, cost projection | **Done** |
| Load test | **Done** — `scripts/loadtest.py`, stdlib only |
| Accessibility / mobile polish | **Done** — focus styles, ARIA labels, responsive layout |
| Canary / shadow deployment | **Not done** — needs live traffic |
| Auth beyond API keys | **Not done** — out of scope for a public read-only service |

## Engineering and docs

| Item | Status |
|---|---|
| `pyproject.toml`, installable, `bdrag` entry point | **Done** |
| ruff clean, mypy configured | **Done** (mypy advisory in CI) |
| Coverage in CI with a floor | **Done** — every `src/` module is exercised |
| ADRs | **Done** — ten, in `docs/adr/` (reference resolution, in-force text, storage, live verification added) |
| Data card | **Done** |
| Blog draft | **Done** — `docs/BLOG_DRAFT.md`, with blanks where your numbers go |
| Property-based tests | **Not done** — Hypothesis is not installable in this environment |
| Pinned lockfile | **Not done** — `pyproject.toml` has ranges; pin when you deploy |
| Demo video, live deployment, published dataset | **Not done** — yours to do |

## The four things only you can do

1. Scrape the corpus and check `stats.json`.
2. Write the evaluation set by hand (`data/eval/WRITING_GUIDE.md`).
3. Run `make ablate` and paste the real table into the README.
4. Run `make failures` and write the failure-analysis section from it.

Everything in this ledger is scaffolding for those four.
