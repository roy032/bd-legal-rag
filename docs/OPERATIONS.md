# Operating the service

What the service does when it is busy or its answering model is down, and what to
watch. Settings are environment variables; `.env.example` lists them all.

## Probes

| Endpoint | Use it for | Answers |
|---|---|---|
| `GET /livez` | liveness (restart the container if it fails) | `200` whenever the process can answer HTTP; loads nothing |
| `GET /readyz` | readiness (send traffic only when it passes) | `200` once the index and models are loaded, `503 {"status": "loading"}` before, `503 {"status": "failed", "error": ...}` if the load failed |
| `GET /health` | a person checking what is loaded | loads the index on first call, then reports chunks, embedder, model and whether Ollama answers |

`BDRAG_PRELOAD=true` (the default from the environment) starts loading at startup, so
`/readyz` turns green without a visitor paying for the load. The Docker image's
`HEALTHCHECK` uses `/readyz`.

## When the model is slow or down

A local 4B model on a laptop CPU answers one question at a time in 20 to 120 seconds;
a free hosted model has a quota and can disappear. Three mechanisms keep the page
responsive (`src/service/resilience.py`):

| Mechanism | Setting | What a visitor sees |
|---|---|---|
| **Admission control**: at most `BDRAG_MAX_INFLIGHT` answers run at once, `BDRAG_MAX_QUEUE` more wait | defaults 2 and 8; `BDRAG_MAX_INFLIGHT=0` turns it off | past the limit, the matching sections straight away (`503`, `Retry-After`, `degraded: true`) instead of a wait that ends in a timeout |
| **Circuit breaker**: after `BDRAG_BREAKER_FAILURES` model failures in a row, stop calling it for `BDRAG_BREAKER_COOLDOWN` seconds; then one trial answer decides | defaults 3 and 30 s; `0` failures turns it off | while open, the matching sections at once, with a note that the model is paused |
| **Single-flight**: identical questions arriving together (a shared link, a refresh) run the model once | always on | the same answer, sooner |

Answers are cached for `BDRAG_CACHE_TTL` seconds, keyed by the question and every
setting that changes the answer (index fingerprint, model, k, retrieval settings).
`/ask` and `/ask/stream` share the cache, so a repeated question replays its answer.

### Paraphrase cache

On a CPU model an answer takes 20 to 115 seconds, and people ask the same thing in
different words. `BDRAG_SEMANTIC_CACHE` (default `auto`) serves an earlier answer to a
question that means the same thing. Every one of these must hold before it does:

| Gate | Why |
|---|---|
| same settings as the exact cache key (model, k, index, retrieval, agent, language) | a different pipeline gives a different answer |
| same script (Bangla, Latin, mixed) | the answer is written in the question's language |
| same numbers, Bangla or ASCII digits | "section 302" must never get the answer for 304 |
| same count of negations (not, without, না, নয়, ছাড়া, -নি ...) | "pays rent regularly" vs "does not pay rent" |
| same everyday situations from the topic table | a dowry question and a dowry-murder question differ |
| the two questions' dense top-5 sections overlap by `BDRAG_SEMANTIC_OVERLAP` (0.6: four of five) | the model would have been shown the same provisions |
| cosine of the query embeddings at least the threshold | measured per embedder with `bdrag semcache` |

`auto` uses the measured threshold for the index's embedder (bge-m3: 0.965, which
merged 40 of 60 paraphrases and none of 8,250 near misses,
[report](reports/semantic-cache-2026-10-22.md)) and is off for any other embedder. A
number sets the threshold yourself; run `bdrag semcache --index data/index` first to
see what it merges. Refusals and general guidance are not offered to paraphrases. A
served answer carries `cache_match` (the earlier question and the similarity) and the
page shows that question, so a wrong merge is visible. `semantic_cache_hits_total`
counts hits; `/stats` shows the cache size and hit rate.

Query embeddings are also memoised (1,024 questions), so the several searches one
request makes (the question, inside a named act, inside a topic's act) embed it once.

Sizing `BDRAG_MAX_INFLIGHT`: Ollama on a CPU runs one generation at a time
(`OLLAMA_NUM_PARALLEL=1`), so a second in-flight answer only waits inside Ollama;
2 keeps the next one's retrieval overlapped with the current generation. With a
hosted model, raise it to what the provider's rate limit allows.

## Metrics

`GET /metrics` is Prometheus text. Set `BDRAG_METRICS_TOKEN` to require
`Authorization: Bearer <token>` when the service is public.

| Metric | Type | Meaning |
|---|---|---|
| `requests_total{path,status}` | counter | requests, labelled by route template (`/a/{answer_id}`, `unmatched` for unknown paths) |
| `request_seconds_bucket{path,le}` | histogram | request latency |
| `answer_seconds_bucket{agent,le}` | histogram | time to a complete answer |
| `ttft_seconds_bucket{le}` | histogram | streaming: time to the first answer token |
| `answers_total{agent,outcome}` | counter | answered or refused |
| `shed_total`, `circuit_open_total`, `degraded_total` | counter | answers given from retrieval only, by reason |
| `singleflight_shared_total`, `cache_hits_total` | counter | answers that did not need the model |
| `inflight_answers`, `queued_answers`, `circuit_open`, `ready` | gauge | state now |

Useful queries:

```promql
# p95 time to a complete answer over 5 minutes
histogram_quantile(0.95, sum by (le) (rate(answer_seconds_bucket[5m])))
# share of questions answered from retrieval only
sum(rate(shed_total[5m]) + rate(circuit_open_total[5m]) + rate(degraded_total[5m]))
  / sum(rate(answers_total[5m]))
```

Also `index_age_seconds` (gauge, since the index was built), `retention_deleted_total{store}`
(rows the retention policy deleted), `feedback_total{rating}` and `daily_limit_total`.

## SLOs and alerts

The rules are code, in [`deploy/monitoring/alerts.yml`](../deploy/monitoring/alerts.yml),
checked and unit-tested with `promtool` in CI
([`alerts.test.yml`](../deploy/monitoring/alerts.test.yml)).
`docker compose --profile monitoring up` starts Prometheus with them on :9090.

| SLO | Target | Alert |
|---|---|---|
| Availability: requests that are not 5xx (`/readyz` while loading excluded) | 99.5% over 30 days | `BdragErrorBudgetFastBurn` pages at 14.4× burn (1 h and 5 min windows); `BdragErrorBudgetSlowBurn` tickets at 6× (6 h and 30 min) |
| `/search` latency | p95 under 1 s | `BdragSearchSlow` after 15 min |
| Answer latency | p95 under 120 s (laptop CPU; lower it on a GPU or a hosted model) | `BdragAnswersSlow` after 30 min |

Other alerts: `BdragDown` (scrape fails 5 min), `BdragNotReady` (15 min),
`BdragModelCircuitOpen` (5 min: the model is down, visitors get sections only),
`BdragShedding` (over 10% of answers retrieval-only for 15 min), `BdragDailyCapReached`,
`BdragIndexStale` (index older than 45 days). Each carries a one-line runbook.

Without a Prometheus server, the uptime workflow is the free fallback:
set the repository variable `BDRAG_URL` and
[`.github/workflows/uptime.yml`](../.github/workflows/uptime.yml) runs `bdrag probe`
every 30 minutes (alive, ready, a canary search, the home page, index age under 60 days).
While it fails one issue labelled `uptime` stays open; it closes on the next pass. Run
the same check by hand with `bdrag probe --url <base url>`.

## Logs

`LOG_FORMAT=json` writes one JSON object per line: an access line per request
(`request_id`, `method`, `path`, `route`, `status`, `ms`) and a trace line per answer
with each stage's time. Every line logged while a request runs carries its
`request_id`, which is also returned in the `X-Request-Id` header; send your own
(letters, digits, `._:-`, up to 64 characters) to follow a request across services.

```bash
LOG_FORMAT=json bdrag serve 2>&1 | jq 'select(.status >= 500 or .level == "error")'
```

### Traces in Jaeger or Grafana Tempo

The trace line can also go to OpenTelemetry. Install the extra and point the service
at an OTLP/HTTP collector:

```bash
pip install -e ".[otel]"
docker run -d -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one   # a local viewer
BDRAG_OTEL_ENDPOINT=http://localhost:4318/v1/traces bdrag serve
```

Each request becomes a `bdrag search` or `bdrag ask` span carrying the request id, with
a child per stage (`retrieve`, `answer`, `degraded_retrieval`). `OTEL_SERVICE_NAME`
renames the service (default `bd-legal-rag`). A collector that is down costs a warning
in the log, never a failed request. Without the endpoint nothing is exported.

## Personal data

People describe their own case and paste their phone, NID or card number into the box.
With `BDRAG_REDACT_PII=true` (the default) the service replaces Bangladeshi mobile
numbers, NID numbers (10, 13 or 17 digits), card and passport numbers and email
addresses, in ASCII or Bangla digits, with `[phone]`, `[NID]`, `[card]`, `[passport]`
and `[email]` as the request arrives. The model (often a hosted free API), the cache,
`data/queries.jsonl`, `data/feedback.jsonl` and the answer's permalink only ever see the
placeholder. `pii_redacted_total{kind}` counts them. Section numbers, years and amounts
are not touched; `bdrag redteam` checks both directions on 52 probes in Bangla, English
and romanised Bangla, and runs in CI.

### Shared answers

A shared link (`/a/<id>`) reads the answer from `BDRAG_ANSWERS_DB`
(`data/answers.sqlite3`), so links survive restarts and deploys and work on every replica
that mounts the same file. Answers are deleted after `BDRAG_ANSWER_DAYS` (90) days: they
quote the law as it stood that day, and the page says which day. Shared pages carry
`noindex`, so search engines do not publish what a visitor asked. If the file cannot be
opened the service logs it once and keeps links in memory; `/stats` reports
`shared_answers.durable`. On a Hugging Face Space the disk is wiped on restart unless the
Space has persistent storage; point the variable at `/data/answers.sqlite3` there.

### Retention

The query log and the feedback log also hold visitors' questions. Rows older than
`BDRAG_LOG_DAYS` (90, like shared answers; `0` keeps them) are deleted at startup and every
`BDRAG_HOUSEKEEPING_S` seconds (6 h) by `src/service/retention.py`, which also runs the
shared-answer purge. The privacy page states this period: change both together.

### Backups

```bash
bdrag backup                       # data/ -> data/backups/bdrag-<UTC time>.tar.gz, keeps 14
bdrag backup --verify data/backups/bdrag-20261027T020000Z.tar.gz
bdrag backup --restore data/backups/bdrag-20261027T020000Z.tar.gz --to data --force
```

The database is copied with SQLite's online backup, so it is safe while the service
runs; each archive carries a SHA-256 and row count per file. Run it nightly (cron, or
Windows Task Scheduler with `bdrag backup --out D:\bdrag-backups`) and copy the archive
to another machine or cloud drive. Restore with the service stopped. The index is not
backed up: rebuild it, or keep a copy of `data/index` from the build.

### What people could not get answered

`bdrag gaps --since 2026-10-01 --out results/gaps.md` lists the questions that were
refused, got general guidance only, failed a guardrail or got a thumbs-down, ranked by
distinct visitors, with the topic-table entry each matched. Questions matching no topic
are the first candidates for `rag/topics.py`; `bdrag feedback-to-eval` turns them into
eval drafts. The report holds what people asked; keep it private.

## Container hardening

The image runs as a non-root user. Run it with a read-only root filesystem, no Linux
capabilities and no privilege escalation; only the index, the logs, the model cache and
`/tmp` need to be mounted:

```bash
docker run --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  -v "$PWD/data/index:/app/data/index:ro" \
  -v bdrag-logs:/app/data/logs -e BDRAG_FEEDBACK=/app/data/logs/feedback.jsonl \
  -e BDRAG_ANALYTICS=/app/data/logs/queries.jsonl \
  -e BDRAG_ANSWERS_DB=/app/data/logs/answers.sqlite3 \
  -v bdrag-hf:/app/.cache/huggingface -p 8000:8000 bd-legal-rag
```

`docker-compose.yml` already does this (`read_only: true`, `./data` and the model cache
mounted). CI starts the image this way and fails if the root filesystem is writable.
Each published GitHub release gets the image's SBOM (SPDX and CycloneDX, from syft)
attached by `.github/workflows/release.yml`; CI keeps one per run as an artifact.

## Limits

| Setting | Default | Notes |
|---|---|---|
| `BDRAG_RATE_PER_MIN` | 20 per client | token bucket with a burst of 5; `/search`, `/ask`, `/ask/stream` and `/feedback` |
| `BDRAG_DAILY_LIMIT` | 0 (none) | answers per UTC day across everyone; set it below a free hosted model's quota |
| `BDRAG_MAX_BODY` | 16384 bytes | larger requests get `413` |
| `BDRAG_API_KEYS`, `BDRAG_REQUIRE_API_KEY` | none | per-key quotas |
| `BDRAG_TRUST_PROXY` | false | honour `X-Forwarded-For` only behind your own proxy |

With more than one replica, set `REDIS_URL` so the cache and rate limits are shared;
admission control and the circuit breaker stay per replica, which is right for a model
on the same machine.
