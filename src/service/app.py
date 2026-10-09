"""HTTP service around the pipeline.

Built on Starlette (the ASGI toolkit FastAPI is built on) so the service has one
small dependency and nothing generated between you and the request. Porting to
FastAPI is mechanical: the payloads below map one-to-one onto pydantic models.

Endpoints
  GET  /                health-checked UI
  GET  /health          liveness + what is loaded
  GET  /stats           config, cache, cost projection
  GET  /metrics         Prometheus text
  POST /search          retrieval only — no model call, free and fast
  POST /ask             grounded answer with citations and guardrail report
  POST /ask/stream      the same, streamed as server-sent events
  POST /feedback        thumbs up/down + comment, appended to a JSONL file
  GET  /a/{id}          permalink to a previously produced answer

Three things here that are easy to get wrong and expensive to get wrong:

1. **Blocking work runs in a thread**, never on the event loop. Embedding,
   reranking and HTTP calls to a model provider are synchronous; awaiting them
   directly would serialise every concurrent request.
2. **The cache key includes the index fingerprint**, so rebuilding the index
   invalidates every cached answer instead of serving yesterday's pipeline.
3. **The model failing degrades to retrieval results**, with a notice, rather
   than a blank error page.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from rag.agent import AgentConfig, LegalAgent
from rag.answer import answer_question, answer_question_stream
from rag.guardrails import GuardConfig
from rag.llm import LLMError
from rag.pipeline import RetrievalConfig, index_fingerprint
from service.backends import make_cache, make_limiter
from service.cache import cache_key
from service.cost import estimate_cost, project_monthly
from service.metrics import Metrics
from service.tracing import Trace

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("service")

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy":
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip()
    return raw.lower() in ("1", "true", "yes", "on") if raw else default


def _env_float(name: str, default: float | None = None) -> float | None:
    """Empty and unset mean the same thing: `BDRAG_MIN_SCORE=` in a .env file
    must not crash startup with float('')."""
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


@dataclass
class ServiceConfig:
    index: str = "data/index"
    chunks: str = "data/processed/chunks.jsonl"
    embedder: str = "auto"           # auto = whatever the index was built with (index.json)
    model: str = "BAAI/bge-m3"
    # The configuration scripts/finish.py selects on the tuning split (results/selected.json):
    # dense bge-m3 beat both fusion settings there, and on the test set BM25 fusion cost recall.
    retrieval: RetrievalConfig = field(default_factory=lambda: RetrievalConfig(
        mode="dense", expand_refs=True, synonyms=True, transliterate=True, route=False,
        boost_in_force=True, resolve_refs=True, max_parts_per_section=2))
    k: int = 5
    max_k: int = 20
    min_score: float | None = None
    agent_enabled: bool = True
    agent_auto: bool = True              # route multi-hop questions to the agent
    max_steps: int = 5
    provider: str | None = None
    llm_model: str = ""
    cache_ttl_s: float = 1800
    cache_size: int = 512
    rate_per_min: float = 20
    burst: int = 5
    api_keys: dict[str, float] = field(default_factory=dict)   # key -> requests/min
    require_api_key: bool = False
    entailer: str = "none"           # none | lexical | nli
    # Empty = don't write. Only from_env() turns logging on, so a ServiceConfig
    # built in a test never appends to the real data/queries.jsonl.
    feedback_path: str = ""
    analytics_path: str = ""
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    trust_proxy: bool = False
    verify_live: bool = False        # re-check cited sections against bdlaws (rag/verify.py)
    preload: bool = False            # load index and models at startup (from_env turns it on)
    cache_dir: str = "data/raw"        # honour X-Forwarded-For (only behind your own proxy)

    @classmethod
    def from_env(cls) -> ServiceConfig:
        retrieval = RetrievalConfig(
            mode=_env_str("BDRAG_MODE", "dense"),
            rerank=_env_str("BDRAG_RERANK", "none"),
            expand_refs=_env_bool("BDRAG_EXPAND_REFS", True),
            synonyms=_env_bool("BDRAG_SYNONYMS", True),
            transliterate=_env_bool("BDRAG_TRANSLITERATE", True),
            route=_env_bool("BDRAG_ROUTE", False),
            boost_in_force=_env_bool("BDRAG_BOOST_IN_FORCE", True),
            resolve_refs=_env_bool("BDRAG_RESOLVE_REFS", True),
            parent_context=_env_bool("BDRAG_PARENT_CONTEXT", False),
            mmr_lambda=_env_float("BDRAG_MMR"),
            max_parts_per_section=_env_int("BDRAG_MAX_PARTS", 2),
        )
        keys: dict[str, float] = {}
        if raw := os.environ.get("BDRAG_API_KEYS", "").strip():   # "key1:60,key2:20"
            for entry in raw.split(","):
                key, _, rate = entry.partition(":")
                if key.strip():
                    keys[key.strip()] = float(rate or "20")
        return cls(
            index=_env_str("BDRAG_INDEX", "data/index"),
            chunks=_env_str("BDRAG_CHUNKS", "data/processed/chunks.jsonl"),
            embedder=_env_str("BDRAG_EMBEDDER", "auto"),
            model=_env_str("BDRAG_MODEL", "BAAI/bge-m3"),
            retrieval=retrieval,
            k=_env_int("BDRAG_K", 5),
            min_score=_env_float("BDRAG_MIN_SCORE"),
            agent_enabled=_env_bool("BDRAG_AGENT", True),
            agent_auto=_env_bool("BDRAG_AGENT_AUTO", True),
            max_steps=_env_int("BDRAG_MAX_STEPS", 5),
            provider=os.environ.get("RAG_LLM", "").strip() or None,
            llm_model=_env_str("RAG_MODEL", ""),
            cache_ttl_s=_env_float("BDRAG_CACHE_TTL", 1800.0) or 0.0,
            rate_per_min=_env_float("BDRAG_RATE_PER_MIN", 20.0) or 20.0,
            api_keys=keys,
            require_api_key=_env_bool("BDRAG_REQUIRE_API_KEY", False),
            entailer=_env_str("BDRAG_ENTAILER", "none"),
            feedback_path=_env_str("BDRAG_FEEDBACK", "data/feedback.jsonl"),
            analytics_path=_env_str("BDRAG_ANALYTICS", "data/queries.jsonl"),
            cors_origins=[o.strip() for o in _env_str("BDRAG_CORS", "*").split(",") if o.strip()],
            trust_proxy=_env_bool("BDRAG_TRUST_PROXY", False),
            verify_live=_env_bool("BDRAG_VERIFY_LIVE", False),
            preload=_env_bool("BDRAG_PRELOAD", True),
            cache_dir=_env_str("BDRAG_CACHE", "data/raw"),
        )


class RequestContext(BaseHTTPMiddleware):
    """Request id, timing, metrics, security headers, structured logs, JSON 500."""

    def __init__(self, app, metrics: Metrics) -> None:
        super().__init__(app)
        self.metrics = metrics

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        request.state.trace = Trace(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(json.dumps({"request_id": rid, "path": request.url.path,
                                      "event": "unhandled_error"}))
            self.metrics.inc("errors_total", path=request.url.path)
            return JSONResponse({"error": "internal error", "request_id": rid}, status_code=500,
                                headers=SECURITY_HEADERS)
        took = time.perf_counter() - start
        self.metrics.inc("requests_total", path=request.url.path, status=response.status_code)
        self.metrics.observe("request", took, path=request.url.path)
        response.headers.update({"x-request-id": rid, **SECURITY_HEADERS})
        log.info(json.dumps({"request_id": rid, "path": request.url.path,
                             "status": response.status_code, "ms": round(took * 1000)}))
        return response


def _client(request: Request, trust_proxy: bool = False) -> str:
    """Who is asking, for rate limiting. X-Forwarded-For is set by the caller, so
    trusting it lets anyone pick a fresh identity per request and walk past the
    limiter. Only honour it when the service sits behind a proxy you control."""
    fwd = request.headers.get("x-forwarded-for") if trust_proxy else None
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _append_jsonl(path: str, row: dict) -> None:
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:                        # logging must never break a response
        log.warning("could not append to %s", path)


MULTI_HOP_HINTS = ("difference", "compare", "পার্থক্য", "তুলনা", "and also", "এবং কি",
                   "both", "দুটি", "besides")


def wants_agent(question: str) -> bool:
    """Cheap router: only pay for multi-step retrieval when the question needs it."""
    low = question.lower()
    return any(h in low for h in MULTI_HOP_HINTS) or low.count("?") > 1


def create_app(config: ServiceConfig | None = None, pipeline=None, llm=None,
               stream_llm=None, records=None) -> Starlette:
    """Build the app. Components can be injected, which is what the tests do —
    a service you cannot construct without a GPU and an API key is untestable."""
    cfg = config or ServiceConfig.from_env()
    metrics = Metrics()
    answers = make_cache(cfg.cache_ttl_s, cfg.cache_size)
    limiter = make_limiter(cfg.rate_per_min, cfg.burst)
    recent: dict[str, dict] = {}             # permalinks: id -> answer payload
    state: dict = {"pipeline": pipeline, "llm": llm, "stream_llm": stream_llm,
                   "records": records, "agent": None, "ready": pipeline is not None,
                   "fingerprint": index_fingerprint(cfg.index)}

    build_lock = threading.Lock()

    def build() -> None:
        """Load the index and models exactly once. Concurrent first requests wait for
        the one load instead of each loading their own copy of the embedding model
        (four parallel loads of bge-m3 exhaust a laptop's memory)."""
        if state["ready"]:
            return
        with build_lock:
            if state["ready"]:
                return
            _build()

    def _build() -> None:
        from rag.embed import embedder_for
        from rag.llm import get_llm, get_stream_llm
        from rag.pipeline import build_pipeline, load_records

        embedder = embedder_for(cfg.retrieval.mode, cfg.embedder, cfg.model, cfg.index)
        state["records"] = state["records"] or load_records(cfg.index, cfg.chunks)
        state["llm"] = state["llm"] or get_llm(cfg.provider)
        state["stream_llm"] = state["stream_llm"] or get_stream_llm(cfg.provider)
        state["pipeline"] = build_pipeline(cfg.retrieval, cfg.index, embedder,
                                           llm=state["llm"], records=state["records"])
        state["fingerprint"] = index_fingerprint(cfg.index)
        state["ready"] = True

    def guard() -> GuardConfig:
        if "entailer" not in state:
            from rag.entail import get_entailer
            try:
                state["entailer"] = get_entailer(cfg.entailer)
            except Exception:                # a missing NLI model must not stop the service
                log.warning("entailer '%s' unavailable; running without claim checking",
                            cfg.entailer)
                state["entailer"] = None
        return GuardConfig(min_score=cfg.min_score, entailer=state["entailer"])

    def agent() -> LegalAgent:
        if state["agent"] is None:
            state["agent"] = LegalAgent(state["pipeline"], state["records"] or [], state["llm"],
                                        AgentConfig(max_steps=cfg.max_steps, per_call_k=cfg.k,
                                                    guard=guard(), seed=True))
        return state["agent"]

    def remember(answer_id: str, out: dict, ans, client, use_agent: bool) -> None:
        """Permalink store (bounded) + one analytics row per answer, for both
        the plain and the streaming endpoint."""
        recent[answer_id] = out
        while len(recent) > 500:
            recent.pop(next(iter(recent)))
        _append_jsonl(cfg.analytics_path, {
            "ts": time.time(), "id": answer_id, "client": client, "question": ans.question,
            "agent": use_agent, "refused": ans.refused, "failures": ans.failures,
            "sources": [s["chunk_id"] for s in ans.sources], "latency_s": round(ans.latency_s, 2)})

    async def payload(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return body if isinstance(body, dict) else {}

    def clamp_k(value) -> int:
        try:
            return max(1, min(int(value), cfg.max_k))
        except (TypeError, ValueError):
            return cfg.k

    def authorize(request: Request):
        """API key -> its own quota. Without keys the service is open but rate limited."""
        key = request.headers.get("x-api-key") or request.query_params.get("api_key")
        if cfg.api_keys and key in cfg.api_keys:
            return None, f"key:{key[:6]}"
        if cfg.require_api_key:
            return JSONResponse({"error": "missing or unknown API key"}, status_code=401), None
        return None, _client(request, cfg.trust_proxy)

    def limited(client: str):
        decision = limiter.check(client)
        if decision.allowed:
            return None
        metrics.inc("rate_limited_total")
        return JSONResponse({"error": "rate limit exceeded",
                             "retry_after_s": decision.retry_after_s}, status_code=429,
                            headers={"retry-after": str(int(decision.retry_after_s) + 1)})

    def gate(request: Request):
        """Auth + rate limit in one step. Returns (response_or_None, client_id)."""
        denied, client = authorize(request)
        if denied is not None:
            return denied, None
        blocked = limited(client)
        return blocked, client

    async def degraded_retrieval(question: str, k: int):
        hits = await run_in_threadpool(lambda: state["pipeline"].search(question, k=k))
        return JSONResponse({
            "question": question,
            "answer": None,
            "degraded": True,
            "error": "the answering model is not configured; showing retrieved provisions",
            "sources": [{"n": n, "citation": h.citation, "url": h.metadata.get("url"),
                         "text": h.body[:800]} for n, h in enumerate(hits, 1)],
            "disclaimer": "Informational only — not legal advice.",
        }, status_code=503)

    # ----------------------------------------------------------- endpoints
    def llm_reachable() -> bool | None:
        """For a local Ollama, whether it answers at all (None: not checked)."""
        if (cfg.provider or "").lower() != "ollama":
            return None
        import urllib.request

        from rag.llm import ollama_host
        host = ollama_host()
        try:
            with urllib.request.urlopen(f"{host}/api/version", timeout=2):
                return True
        except OSError:
            return False

    async def health(request: Request):
        try:
            await run_in_threadpool(build)
        except Exception as e:
            return JSONResponse({"status": "degraded", "error": str(e)}, status_code=503)
        store = getattr(state["pipeline"].dense, "store", None) if state["pipeline"].dense else None
        return JSONResponse({"status": "ok", "mode": state["pipeline"].config.mode,
                             "chunks": len(store) if store else None,
                             "embedder": getattr(store, "embedder_name", None),
                             "index_fingerprint": state["fingerprint"],
                             "agent_enabled": cfg.agent_enabled,
                             "llm": cfg.provider or "none",
                             "llm_model": cfg.llm_model or None,
                             "llm_reachable": await run_in_threadpool(llm_reachable)})

    async def stats(request: Request):
        await run_in_threadpool(build)
        snap = metrics.snapshot()
        spend = snap["counters"].get("llm_cost_usd_total", 0.0)
        answered = sum(v for k, v in snap["counters"].items() if k.startswith("answers_total"))
        per_query = spend / answered if answered else 0.0
        return JSONResponse({
            "config": {**{k: v for k, v in asdict(cfg).items()
                          if k not in ("cors_origins", "api_keys", "retrieval")},
                       "retrieval": cfg.retrieval.to_dict()},
            "index_fingerprint": state["fingerprint"],
            "cache": answers.stats(),
            "cost": {"total_usd": round(spend, 4), "per_query_usd": round(per_query, 5),
                     "projected_monthly_usd_at_200_per_day": round(project_monthly(per_query), 2)},
            "metrics": snap,
        })

    async def metrics_endpoint(request: Request):
        return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    async def search(request: Request):
        blocked, _ = gate(request)
        if blocked is not None:
            return blocked
        body = await payload(request)
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)
        await run_in_threadpool(build)
        k = clamp_k(body.get("k"))
        trace: Trace = request.state.trace
        with trace.span("retrieve", k=k):
            hits = await run_in_threadpool(
                lambda: state["pipeline"].search(question, k=k, language=body.get("language")))
        metrics.inc("search_total")
        trace.finish(endpoint="search", question_chars=len(question), hits=len(hits))
        return JSONResponse({"question": question, "results": [
            {"n": n, "citation": h.citation, "score": round(h.score, 4),
             "section_title": h.metadata.get("section_title"),
             "act_title": h.metadata.get("act_title"), "url": h.metadata.get("url"),
             "amended": bool(h.metadata.get("amended")), "text": h.body[:1200]}
            for n, h in enumerate(hits, 1)]})

    def serialize(ans, cached: bool = False, answer_id: str | None = None) -> dict:
        return {
            "id": answer_id, "question": ans.question, "answer": ans.text,
            "refused": ans.refused, "abstained": ans.abstained, "repaired": ans.repaired,
            "failures": ans.failures, "sources": ans.sources,
            "confidence": ans.checks.get("confidence"),
            "llm_calls": ans.llm_calls, "cached": cached,
            "latency_s": round(ans.latency_s, 3),
            "trace": ans.checks.get("trace"), "stop_reason": ans.checks.get("stop_reason"),
            "disclaimer": "Informational only — not legal advice.",
        }

    def live_statuses(ans, out: dict) -> None:
        from ingest.fetch import Fetcher
        from rag.verify import verify_cited

        if "fetcher" not in state:
            state["fetcher"] = Fetcher(cache_dir=cfg.cache_dir, delay=0.0, retries=1, timeout=5.0)
        statuses = verify_cited(ans.hits, ans.cited, state["fetcher"])
        for src in out["sources"]:
            if src["n"] in statuses:
                src["live_check"] = statuses[src["n"]]
        if any(v == "changed" for v in statuses.values()):
            metrics.inc("live_check_changed_total")

    async def check_live(ans, out: dict) -> None:
        """Opt-in: confirm the cited text is still what the site publishes."""
        if cfg.verify_live and not ans.refused and ans.cited:
            await run_in_threadpool(live_statuses, ans, out)

    def record_cost(ans) -> None:
        model = cfg.llm_model or (cfg.provider or "")
        prompt_chars = sum(len(h.body) for h in ans.hits) + len(ans.question) + 1500
        metrics.inc("llm_cost_usd_total",
                    estimate_cost(model, prompt_chars * max(ans.llm_calls, 1), len(ans.text)))

    async def ask(request: Request):
        blocked, client = gate(request)
        if blocked is not None:
            return blocked
        body = await payload(request)
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)
        if len(question) > 500:
            return JSONResponse({"error": "question too long (max 500 characters)"}, status_code=400)
        await run_in_threadpool(build)
        trace: Trace = request.state.trace
        k = clamp_k(body.get("k"))
        if getattr(state["llm"], "offline_stub", False):
            return await degraded_retrieval(question, k)
        use_agent = cfg.agent_enabled and (bool(body.get("agent")) or
                                           (cfg.agent_auto and wants_agent(question)))
        key = cache_key(question, k=k, agent=use_agent, language=body.get("language"),
                        fingerprint=state["fingerprint"], retrieval=cfg.retrieval.to_dict(),
                        min_score=cfg.min_score)
        if (hit := answers.get(key)) is not None:
            metrics.inc("cache_hits_total")
            return JSONResponse({**hit, "cached": True})

        def work():
            if use_agent:
                return agent().run(question)
            return answer_question(question, state["pipeline"], state["llm"], k=k,
                                   guard=guard(), language=body.get("language"))

        t0 = time.perf_counter()
        try:
            with trace.span("answer", agent=use_agent, k=k):
                ans = await run_in_threadpool(work)
        except LLMError as e:
            # Graceful degradation: the model is down, retrieval is not. Give the
            # user the provisions we found and say plainly what is missing.
            metrics.inc("degraded_total")
            with trace.span("degraded_retrieval"):
                hits = await run_in_threadpool(lambda: state["pipeline"].search(question, k=k))
            trace.finish(endpoint="ask", degraded=True)
            return JSONResponse({
                "question": question, "answer": None, "degraded": True,
                "error": f"the answering model is unavailable ({e})",
                "sources": [{"n": n, "citation": h.citation, "url": h.metadata.get("url"),
                             "text": h.body[:800]} for n, h in enumerate(hits, 1)],
                "disclaimer": "Informational only — not legal advice.",
            }, status_code=503)

        metrics.observe("answer", time.perf_counter() - t0, agent=str(use_agent))
        metrics.inc("answers_total", agent=str(use_agent),
                    outcome="refused" if ans.refused else "answered")
        if ans.repaired:
            metrics.inc("repairs_total")
        if ans.failures:
            metrics.inc("guardrail_failures_total")
        record_cost(ans)

        answer_id = uuid.uuid4().hex[:10]
        out = serialize(ans, answer_id=answer_id)
        await check_live(ans, out)
        answers.put(key, out)
        remember(answer_id, out, ans, client, use_agent)
        trace.finish(endpoint="ask", refused=ans.refused, agent=use_agent,
                     llm_calls=ans.llm_calls)
        return JSONResponse(out)

    async def ask_stream(request: Request):
        blocked, client = gate(request)
        if blocked is not None:
            return blocked
        body = await payload(request)
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)
        await run_in_threadpool(build)
        k = clamp_k(body.get("k"))
        if getattr(state["stream_llm"], "offline_stub", False):
            return await degraded_retrieval(question, k)

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def events():
            try:
                for item in answer_question_stream(
                        question, state["pipeline"], state["stream_llm"], k=k, guard=guard(),
                        repair_llm=state["llm"], language=body.get("language")):
                    kind = item["type"]
                    if kind == "final":
                        ans = item["answer"]
                        metrics.inc("answers_total", agent="False",
                                    outcome="refused" if ans.refused else "answered")
                        record_cost(ans)
                        answer_id = uuid.uuid4().hex[:10]
                        out = serialize(ans, answer_id=answer_id)
                        if cfg.verify_live and not ans.refused:
                            live_statuses(ans, out)
                        remember(answer_id, out, ans, client, False)
                        yield sse("final", out)
                    else:
                        yield sse(kind, {k2: v for k2, v in item.items() if k2 != "type"})
            except LLMError as e:
                # Same degradation as /ask: the model failed, retrieval did not.
                log.warning("answering model failed during stream: %s", e)
                metrics.inc("degraded_total")
                try:
                    hits = state["pipeline"].search(question, k=k)
                except Exception:
                    hits = []
                yield sse("final", {
                    "question": question, "answer": None, "degraded": True,
                    "error": f"the answering model is unavailable ({e})",
                    "sources": [{"n": n, "citation": h.citation, "url": h.metadata.get("url"),
                                 "text": h.body[:800]} for n, h in enumerate(hits, 1)],
                    "disclaimer": "Informational only — not legal advice."})
            except Exception as e:            # a dropped stream must not hang the client
                log.exception("stream failed")
                yield sse("error", {"error": f"{type(e).__name__}: {e}"})

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"cache-control": "no-cache", "x-accel-buffering": "no"})

    async def feedback(request: Request):
        """Thumbs up/down on an answer. This is tomorrow's evaluation set."""
        body = await payload(request)
        answer_id = (body.get("id") or "").strip()
        rating = body.get("rating")
        if rating not in ("up", "down"):
            return JSONResponse({"error": "rating must be 'up' or 'down'"}, status_code=400)
        stored = recent.get(answer_id, {})
        _append_jsonl(cfg.feedback_path, {
            "ts": time.time(), "id": answer_id, "rating": rating,
            "comment": (body.get("comment") or "")[:1000],
            "question": stored.get("question"), "answer": stored.get("answer"),
            "sources": [s.get("chunk_id") for s in stored.get("sources", [])],
            "failures": stored.get("failures"),
        })
        metrics.inc("feedback_total", rating=rating)
        return JSONResponse({"ok": True})

    async def permalink(request: Request):
        stored = recent.get(request.path_params["answer_id"])
        if not stored:
            return JSONResponse({"error": "not found or expired"}, status_code=404)
        return JSONResponse(stored)

    async def index_page(request: Request):
        return FileResponse(STATIC / "index.html")

    routes: list[Route | Mount] = [
        Route("/", index_page),
        Route("/health", health),
        Route("/stats", stats),
        Route("/metrics", metrics_endpoint),
        Route("/search", search, methods=["POST"]),
        Route("/ask", ask, methods=["POST"]),
        Route("/ask/stream", ask_stream, methods=["POST"]),
        Route("/feedback", feedback, methods=["POST"]),
        Route("/a/{answer_id}", permalink),
    ]
    if STATIC.exists():
        routes.append(Mount("/static", StaticFiles(directory=str(STATIC)), name="static"))

    middleware = [
        Middleware(RequestContext, metrics=metrics),
        Middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["*"],
                   allow_headers=["*"]),
    ]
    def preload() -> None:
        """Warm the index and model in the background at startup, so the first
        question is not the one that pays for loading them."""
        try:
            build()
            log.info("index and models loaded")
        except Exception:
            log.exception("preload failed; the first request will retry")

    @asynccontextmanager
    async def lifespan(_app):
        if cfg.preload and not state["ready"]:
            threading.Thread(target=preload, daemon=True).start()
        yield

    app = Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
    app.state.config, app.state.metrics, app.state.cache = cfg, metrics, answers
    app.state.components, app.state.recent = state, recent
    app.state.build = build
    return app


app = None  # built on demand by `uvicorn service.app:get_app --factory`


def get_app() -> Starlette:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
