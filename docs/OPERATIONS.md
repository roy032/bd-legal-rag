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

Suggested alerts: `circuit_open == 1` for 5 minutes (the model is down);
shed share above 10% for 15 minutes (add capacity or lower traffic); p95 time to first
token above 15 s (the model is no longer warm: check `OLLAMA_KEEP_ALIVE`).

## Logs

`LOG_FORMAT=json` writes one JSON object per line: an access line per request
(`request_id`, `method`, `path`, `route`, `status`, `ms`) and a trace line per answer
with each stage's time. Every line logged while a request runs carries its
`request_id`, which is also returned in the `X-Request-Id` header; send your own
(letters, digits, `._:-`, up to 64 characters) to follow a request across services.

```bash
LOG_FORMAT=json bdrag serve 2>&1 | jq 'select(.status >= 500 or .level == "error")'
```

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
