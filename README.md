# bd-legal-rag

A bilingual (Bangla + English) retrieval-augmented question answering system over the
statutes of Bangladesh. Ask in either language, get an answer grounded in the text of the
Acts with the section cited — or an honest refusal when the corpus does not answer.

```
                    ┌──────────── ingestion (offline) ───────────┐
 bdlaws.minlaw.gov.bd → parse Act/Chapter/Section → chunk + metadata → chunks.jsonl
                                                                          │
   ┌──────────────────────────── indexing ──────────────────────────────┐ │
   │  dense vectors (bge-m3)          BM25 (Bangla-aware tokenizer)     │◄┘
   └───────────┬──────────────────────────────┬────────────────────────-┘
               │                              │
 question ──► resolve "দণ্ডবিধির ধারা ৩০২" to the section itself
          ──► expand refs, legal synonyms, romanised Bangla
               ├─ dense top-50 (served) ─┐    │
               └─ BM25 top-50 ───────────┼── reciprocal rank fusion (measured, not served)
                                         │            │
                 in-force boost · dedupe section parts ── cross-encoder rerank (measured, CPU-slow)
                                                           │
                    support gate (refuse if weak) ─────────┤
                                                           ▼
                        LLM answer, every sentence cited [n]
                                                           │
                      guardrails: citations · verbatim quotes · language
                                   └─ one corrective re-prompt if a check fails
                                                           ▼
                           HTTP API + streaming UI · metrics · cache
```

<!-- auto:headline -->
| Measured on the full corpus (86 test questions) | |
|---|---|
| Right section in the top 5 (retrieval) | 0.85 [0.77–0.91] |
| Citations that point at a retrieved excerpt (qwen2.5:7b) | 0.99 [0.97–1.00] |
| Citations that point at a retrieved excerpt (qwen2.5:14b) | 1.00 [1.00–1.00] |
| Refuses exactly when the corpus has no answer (qwen2.5:7b) | 0.86 [0.79–0.93] |
| Refuses exactly when the corpus has no answer (qwen2.5:14b) | 0.91 [0.84–0.96] |
| Answer judged correct against the reference (qwen2.5:7b) | 0.53 [0.45–0.62] |
| Answer judged correct against the reference (qwen2.5:14b) | 0.71 [0.64–0.77] |

95% bootstrap intervals; details in [Results](#results).
<!-- /auto:headline -->

Every stage in the diagram is implemented and switchable; which ones the service
uses was decided by measurement (see [Results](#results)): on the full corpus, dense
retrieval with reference resolution beat every BM25 fusion setting, and the
cross-encoder, although the most accurate, takes minutes per query on a laptop CPU.

An agent mode sits alongside the single-shot path: the model calls `search`,
`get_section` and `follow_refs` itself for multi-hop and cross-reference questions.

## Quick start

```bash
pip install -e ".[serve]"     # or: make install
make test                     # 243 tests, all offline — no API key, no model download
make demo                     # full pipeline + ablation on the bundled sample corpus
make serve                    # API + UI on :8000
```

Then on real data:

```bash
python scripts/ingest.py --year-from 2000 --limit 30     # scrape, parse, chunk
python scripts/build_index.py --bm25                     # dense + lexical indexes
export RAG_LLM=anthropic ANTHROPIC_API_KEY=sk-...        # or openai, or ollama (free)
python scripts/ask.py --mode dense --expand-refs --resolve-refs "ধারা ৩০২ কী বলে?"
make serve                                               # API + UI on :8000
```

For generated answers, choose one provider before starting the service:

```bash
# Hosted providers
RAG_LLM=openai RAG_MODEL=gpt-4o-mini OPENAI_API_KEY=sk-... make serve
RAG_LLM=anthropic RAG_MODEL=claude-sonnet-4-5 ANTHROPIC_API_KEY=sk-... make serve

# Local Ollama (start Ollama and pull a model first)
ollama pull qwen2.5:7b
RAG_LLM=ollama RAG_MODEL=qwen2.5:7b OLLAMA_HOST=http://localhost:11434 make serve
```

Without a provider, the service returns retrieved provisions with HTTP 503 instead of
presenting an offline stub as a generated answer. Set `RAG_LLM=echo` explicitly when
testing retrieval-only behavior.

## What is in here

| Area | Module | What it does |
|---|---|---|
| Ingestion | `src/ingest/` | scrape, parse Act → Chapter → Section, structure-aware chunking, cross-references |
| Retrieval | `src/rag/` | embeddings (optionally int8), BM25, RRF fusion, reranking, MMR, parent expansion |
| Query understanding | `banglish.py`, `lexicon.py`, `query.py` | romanised Bangla, legal synonyms, query classification and routing |
| Generation | `answer.py`, `guardrails.py`, `entail.py`, `scope.py` | grounded answering, per-claim entailment, quote verification, abstention, scope and injection handling |
| Agent | `agent.py`, `tools.py`, `toolcalling.py` | multi-step retrieval, parallel tool calls, native tool-calling adapter |
| Evaluation | `src/evalkit/` | labelled set, confidence intervals, paired tests, failure taxonomy, ablation tables |
| Service | `src/service/` | HTTP API, SSE streaming, cache, rate limit, API keys, metrics, cost, tracing, UI |

Command-line entry points live in `scripts/`; `make help` lists them. Design
decisions are recorded in `docs/adr/`, the corpus is described in
`docs/DATA_CARD.md`, `docs/RUNBOOK_WINDOWS.md` walks through the full run on a
Windows laptop, and `IMPROVEMENTS.md` / `IMPLEMENTED.md` track what is done and
what is deliberately left.

## Results

Measured on the full corpus (43,966 chunks) with the 96-question evaluation set in `data/eval/eval.jsonl`; 95% bootstrap intervals, paired tests against the dense baseline. Regenerate everything with `python scripts/finish.py`.

### Retrieval ablation

| run | pipeline | k | recall@5 | recall@10 | mrr | ndcg@5 | p95 latency (ms) |
|---|---|---|---|---|---|---|---|
| bm25 | bm25 | 10 | 0.372 [0.27–0.48] | 0.436 [0.33–0.55] | 0.270 [0.19–0.36] | 0.287 [0.21–0.38] | 101 |
| dense | dense | 10 | 0.808 [0.72–0.88] | 0.884 [0.81–0.95] | 0.695 [0.61–0.78] | 0.706 [0.62–0.78] | 457 |
| hybrid | hybrid | 10 | 0.669 [0.57–0.77] | 0.756 [0.66–0.84] | 0.520 [0.43–0.61] | 0.542 [0.45–0.63] | 504 |
| +refs | hybrid +refs | 10 | 0.669 [0.58–0.77] | 0.756 [0.67–0.84] | 0.520 [0.43–0.61] | 0.541 [0.45–0.63] | 583 |
| +dedupe | hybrid +refs +dedupe2 | 10 | 0.669 [0.58–0.77] | 0.756 [0.67–0.84] | 0.520 [0.43–0.61] | 0.541 [0.45–0.63] | 608 |
| +synonyms | hybrid +refs +dedupe2 +syn +translit | 10 | 0.674 [0.58–0.77] | 0.773 [0.69–0.85] | 0.505 [0.41–0.60] | 0.532 [0.44–0.62] | 627 |
| +route | hybrid +refs +dedupe2 +syn +translit +route | 10 | 0.686 [0.59–0.78] | 0.791 [0.71–0.87] | 0.511 [0.42–0.60] | 0.539 [0.44–0.63] | 630 |
| +resolve | hybrid +refs +dedupe2 +syn +translit +route +resolve | 10 | 0.733 [0.64–0.83] | 0.837 [0.76–0.91] | 0.567 [0.48–0.65] | 0.593 [0.51–0.68] | 829 |
| +in-force | hybrid +refs +dedupe2 +syn +translit +route +resolve +in-force | 10 | 0.733 [0.64–0.83] | 0.837 [0.76–0.91] | 0.567 [0.48–0.65] | 0.593 [0.51–0.68] | 884 |
| +rerank | hybrid +refs +rerank(cross) +dedupe2 +syn +translit +route +resolve +in-force | 10 | 0.878 [0.80–0.94] | 0.948 [0.90–0.99] | 0.749 [0.67–0.82] | 0.770 [0.70–0.84] | 109172 |

```
Paired comparison on recall@5 vs 'dense' (same questions, 2000 resamples):
  bm25                       -0.436 [-0.547, -0.326]  worse  (n=86)
  hybrid                     -0.140 [-0.233, -0.041]  worse  (n=86)
  +refs                      -0.140 [-0.233, -0.041]  worse  (n=86)
  +dedupe                    -0.140 [-0.233, -0.041]  worse  (n=86)
  +synonyms                  -0.134 [-0.244, -0.023]  worse  (n=86)
  +route                     -0.122 [-0.233, -0.017]  worse  (n=86)
  +resolve                   -0.076 [-0.192, +0.035]  within noise  (n=86)
  +in-force                  -0.076 [-0.192, +0.035]  within noise  (n=86)
  +rerank                    +0.070 [-0.017, +0.157]  within noise  (n=86)
```

### Served configuration

Chosen on the tuning split (recall@5: dense 0.773, hybrid-routed 0.568, hybrid-tuned 0.773), then measured once on the test set: **dense**.

| recall@5 | recall@10 | MRR |
|---|---|---|
| 0.849 [0.77–0.91] | 0.901 [0.83–0.96] | 0.772 [0.69–0.85] |

`--mode dense --expand-refs --synonyms --transliterate --resolve-refs --boost-in-force --max-parts-per-section 2`

### Fusion weights (tuned on the separate 24-question tuning split)

```json
{
 "dense_weight": 1.0,
 "bm25_weight": 0.5,
 "rrf_k": 10,
 "candidates": 50,
 "recall@5": 0.7727
}
```

### Abstention threshold (`calibrate_guard.py`, served configuration)

```
 min_score  answer_rate  gold_kept  correct_abstain   score
    0.0321         1.00       0.86             0.00   0.430
    0.0989         0.94       0.83             0.00   0.413
    0.1657         0.94       0.83             0.00   0.413
    0.2325         0.94       0.83             0.00   0.413
    0.2993         0.94       0.83             0.00   0.413
    0.3661         0.94       0.83             0.00   0.413
    0.4329         0.94       0.83             0.00   0.413
    0.4997         0.94       0.83             0.10   0.463
    0.5666         0.92       0.80             0.40   0.601
    0.6334         0.69       0.62             1.00   0.808
    0.7002         0.17       0.17             1.00   0.587
    0.7670         0.01       0.01             1.00   0.506
```

No threshold fits both goals: refusing most unanswerable questions also refuses a large share of answerable ones, because the top dense score of an off-topic question is often as high as that of a hard real one. The service therefore ships without a score threshold (`BDRAG_MIN_SCORE` unset) and relies on the answer prompt, which tells the model to refuse when the excerpts do not answer, and on the citation checks.

### End to end (answers by a local Ollama model, judged by llama3.1:8b, on a Kaggle T4)

Same retrieval, same five excerpts per question, two answering models fixed in advance.

| | qwen2.5:7b | qwen2.5:14b |
|---|---|---|
| Correct (judge vs. reference answer) | 0.535 [0.45–0.62] | 0.709 [0.64–0.77] |
| Faithful to the cited excerpts (judge) | 0.562 [0.46–0.67] | 0.406 [0.31–0.51] |
| Cites a gold section | 0.698 [0.60–0.79] | 0.767 [0.69–0.85] |
| Citations point at retrieved excerpts | 0.990 [0.97–1.00] | 1.000 [1.00–1.00] |
| Refuses exactly when it should | 0.865 [0.79–0.93] | 0.906 [0.84–0.96] |

The judge is itself an 8B model: its scores are indicative, and the deterministic rows (citations, refusals) are the ones to trust most.

## Failure analysis

<!-- auto:failures -->
Served configuration, 86 test questions: **66 fully correct**.

| Where it failed | Questions | Meaning |
|---|---|---|
| retrieval miss | 1 | no gold section among the top 50 candidates |
| ranking miss | 11 | a gold section in the top 50, but not among the excerpts the model saw |
| citation miss | 8 | the gold section was retrieved but the answer cited another |

By question type (failures / total):

- exact_ref: 2 / 7
- multi: 2 / 6
- paraphrase: 3 / 10
- single: 13 / 63

The misses, verbatim:

- `ranking_miss` (single, en) What is the punishment for murder in Bangladesh?
- `citation_miss` (multi, bn) অবহেলা করে গাড়ি চালিয়ে কারো মৃত্যু ঘটালে কী শাস্তি হতে পারে?
- `citation_miss` (exact_ref, bn) দণ্ডবিধির ধারা ৩৪ কী বলে?
- `ranking_miss` (multi, bn) জাল দলিল বানানোর শাস্তি কী?
- `ranking_miss` (single, en) Is attempting suicide a crime in Bangladesh?
- `citation_miss` (exact_ref, en) What does Article 27 of the Constitution say?
- `ranking_miss` (paraphrase, en) Can the state take away someone's life or liberty?
- `ranking_miss` (single, bn) রাষ্ট্রপতি কীভাবে নির্বাচিত হন?
- `ranking_miss` (single, en) How much maternity leave does a female worker get under the Labour Act?
- `citation_miss` (single, bn) স্থায়ী শ্রমিককে ছাঁটাই ছাড়া চাকরি থেকে বাদ দিতে মালিককে কত দিনের নোটিশ দিতে হয়?
- `ranking_miss` (single, mixed) Labour Act অনুযায়ী maternity leave কত দিন?
- `ranking_miss` (single, bn) পুলিশের কাছে দেওয়া স্বীকারোক্তি কি আদালতে প্রমাণ হিসেবে ব্যবহার করা যায়?
- `ranking_miss` (single, en) What is the punishment for kidnapping a woman or child?
- `ranking_miss` (paraphrase, bn) দোকানদার ওজনে কম দিলে কী শাস্তি হয়?
- `citation_miss` (single, en) Who fixes the standard rent of a house?
- `citation_miss` (single, en) Which documents must be registered compulsorily?
- `ranking_miss` (single, en) What counts as dowry under the Dowry Prohibition Act 2018?
- `citation_miss` (single, mixed) RTI আবেদন করে কত দিনে তথ্য পাব?
- `retrieval_miss` (paraphrase, en) Someone threw me out of my land without legal process. Can I get it back quickly?
- `citation_miss` (single, bn) আইনগত সহায়তার জন্য কোথায় আবেদন করতে হয়?
<!-- /auto:failures -->

What the misses have in common (answers from qwen2.5:14b):

- **Ranking is the largest bucket.** In 11 of the 20 misses a gold section is among the top
  50 candidates but not among the five excerpts the model sees. They are questions about
  well-known provisions (murder, kidnapping, maternity leave, confessions to the police)
  where many sections, amendments and other acts share the same vocabulary. The
  cross-encoder fixes most of these (0.878 recall@5), so a GPU reranker over the top 20 is
  the clearest next step; on a laptop CPU it costs minutes per query.
- **Citation is the second.** In 8 misses the gold section was in front of the model and
  it cited a neighbouring excerpt instead, including two questions that name the section
  (দণ্ডবিধির ধারা ৩৪, Article 27): retrieval resolves the reference correctly every time,
  but the answer can still lean on a definition or a related section. Putting the resolved
  section first and labelling it in the prompt is the targeted fix.
- **Colloquial paraphrase is the one true retrieval miss.** "Someone threw me out of my
  land" shares almost no wording with the statute's language about a person dispossessed
  of immovable property; query rewriting (`--multi-query` / `--hyde`, one model call
  each) is the targeted fix.
- **The larger model trades citations for coverage.** qwen2.5:14b answers more questions
  correctly (0.71 vs 0.54) and refuses answerable ones less often, but it writes about one
  citation per answer against 1.45 for the 7B model, so the judge finds more uncited
  statements and scores it lower on faithfulness. Every citation it does make points at a
  retrieved excerpt.

## Deployment

```bash
cp .env.example .env            # set RAG_LLM and a key
docker compose up --build       # API + UI on :8000
docker compose --profile qdrant up   # add Qdrant when the corpus outgrows brute force
make loadtest                   # throughput and p95 against the running server
```

The image runs as a non-root user, carries no data (mount `./data`), and exposes
`/health` for orchestration and `/metrics` for Prometheus. `.github/workflows/ci.yml`
runs the tests and then the **retrieval quality gate** — a pull request that drops
recall@5 below the committed baseline fails the build.

The service is built on Starlette, the ASGI toolkit FastAPI is built on, to keep one
small dependency; porting the handlers to FastAPI is mechanical if you want pydantic
models and generated OpenAPI docs.

## Scope, limits, and the legal bit

- **This is not legal advice**, and the UI says so on every answer. It reports what the
  retrieved statutory text says, nothing more.
- The corpus is public legislation published by the Ministry of Law. The scraper
  identifies itself, rate-limits to one request per second, and caches everything so it
  never re-fetches. Put your own contact address in `src/ingest/fetch.py`.
- **Amendments are the real risk.** An excerpt marked `[amended]` may not be the text in
  force today, and the system says so rather than pretending otherwise.
- Repealed acts are excluded from retrieval by default.
- No API keys, scraped pages or indexes are committed; `data/` is gitignored apart from
  the small sample corpus used by tests and the demo.

## How it was built

[`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md) is the build log, one phase at a time
(ingestion, baseline RAG, evaluation, retrieval, generation, agent, production,
improvement pass): what was added, why, and what was deliberately left out.
