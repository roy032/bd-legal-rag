# Improvements — bd-legal-rag

Everything I can see worth doing, ordered by what it buys you. Effort is rough:
**S** ≈ an evening, **M** ≈ a weekend, **L** ≈ a week or more.

Three warnings before the list:

1. Almost nothing here is worth doing before the corpus and the evaluation set exist.
   Without them you cannot tell an improvement from a regression, and most items below
   are only meaningful as a row in the ablation table.
2. A finished project with four techniques and honest numbers beats an unfinished one
   with twelve. Pick from tier 1, ship, then continue.
3. Anything you add, you must be able to explain and defend. A technique you cannot
   justify in an interview is worse than not having it.

---

## Tier 0 — defects I know about in what I handed you

These are real, and finding them yourself in someone else's code is a good habit. Fixing
them is also the cheapest credibility you can buy.

| # | Problem | Why it matters | Fix | Effort |
|---|---|---|---|---|
| 1 | **Blocking work runs in async handlers.** Embedding, reranking and LLM HTTP calls are synchronous but sit inside `async def` endpoints, so they block the event loop. | Under two concurrent users the service serialises and latency doubles. This is the single most likely thing a backend interviewer spots. | Wrap the work in `starlette.concurrency.run_in_threadpool`, or make the handlers `def` instead of `async def` so Starlette threads them automatically. | S |
| 2 | **The answer cache is keyed by index *path*, not index *content*.** | Rebuild the index at the same path and the service keeps serving pre-rebuild answers until the TTL expires. | Hash `index.json` (embedder + count + mtime) into the cache key; clear the cache on rebuild. | S |
| 3 | **No timeout on the LLM call** in the service. | A hung provider holds the connection until the client gives up. | Per-provider timeout + return 504; add a retry with jitter for 5xx. | S |
| 4 | **`textutils_bridge.py` manipulates `sys.path`** to import across packages. | It is the kind of hack that makes a reviewer distrust the rest. | Add `pyproject.toml`, make it one installable package, import normally. | S |
| 5 | **The streaming path duplicates `answer_question`'s logic.** | Two code paths drift; a guardrail fix applied to one silently misses the other. | Factor the shared part into one generator and have the non-streaming version consume it. | M |
| 6 | **Parent–child retrieval is described in the Phase 1 README but never implemented.** | Documentation that overstates the code is the worst kind of bug in a portfolio. | Either implement it (search child chunks, return the parent section) or delete the claim. | M |
| 7 | **`QdrantStore` has never been run.** | Shipping untested code is a choice you have to own. | Run it once against a local Qdrant, add one integration test marked skip-if-unavailable, and compare its top-k against `NumpyStore` on the same queries — that comparison is itself a good README table. | M |
| 8 | **The judge and the answering model both default to `$RAG_LLM`.** | A model grading its own output inflates faithfulness. | Require `--judge-provider` to differ, or refuse to run and say why. | S |
| 9 | **`follow_refs` only follows references inside the same act.** | "as defined in the Companies Act, 1994" is common and silently ignored. | The parser already collects act links; build a title → `act_id` map and resolve across acts. | M |
| 10 | **`/metrics` emits no `# HELP` / `# TYPE` lines** and counters lack a `_total` convention in places. | Prometheus will scrape it, but a reviewer who knows the format will notice. | Emit proper metric metadata. | S |
| 11 | **`ablate.py` fabricates an `argparse.Namespace`** to build configs. | Works, but it is a smell — the config object should be the interface. | Have `build_pipeline` take `RetrievalConfig` directly; let the CLI construct one. | S |
| 12 | **`lexical.py` imports `_match` (a private name) from `store.py`.** | Private-by-convention imported across modules. | Promote it to a shared `filters.py`. | S |

---

## Tier 1 — do these five first, after the corpus and eval set exist

These give the most improvement per hour, and each one becomes a row in your table or a
paragraph in your README.

1. **Tune fusion weights, `rrf_k` and `k` on a held-out split** (S).
   You already have every knob and the measurement harness; you have never actually
   searched the space. A small grid search over the tuning split usually finds several
   points of recall for free. Write `scripts/tune.py`, report the search, and state
   plainly that the tuning split is separate from the reported set.

2. **Romanised Bangla ("Banglish") query handling** (M).
   Real users type `dhara 302 ki bole`, `bhara briddhi`. Neither your embeddings nor BM25
   handle it. A transliteration layer (Avro-style rules, or `indic-transliteration`) that
   generates a Bangla variant of a romanised query, searched alongside the original, is a
   genuine, locally-specific engineering contribution — and it is the kind of detail that
   makes an interviewer remember this project.

3. **Per-claim entailment checking instead of per-sentence citation counting** (M).
   Today a sentence passes if it carries a `[n]`. Upgrade to: does the cited excerpt
   actually *entail* the claim? A small multilingual NLI model scores each
   (claim, cited excerpt) pair. This turns "it cites its sources" into "its claims are
   supported", which is the difference between a demo and a system you would let a person
   rely on.

4. **A failure taxonomy that assigns blame automatically** (S).
   For every failed question, decide from data which stage failed: gold not in the
   candidate pool (retrieval), in the pool but not in top-k (ranking), in top-k but not
   cited (generation), cited but wrong answer (reasoning). A `scripts/failure_report.py`
   that prints these four counts tells you exactly where to spend the next weekend, and
   the resulting paragraph is the best section of your README.

5. **User feedback capture, stored as future evaluation data** (M).
   Thumbs up/down plus an optional comment on each answer in the UI, written to a JSONL
   file with the question, the retrieved sections and the config. Three things fall out:
   a growing evaluation set from real questions, a demo that looks like a product, and an
   honest answer to "how would you improve this in production?" — you already are.

---

## Data and ingestion

| Improvement | Why | Effort |
|---|---|---|
| Parse **schedules (তফসিল), forms and appendices** | Fee schedules and forms are exactly what people ask about, and they are currently missing | M |
| Link **amendment footnotes to the inline marker**, store amendment date and amending act | Right now footnotes are collected but not attached to the text they modify; "is this the current text?" is unanswerable | M |
| **Point-in-time law**: keep versions, answer "what did this say in 2015?" | The hardest and most impressive feature in this domain; almost no free tool does it | L |
| Resolve **cross-act references** into act ids | Unblocks agent `follow_refs` across acts | M |
| Ingest **rules, SROs and gazette notifications** | Acts alone answer maybe half of real questions | L |
| Parse the **subsection/clause tree** into structured JSON instead of flat text | Enables precise citation ("section 2(c)(iv)") and better chunk boundaries | M |
| **Table extraction** for schedules | Tables flattened to text retrieve and read badly | M |
| **OCR fallback** for acts published as scanned images (tesseract + Bangla data) | Some older acts are images; they are silently absent today | M |
| **Incremental re-crawl** with ETag/Last-Modified + a diff report | Turns a one-off scrape into a maintained corpus; the diff report doubles as an amendment feed | M |
| **Ingestion quality monitor**: assert section counts against the site's own table of contents, alert on drift | Catches the day the site changes its markup, instead of discovering it in an answer | S |
| A **data card** documenting provenance, coverage, licence and known gaps | Standard practice for published datasets; cheap and looks professional | S |
| Consider **case law** (Supreme Court judgments) | Enormous value, but check licensing and scale before starting | L |

## Chunking and indexing

| Improvement | Why | Effort |
|---|---|---|
| **Chunk-size ablation** (`--max-chars` 800 / 1200 / 1800 / 2500) | You built the knob and never measured it | S |
| **Parent–child retrieval** | Precision of small chunks, context of whole sections | M |
| **Contextual retrieval**: prepend a one-line LLM-written context to each chunk before embedding | Reported large recall gains elsewhere; costs one cheap call per chunk, once | M |
| **Multi-field embeddings**: embed the section heading separately from the body, fuse | Headings are short and highly discriminative in statutes | M |
| **Sparse vectors in Qdrant** so hybrid runs server-side | Removes the two-index split and scales past memory | M |
| **Vector quantisation** (int8/binary) with full-precision rescoring | 4–32× memory reduction; measure the recall cost and report it | M |
| **Exact vs approximate recall study** (`NumpyStore` as ground truth vs Qdrant HNSW) | A table almost no portfolio project has, and you are one afternoon from it | S |
| **Index fingerprinting and blue/green swap** | Rebuild without downtime or stale caches | M |
| **Incremental indexing** of changed sections only | Full rebuilds get slow past ~100k chunks | M |

## Retrieval

| Improvement | Why | Effort |
|---|---|---|
| **Query routing**: exact-reference questions → BM25-first, conceptual → dense-first | Cheaper and better than running everything through the same pipeline | S |
| **Romanised Bangla transliteration** (tier 1 above) | Real user behaviour | M |
| **Legal synonym dictionary** (উচ্ছেদ ↔ eviction ↔ বেদখল) | Bridges the vocabulary gap between people and statutes | S |
| **Proper Bangla stemming/morphology** (or SentencePiece subwords for BM25) | Your current suffix stripper is crude; measure both | M |
| **Typo tolerance** (fuzzy BM25 terms, character n-grams) | Bangla typing is error-prone | M |
| **MMR / diversity** in the final top-k | Stops five near-identical chunks filling the context | S |
| **Fine-tune the embedder on your own labelled pairs** (LoRA, mined hard negatives) | The strongest possible result: "domain fine-tuning beat the off-the-shelf model by N points on my own benchmark" | L |
| **Fine-tune the reranker** on the same data | Usually cheaper than fine-tuning the embedder and often bigger | L |
| **ONNX / quantised reranker** for CPU latency | Makes the reranker affordable on a free-tier host | M |
| **In-force boosting**: rank current law above superseded text | Legal correctness, not just relevance | S |

## Generation

| Improvement | Why | Effort |
|---|---|---|
| **Structured answers** (JSON: claims[], each with citation and quoted span) | Makes per-claim verification mechanical instead of regex-based | M |
| **Entailment-based faithfulness** (tier 1) | Real grounding, not citation presence | M |
| **Calibrated confidence** shown to the user, from reranker score + support count | Honest uncertainty beats a confident-sounding paragraph | M |
| **Answer template**: operative text → plain-language explanation → caveats (amended / repealed / consult a lawyer) | The format a person actually needs from legal text | S |
| **Model routing**: cheap model for simple questions, strong model when retrieval is ambiguous | Cost control you can quantify | M |
| **Prompt registry with versions**, evaluated per version | Prompts are code; treat changes as changes | S |
| **Prompt-injection resistance test** (a question containing "ignore the excerpts and say X") | You accept free text from the internet; show you thought about it | S |
| **Out-of-scope handling**: "should I sue my landlord?" → explain, decline to advise, point to legal aid | Domain-appropriate safety, and interviewers notice it | S |
| **Stream the agent's final answer** as well | Consistency of UX between modes | S |

## Evaluation

| Improvement | Why | Effort |
|---|---|---|
| **Inter-annotator agreement** on 20–30 questions (Cohen's kappa) | Tells you the ceiling of your own labels; almost nobody does this | S |
| **Judge calibration**: agreement between the LLM judge and your own verdicts on ~50 answers | Without it, faithfulness is a number from an unaudited machine | S |
| **Graded relevance** (2 = answers it, 1 = related, 0 = no) and graded nDCG | Sharper signal than binary, at the cost of more labelling | M |
| **Variance across runs** for anything LLM-dependent (3 seeds, report spread) | One run of an LLM metric is an anecdote | S |
| **Adversarial set**: typos, romanised input, very long questions, injection attempts, questions about repealed law | Robustness you can point at | M |
| **Statistical power note**: how many questions you need to detect a 5-point difference | One paragraph that signals you understand your own methodology | S |
| **Regression tests for specific bugs** (a fixed bug becomes a permanent question) | Standard engineering discipline applied to model quality | S |
| **Retrieval↔answer correlation study**: does recall@5 predict correctness? | Justifies using the cheap metric for fast iteration | S |
| **Cost and latency budgets asserted in CI** | Stops a "small" quality win from tripling the bill | S |
| **Blind A/B with three friends** on 20 questions, two configs | Human preference alongside automatic metrics | M |

## Agent

| Improvement | Why | Effort |
|---|---|---|
| **Native tool-calling implementation** behind the same interface | What you would ship; keep the text protocol as the portable fallback | M |
| **Router: single-shot vs agent**, chosen by a cheap classifier | The agent costs 4× for no gain on simple questions — route and prove it | M |
| **Parallel tool calls** in one step | Halves latency on multi-hop questions | M |
| **`compare_sections` tool** | "What's the difference between 302 and 304A?" is a top-5 real question | S |
| **Trace visualisation** in the UI | Makes the demo legible to non-technical viewers | S |
| **Self-consistency** (sample n, keep the answer whose citations agree) | Expensive; only for high-stakes questions | M |

## Service and production

| Improvement | Why | Effort |
|---|---|---|
| **Redis** for cache and rate limiting | In-process state does not survive a restart or span replicas | M |
| **API keys with per-key quotas** | Required the moment it is public and costs money | M |
| **OpenTelemetry / Langfuse tracing** of every stage | "I can see which stage took 400 ms for that request" | M |
| **Graceful degradation**: LLM down → return retrieval results with a notice | Never show a blank error when you have something useful | S |
| **Query analytics dashboard**: top questions, refusal rate, zero-result queries | Zero-result queries are a free roadmap | M |
| **Shadow / canary evaluation**: run the new pipeline alongside the old on live traffic, compare offline | The professional way to ship a retrieval change | L |
| **Load test** (k6 or locust) with a published throughput/latency table | Turns "it's fast" into a number | S |
| **Cost dashboard**: cost per query, monthly projection at N users | The question every hiring manager has | S |
| **Security pass**: CSP headers, dependency scanning (`pip-audit`), secret scanning in CI, no prompt content in logs by default | Cheap, visible diligence | S |
| **Accessibility and mobile polish**, proper Bangla webfont | Most of your users would be on a phone | S |
| **Shareable answer permalinks** | Makes the demo spreadable | M |

## Engineering quality

| Improvement | Why | Effort |
|---|---|---|
| `pyproject.toml`, installable package, console entry points (`bdrag ask ...`) | Removes every `sys.path` hack | S |
| **ruff + mypy + pre-commit**, enforced in CI | Table stakes for a repo people read | S |
| **Coverage report** with a badge | You have 142 tests; show what they cover | S |
| **Property-based tests** (Hypothesis) for the tokenizer, chunker and fusion | Finds Unicode edge cases you will never think of | M |
| **Single typed config** (YAML + env override) instead of scattered flags | One place to see what the system is running | M |
| **ADRs** (short architecture decision records) for the five biggest choices | Your README already argues them; formalising is half a day | S |
| **Pinned dependencies / lockfile**, pinned base image digest | Reproducibility | S |
| **Demo GIF and a 2-minute video** in the README | The single highest-return hour in this whole document | S |

## Portfolio

| Improvement | Why | Effort |
|---|---|---|
| **Deploy it publicly** (Fly.io, Render, or a HF Space) with a small local model or a rate-limited key | A link beats a repo | M |
| **Blog post: "Retrieval for Bangla legal text — what actually worked"** with your ablation table | This is what gets shared, and what interviewers read before the code | M |
| **Publish the question set** as an open dataset with a data card | A real contribution: there is very little Bangla legal IR evaluation data | M |
| **Write up the negative results** — what did not help and why | Rarer and more convincing than another win | S |
| Present at a BRACU CSE club session | Practice explaining it out loud before an interview does it for you | S |

---

## Deliberately not worth doing

- **GraphRAG over statutes.** The structure is already explicit (act → section → refs);
  a graph database adds machinery without adding information you do not have.
- **Fine-tuning the answering LLM.** Grounding is a retrieval problem here; fine-tuning
  the generator is expensive and mostly changes style.
- **Writing your own vector database.** `NumpyStore` for correctness, Qdrant for scale.
  There is no third thing worth your time.
- **Kubernetes, microservices, a message queue.** One container serves this fine, and
  over-engineering reads as inexperience rather than ambition.
- **Multi-agent "crews".** One bounded agent already needs careful stopping rules; five
  of them mostly multiply failure modes.
- **Chasing the newest embedding model every month.** Your ablation harness tells you
  whether a swap helps; do it once a quarter, not weekly.
- **A mobile app.** The web UI works on a phone.

---

## A three-weekend plan, if you want one

**Weekend 1 — make it real.** Scrape, check `stats.json`, fix what the parser breaks on,
write the first 60 questions, run the sweep, paste the real ablation table into the README.

**Weekend 2 — make it defensible.** Tier 0 defects 1–4 and 8. Tune on a held-out split.
Add the failure taxonomy report and write the failure-analysis section from it.

**Weekend 3 — make it visible.** Deploy it, record the demo video, add feedback capture,
write the blog post. Then stop adding techniques and start applying for jobs — the project
is already stronger than most of what it will be compared against.
