# Production upgrades, and what comes after them

Written 2026-10-21 against `main` = `ea3e0e6` (1.1.0 plus PR #8). Constraint unchanged:
free or local models only, no Anthropic API.

## Already in place before this round

Request ids, a Prometheus endpoint, a TTL answer cache keyed by the index fingerprint,
token-bucket rate limits per IP and per API key (Redis when there are replicas), a
daily answer cap, security headers and CSP, a non-root two-stage image, a retrieval
regression gate with paired bootstrap, an adversarial suite in CI, judge calibration,
and graceful degradation to retrieval when the model throws.

## Done in this round

| Upgrade | Why it matters |
|---|---|
| `/livez` and `/readyz` probes; the image's healthcheck uses readiness | `/health` loads the models, so a probe on it could pile up behind a minute-long load |
| Admission control (`BDRAG_MAX_INFLIGHT`, `BDRAG_MAX_QUEUE`) | a CPU model serves one answer at a time; past the queue a visitor gets the sections now instead of a timeout later |
| Circuit breaker on the answering model | a dead Ollama or an exhausted free quota stops costing every visitor a full timeout |
| Single-flight for identical concurrent questions | a shared link opened by twenty people runs the model once |
| Streamed answers cached and shared with `/ask` | the UI streams, so before this the cache almost never served the page |
| Histograms, gauges, time to first token, route-labelled metrics | quantiles that aggregate across replicas; no series explosion from permalinks and scanners |
| JSON logs with the request id in every line | one `jq` filter follows a request through retrieval, model and guardrails |
| Body-size limit, rate-limited `/feedback`, `/metrics` token, safe `X-Request-Id` | closes a disk-fill path and a log-forging path |
| CI on Python 3.10 and 3.12, pip cache, cancel superseded runs | 3.10 is the declared minimum and was never tested |
| Quality gate against a committed baseline on recall@5, MRR and nDCG@5 | it was a floor of 0.8 because `results/baseline.json` is git-ignored |
| Docker smoke test with a latency SLO | the image must boot, pass readiness, hold p95 under 1 s for 400 searches, degrade `/ask`, and log JSON |
| CodeQL, Dependabot (pip, actions, Docker), pre-commit | supply-chain and static analysis on every pull request |

Operating notes are in [docs/OPERATIONS.md](../OPERATIONS.md).

## Next, in order

Effort: S under a day, M one to three days.

| # | Upgrade | Effort | Needs the laptop | Why |
|---|---|---|---|---|
| 1 | **CI gate on the real questions.** Build a fixture corpus of every gold chunk in the 171 eval questions plus their 20 nearest neighbours from the full index (a few MB), commit it, and gate BM25 + topics + reference resolution on it in CI | M | yes (export from `data/index`) | today CI gates 6 sample questions; topic-table or lexicon regressions on real questions are only caught on the laptop |
| 2 | **Run `RUN_UPGRADES.bat`** and serve translate and the reranker only where they win | S | yes | still the largest open measurement; everything since 1.0 that touches retrieval is unmeasured on answers |
| 3 | **Citation precision in e2e reports**: share of cited sections that are gold or entailed, per question type, with the paired test against the last run | S | no (code) / yes (run) | answer quality is judged by one uncalibrated 8B judge; a cheap, judge-free number belongs next to it |
| 4 | **Semantic cache for paraphrases**, gated hard (same detected topic and act, cosine above a threshold tuned on the tune split to zero false merges) | M | yes (to tune) | on a CPU model a cached answer is the difference between 60 s and 50 ms; exact-match caching misses "what is the punishment for murder" vs "murder punishment" |
| 5 | **OpenTelemetry export** of the existing spans (`BDRAG_OTEL_ENDPOINT`), optional dependency | S | no | the span shape already matches; Grafana Tempo or Jaeger then show retrieval vs model time per request |
| 6 | **Prompt-injection and PII red-team set** grown from 8 to ~50 (Bangla and romanised), run in CI with the echo provider and on the laptop with gemma4 | M | partly | the service is public on a Space; refusal and scope rules are only as good as the adversarial set |
| 7 | **Read-only root filesystem and SBOM** in the image (`--read-only` with a tmpfs for caches; `syft` SBOM attached to releases) | S | no | container hardening that costs nothing at runtime |
| 8 | **Contextual chunk headers re-run with gemma4**, then re-embed and ablate | M | yes | the "many acts share vocabulary" ranking misses remain the largest failure bucket |
| 9 | **Accessibility audit of the UI** (axe in CI on the built page, keyboard-only pass, Bangla screen-reader labels) | S | no | the page is the product for most visitors |

Not recommended now: a vector database server (43,966 chunks fit in memory and search
in milliseconds), Kubernetes manifests (one container on a laptop or a Space), and
fine-tuning (the eval set is too small to show a gain).
