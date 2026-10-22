"""HTTP service around the pipeline.

Built on Starlette (the ASGI toolkit FastAPI is built on) so the service has one
small dependency and nothing generated between you and the request. Porting to
FastAPI is mechanical: the payloads below map one-to-one onto pydantic models.

Endpoints
  GET  /                health-checked UI
  GET  /health          what is loaded (loads it on first call)
  GET  /livez           liveness probe: the process answers; never loads anything
  GET  /readyz          readiness probe: 200 once the index and models are loaded
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
   than a blank error page. The same happens when too many answers are already
   running (admission control) and while the model's circuit breaker is open
   after repeated failures (service/resilience.py).
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
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
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from rag.agent import AgentConfig, LegalAgent
from rag.answer import answer_question, answer_question_stream
from rag.guardrails import GuardConfig
from rag.llm import LLMError
from rag.pii import redact
from rag.pipeline import RetrievalConfig, index_fingerprint
from rag.topics import match_topics
from service.answers import AnswerStore
from service.backends import make_cache, make_limiter
from service.cache import cache_key
from service.cost import estimate_cost, project_monthly
from service.logs import request_id as request_id_var
from service.logs import safe_request_id
from service.metrics import Metrics
from service.resilience import Admission, Busy, CircuitBreaker, SingleFlight
from service.semcache import Probe, SemanticCache, evidence, resolve_threshold, signature
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


def security_headers(frame_ancestors: str = "") -> dict[str, str]:
    """The headers every response carries. A Hugging Face Space shows the app inside
    an iframe on huggingface.co, so a deployment can name the sites allowed to frame
    it (BDRAG_FRAME_ANCESTORS="https://huggingface.co"); by default nobody may."""
    if not frame_ancestors.strip():
        return {**SECURITY_HEADERS,
                "content-security-policy": SECURITY_HEADERS["content-security-policy"]
                + "; frame-ancestors 'none'"}
    headers = {k: v for k, v in SECURITY_HEADERS.items() if k != "x-frame-options"}
    headers["content-security-policy"] += f"; frame-ancestors 'self' {frame_ancestors.strip()}"
    return headers


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
        boost_in_force=True, resolve_refs=True, topics=True, max_parts_per_section=2))
    k: int = 5
    max_k: int = 20
    min_score: float | None = None
    agent_enabled: bool = True
    agent_auto: bool = True              # route multi-hop questions to the agent
    max_steps: int = 5
    provider: str | None = None
    llm_model: str = ""
    # Answering models a visitor may pick in the UI, "provider:model", default first:
    # BDRAG_MODELS="ollama:gemma4:e4b,groq:llama-3.3-70b-versatile". Empty = RAG_LLM only.
    models: list[str] = field(default_factory=list)
    cache_ttl_s: float = 1800
    cache_size: int = 512
    rate_per_min: float = 20
    # Answers per UTC day across all visitors; 0 = no cap. A public demo on a free
    # hosted model key should set this below the provider's daily quota.
    daily_limit: int = 0
    burst: int = 5
    api_keys: dict[str, float] = field(default_factory=dict)   # key -> requests/min
    require_api_key: bool = False
    entailer: str = "none"           # none | lexical | nli
    # When the indexed laws cannot answer, reply with labelled general guidance and
    # the legal-aid note instead of a bare "not found" (rag.answer.general_guidance).
    general_fallback: bool = True
    # Empty = don't write. Only from_env() turns logging on, so a ServiceConfig
    # built in a test never appends to the real data/queries.jsonl.
    feedback_path: str = ""
    analytics_path: str = ""
    # Shared answers (/a/<id>): a SQLite file so links survive restarts and deploys;
    # empty = memory only. Kept this many days, then deleted; 0 = forever.
    answers_path: str = ""
    answer_days: float = 90
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    trust_proxy: bool = False
    verify_live: bool = False        # re-check cited sections against bdlaws (rag/verify.py)
    preload: bool = False            # load index and models at startup (from_env turns it on)
    cache_dir: str = "data/raw"        # honour X-Forwarded-For (only behind your own proxy)
    frame_ancestors: str = ""        # sites allowed to embed the UI in an iframe; empty = none
    # Answers the model works on at once, and how many more may wait; beyond that a
    # visitor gets the retrieved provisions at once. A local model on a laptop CPU
    # serves one answer at a time well; 0 = no limit.
    max_inflight: int = 2
    max_queue: int = 8
    # Model failures in a row that open the circuit, and how long it stays open.
    breaker_failures: int = 3
    breaker_cooldown_s: float = 30.0
    max_body_bytes: int = 16_384     # requests larger than this get 413
    metrics_token: str = ""          # set to require "Authorization: Bearer <token>" on /metrics
    # Replace phone, NID, card, passport numbers and emails in questions and feedback
    # before they reach the model, the cache or the logs (rag/pii.py).
    redact_pii: bool = True
    # Serve an earlier answer to a paraphrase (service/semcache.py): "auto" uses the
    # threshold `bdrag semcache` measured for the index's embedder, "off" disables,
    # a number sets the cosine threshold. Overlap: share of top-5 sections in common.
    semantic_cache: str = "auto"
    semantic_overlap: float = 0.6

    @classmethod
    def from_env(cls) -> ServiceConfig:
        retrieval = RetrievalConfig(
            mode=_env_str("BDRAG_MODE", "dense"),
            rerank=_env_str("BDRAG_RERANK", "none"),
            rerank_model=_env_str("BDRAG_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            rerank_top=_env_int("BDRAG_RERANK_TOP", 20),
            rerank_precision=_env_str("BDRAG_RERANK_PRECISION", "auto"),
            rewrite=_env_str("BDRAG_REWRITE", "colloquial"),
            translate=_env_bool("BDRAG_TRANSLATE", True),
            expand_refs=_env_bool("BDRAG_EXPAND_REFS", True),
            synonyms=_env_bool("BDRAG_SYNONYMS", True),
            transliterate=_env_bool("BDRAG_TRANSLITERATE", True),
            route=_env_bool("BDRAG_ROUTE", False),
            boost_in_force=_env_bool("BDRAG_BOOST_IN_FORCE", True),
            resolve_refs=_env_bool("BDRAG_RESOLVE_REFS", True),
            topics=_env_bool("BDRAG_TOPICS", True),
            topic_slots=_env_int("BDRAG_TOPIC_SLOTS", 3),
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
            models=[m.strip() for m in _env_str("BDRAG_MODELS", "").split(",") if m.strip()],
            cache_ttl_s=_env_float("BDRAG_CACHE_TTL", 1800.0) or 0.0,
            rate_per_min=_env_float("BDRAG_RATE_PER_MIN", 20.0) or 20.0,
            daily_limit=_env_int("BDRAG_DAILY_LIMIT", 0),
            burst=_env_int("BDRAG_BURST", 5),
            api_keys=keys,
            require_api_key=_env_bool("BDRAG_REQUIRE_API_KEY", False),
            entailer=_env_str("BDRAG_ENTAILER", "none"),
            general_fallback=_env_bool("BDRAG_GENERAL_FALLBACK", True),
            feedback_path=_env_str("BDRAG_FEEDBACK", "data/feedback.jsonl"),
            analytics_path=_env_str("BDRAG_ANALYTICS", "data/queries.jsonl"),
            answers_path=_env_str("BDRAG_ANSWERS_DB", "data/answers.sqlite3"),
            answer_days=_env_float("BDRAG_ANSWER_DAYS", 90.0) or 0.0,
            cors_origins=[o.strip() for o in _env_str("BDRAG_CORS", "*").split(",") if o.strip()],
            trust_proxy=_env_bool("BDRAG_TRUST_PROXY", False),
            verify_live=_env_bool("BDRAG_VERIFY_LIVE", False),
            preload=_env_bool("BDRAG_PRELOAD", True),
            cache_dir=_env_str("BDRAG_CACHE", "data/raw"),
            frame_ancestors=_env_str("BDRAG_FRAME_ANCESTORS", ""),
            max_inflight=_env_int("BDRAG_MAX_INFLIGHT", 2),
            max_queue=_env_int("BDRAG_MAX_QUEUE", 8),
            breaker_failures=_env_int("BDRAG_BREAKER_FAILURES", 3),
            breaker_cooldown_s=_env_float("BDRAG_BREAKER_COOLDOWN", 30.0) or 30.0,
            max_body_bytes=_env_int("BDRAG_MAX_BODY", 16_384),
            metrics_token=_env_str("BDRAG_METRICS_TOKEN", ""),
            redact_pii=_env_bool("BDRAG_REDACT_PII", True),
            semantic_cache=_env_str("BDRAG_SEMANTIC_CACHE", "auto"),
            semantic_overlap=_env_float("BDRAG_SEMANTIC_OVERLAP", 0.6) or 0.0,
        )


def _clip(text: object, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def share_page(stored: dict | None) -> str:
    """index.html with a shared answer's question as the title and its opening as the
    link-preview description. Shared answers are marked noindex: they hold what a
    visitor asked, which is theirs to pass on, not a search engine's to publish."""
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    robots = '<meta name="robots" content="noindex">\n'
    if not stored:
        return page.replace("</head>", robots + "</head>", 1)
    title = html.escape(_clip(stored.get("question"), 90) + " · Bangladesh Law Assistant",
                        quote=True)
    desc = html.escape(_clip(re.sub(r"\[\d+\]|[*#_`>]", "", stored.get("answer") or "")
                             or "Cited answer about Bangladeshi law.", 200), quote=True)
    # Functions, not replacement strings: a backslash in a question is not a group.
    page = re.sub(r"<title>.*?</title>", lambda _: f"<title>{title}</title>", page,
                  count=1, flags=re.S)
    def fill(attr: str, value: str) -> None:
        nonlocal page
        page = re.sub(rf'(<meta {attr} content=")[^"]*', lambda m: m.group(1) + value, page,
                      count=1)

    fill('property="og:title"', title)
    fill('property="og:description"', desc)
    fill('name="description"', desc)
    return page.replace("</head>", robots + "</head>", 1)


def route_label(request: Request) -> str:
    """The matched route's template ("/a/{answer_id}"), not the raw path: metrics
    labelled by raw path grow a new series for every permalink and every scanner
    probing /wp-login.php, until the scrape is too big to store."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class RequestContext(BaseHTTPMiddleware):
    """Request id, body limit, timing, metrics, security headers, structured logs, JSON 500."""

    def __init__(self, app, metrics: Metrics, headers: dict[str, str] | None = None,
                 max_body_bytes: int = 0) -> None:
        super().__init__(app)
        self.metrics = metrics
        self.headers = headers or security_headers()
        self.max_body_bytes = max_body_bytes

    def too_large(self, request: Request) -> bool:
        if not self.max_body_bytes:
            return False
        try:
            return int(request.headers.get("content-length") or 0) > self.max_body_bytes
        except ValueError:
            return True

    async def dispatch(self, request: Request, call_next):
        # A caller's id is kept only if it is safe to echo into headers and logs.
        rid = safe_request_id(request.headers.get("x-request-id")) or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        request.state.trace = Trace(rid)
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            if self.too_large(request):
                response = JSONResponse({"error": "request body too large",
                                         "max_bytes": self.max_body_bytes}, status_code=413)
            else:
                response = await call_next(request)
        except Exception:
            log.exception(json.dumps({"request_id": rid, "path": request.url.path,
                                      "event": "unhandled_error"}))
            self.metrics.inc("errors_total", path=route_label(request))
            return JSONResponse({"error": "internal error", "request_id": rid}, status_code=500,
                                headers={"x-request-id": rid, **self.headers})
        finally:
            request_id_var.reset(token)
        took = time.perf_counter() - start
        path = route_label(request)
        self.metrics.inc("requests_total", path=path, status=response.status_code)
        self.metrics.observe("request", took, path=path)
        response.headers.update({"x-request-id": rid, **self.headers})
        log.info(json.dumps({"request_id": rid, "method": request.method,
                             "path": request.url.path, "route": path,
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
    """Cheap router: only pay for multi-step retrieval when the question needs it.

    A personal situation ("my landlord locked me out, what can I do?") usually needs
    several provisions at once (the right, the penalty, where to complain), which
    is what the agent's multiple searches are for."""
    from rag.scope import classify_request

    low = question.lower()
    return (any(h in low for h in MULTI_HOP_HINTS) or low.count("?") > 1
            or classify_request(question)["advice"])


LOCAL_PROVIDERS = ("ollama", "compat", "echo")


def split_model(spec: str) -> tuple[str, str]:
    """"groq:openai/gpt-oss-120b" -> ("groq", "openai/gpt-oss-120b"); the model may hold ':'."""
    provider, _, model = spec.partition(":")
    return provider.strip().lower(), model.strip()


def model_options(cfg: ServiceConfig) -> list[dict]:
    """What the UI's model picker offers. Hosted entries without a key are left out."""
    from rag.llm import COMPAT_HOSTS, compat_settings

    specs = cfg.models or [f"{cfg.provider or 'echo'}:{cfg.llm_model}"]
    out = []
    for spec in specs:
        provider, model = split_model(spec)
        if provider in COMPAT_HOSTS and provider != "compat":
            try:
                compat_settings(provider, model or None)
            except ValueError:                   # no key for this host: don't offer it
                continue
        local = provider in LOCAL_PROVIDERS
        out.append({"id": spec, "provider": provider, "model": model or None, "local": local,
                    "label": f"{model or provider} ({'on this machine' if local else provider})"})
    return out


def create_app(config: ServiceConfig | None = None, pipeline=None, llm=None,
               stream_llm=None, records=None) -> Starlette:
    """Build the app. Components can be injected, which is what the tests do —
    a service you cannot construct without a GPU and an API key is untestable."""
    cfg = config or ServiceConfig.from_env()
    resolve_threshold(cfg.semantic_cache, None)      # a bad BDRAG_SEMANTIC_CACHE fails at start
    metrics = Metrics()
    answers = make_cache(cfg.cache_ttl_s, cfg.cache_size)
    limiter = make_limiter(cfg.rate_per_min, cfg.burst)
    recent = AnswerStore(cfg.answers_path, cfg.answer_days)     # permalinks: id -> payload
    state: dict = {"pipeline": pipeline, "llm": llm, "stream_llm": stream_llm,
                   "records": records, "agent": None, "ready": pipeline is not None,
                   "fingerprint": index_fingerprint(cfg.index), "load_error": None}
    admission = Admission(cfg.max_inflight, cfg.max_queue)
    breaker = CircuitBreaker(cfg.breaker_failures, cfg.breaker_cooldown_s)
    flights = SingleFlight()

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
            try:
                _build()
            except Exception as e:
                state["load_error"] = f"{type(e).__name__}: {e}"
                raise
            state["load_error"] = None

    def _build() -> None:
        from rag.embed import CachedQueryEmbedder, embedder_for
        from rag.llm import get_llm, get_stream_llm
        from rag.pipeline import build_pipeline, load_records

        embedder = embedder_for(cfg.retrieval.mode, cfg.embedder, cfg.model, cfg.index)
        if embedder is not None:
            embedder = CachedQueryEmbedder(embedder)
        state["records"] = state["records"] or load_records(cfg.index, cfg.chunks)
        provider, model = split_model(cfg.models[0]) if cfg.models else (cfg.provider, "")
        state["llm"] = state["llm"] or get_llm(provider, model or None)
        state["stream_llm"] = state["stream_llm"] or get_stream_llm(provider, model or None)
        state["pipeline"] = build_pipeline(cfg.retrieval, cfg.index, embedder,
                                           llm=state["llm"], records=state["records"])
        state["fingerprint"] = index_fingerprint(cfg.index)
        state["ready"] = True

    def semantic() -> SemanticCache | None:
        """The paraphrase cache, once the pipeline exists; None without a dense
        embedder, without a threshold for it, or with answer caching off."""
        if "semantic" not in state:
            dense = getattr(state["pipeline"], "dense", None)
            threshold = (resolve_threshold(cfg.semantic_cache, dense.embedder.name)
                         if dense is not None and cfg.cache_ttl_s else None)
            state["semantic"] = (SemanticCache(threshold, cfg.semantic_overlap, cfg.cache_size,
                                               cfg.cache_ttl_s) if threshold else None)
        return state["semantic"]

    def probe(question: str, scope: str) -> Probe | None:
        if semantic() is None:
            return None
        pipe = state["pipeline"]
        vector = pipe.dense.embedder.encode_queries([question])[0]
        topics = [t.name for t in match_topics(question)] if pipe.config.topics else []
        hits = pipe.dense.store.search(vector, k=5)
        return Probe(question, vector, signature(question, scope, topics), evidence(hits))

    def semantic_hit(question: str, scope: str):
        """(cached payload, probe): payload is None on a miss; the probe is kept so
        the fresh answer can be added under this question afterwards."""
        try:
            p = probe(question, scope)
        except Exception:                    # the cache must never fail a request
            log.exception("paraphrase cache lookup failed")
            return None, None
        if p is None or (m := state["semantic"].lookup(p)) is None:
            return None, p
        if (hit := answers.get(m.key)) is None:      # the answer itself expired
            return None, p
        metrics.inc("semantic_cache_hits_total")
        return {**hit, "cached": True, "cache_match": {
            "question": m.question, "similarity": round(m.similarity, 3)}}, p

    def remember_paraphrase(p: Probe | None, key: str, ans) -> None:
        # A refusal is cheap to recompute and depends on exact wording; keep only answers.
        if p is not None and not ans.refused and not ans.general:
            state["semantic"].add(key, p)

    def guard() -> GuardConfig:
        if "entailer" not in state:
            from rag.entail import get_entailer
            try:
                state["entailer"] = get_entailer(cfg.entailer)
            except Exception:                # a missing NLI model must not stop the service
                log.warning("entailer '%s' unavailable; running without claim checking",
                            cfg.entailer)
                state["entailer"] = None
        return GuardConfig(min_score=cfg.min_score, entailer=state["entailer"],
                           general_fallback=cfg.general_fallback)

    def agent() -> LegalAgent:
        if state["agent"] is None:
            state["agent"] = LegalAgent(state["pipeline"], state["records"] or [], state["llm"],
                                        AgentConfig(max_steps=cfg.max_steps, per_call_k=cfg.k,
                                                    guard=guard(), seed=True))
        return state["agent"]

    def remember(answer_id: str, out: dict, ans, client, use_agent: bool) -> None:
        """Permalink store (bounded) + one analytics row per answer, for both
        the plain and the streaming endpoint."""
        recent.put(answer_id, out)
        _append_jsonl(cfg.analytics_path, {
            "ts": time.time(), "id": answer_id, "client": client, "question": ans.question,
            "agent": use_agent, "refused": ans.refused, "failures": ans.failures,
            "sources": [s["chunk_id"] for s in ans.sources], "latency_s": round(ans.latency_s, 2)})

    def pick_model(body: dict):
        """(llm, stream_llm, id) for the model the request asks for; None = unknown model."""
        wanted = (body.get("model") or "").strip()
        default = cfg.models[0] if cfg.models else ""
        if not wanted or wanted == default:
            return state["llm"], state["stream_llm"], default
        if wanted not in cfg.models:
            return None
        built = state.setdefault("models", {})
        if wanted not in built:
            from rag.llm import get_llm, get_stream_llm

            provider, model = split_model(wanted)
            built[wanted] = (get_llm(provider, model or None),
                             get_stream_llm(provider, model or None))
        return (*built[wanted], wanted)

    async def models(request: Request):
        options = model_options(cfg)
        return JSONResponse({"models": options,
                             "default": options[0]["id"] if options else None})

    async def payload(request: Request) -> dict:
        try:
            body = await request.json()
        except Exception:
            body = {}
        return body if isinstance(body, dict) else {}

    def read_question(body: dict) -> str:
        """The question as everything downstream sees it: personal identifiers are
        replaced here, before the model, the cache, the logs or the answer store."""
        question = str(body.get("question") or "").strip()
        if cfg.redact_pii:
            question, kinds = redact(question)
            for kind in kinds:
                metrics.inc("pii_redacted_total", kind=kind)
        return question

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

    daily: dict = {"day": "", "n": 0}
    daily_lock = threading.Lock()

    def over_daily_limit() -> JSONResponse | None:
        if not cfg.daily_limit:
            return None
        today = time.strftime("%Y-%m-%d", time.gmtime())
        with daily_lock:
            if daily["day"] != today:
                daily.update(day=today, n=0)
            if daily["n"] >= cfg.daily_limit:
                metrics.inc("daily_limit_total")
                return JSONResponse({"error": "this demo has answered its questions for today; "
                                              "please try again tomorrow"}, status_code=429)
            daily["n"] += 1
        return None

    def degraded_payload(question: str, hits, error: str) -> dict:
        return {
            "question": question,
            "answer": None,
            "degraded": True,
            "error": error,
            "sources": [{"n": n, "citation": h.citation, "url": h.metadata.get("url"),
                         "text": h.body[:800]} for n, h in enumerate(hits, 1)],
            "disclaimer": "Informational only — not legal advice.",
        }

    async def degraded_retrieval(question: str, k: int,
                                 error: str = "the answering model is not configured; "
                                              "showing retrieved provisions",
                                 retry_after_s: float | None = None):
        hits = await run_in_threadpool(lambda: state["pipeline"].search(question, k=k))
        headers = {"retry-after": str(int(retry_after_s) + 1)} if retry_after_s else None
        return JSONResponse(degraded_payload(question, hits, error), status_code=503,
                            headers=headers)

    async def model_unavailable(question: str, k: int, breaker_mode: str | None):
        """None when the model may be called; otherwise the retrieval-only reply for an
        open circuit or a full queue. A refused request hands back any breaker trial."""
        if breaker_mode is None:
            metrics.inc("circuit_open_total")
            return await degraded_retrieval(
                question, k, "the answering model failed several times in a row and is "
                "paused; showing retrieved provisions", breaker.retry_after())
        if admission.full():
            if breaker_mode == "trial":
                breaker.release_trial()
            metrics.inc("shed_total")
            return await degraded_retrieval(
                question, k, "too many questions are being answered right now; showing "
                "retrieved provisions", admission.retry_after_s)
        return None

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

    async def livez(request: Request):
        return JSONResponse({"status": "alive"})

    async def readyz(request: Request):
        """For a load balancer or orchestrator: route traffic here only once loading
        is done. Never starts the load itself (startup preload does that), so a probe
        cannot pile up behind a minute-long model load."""
        if state["ready"]:
            return JSONResponse({"status": "ready", "index_fingerprint": state["fingerprint"],
                                 "circuit": breaker.state})
        body = {"status": "loading"}
        if state["load_error"]:
            body = {"status": "failed", "error": state["load_error"]}
        return JSONResponse(body, status_code=503)

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
            "semantic_cache": sem.stats() if (sem := semantic()) else None,
            "admission": admission.stats(),
            "circuit": {"state": breaker.state, "trips": breaker.trips,
                        "consecutive_failures": breaker.failures},
            "singleflight_shared": flights.shared,
            "shared_answers": {"stored": len(recent), "durable": recent.durable},
            "cost": {"total_usd": round(spend, 4), "per_query_usd": round(per_query, 5),
                     "projected_monthly_usd_at_200_per_day": round(project_monthly(per_query), 2)},
            "metrics": snap,
        })

    async def metrics_endpoint(request: Request):
        if cfg.metrics_token:
            import hmac

            given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(given.encode(), cfg.metrics_token.encode()):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        live = admission.stats()
        metrics.set_gauge("inflight_answers", live["inflight"])
        metrics.set_gauge("queued_answers", live["waiting"])
        metrics.set_gauge("circuit_open", 0 if breaker.state == CircuitBreaker.CLOSED else 1)
        metrics.set_gauge("ready", 1 if state["ready"] else 0)
        return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")

    async def search(request: Request):
        blocked, _ = gate(request)
        if blocked is not None:
            return blocked
        body = await payload(request)
        question = read_question(body)
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
            "id": answer_id, "created": int(time.time()),
            "question": ans.question, "answer": ans.text,
            "refused": ans.refused, "abstained": ans.abstained, "repaired": ans.repaired,
            # Not grounded in the indexed laws: label it and replace any streamed draft.
            "general_guidance": ans.general,
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
        if (capped := over_daily_limit()) is not None:
            return capped
        body = await payload(request)
        question = read_question(body)
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)
        if len(question) > 500:
            return JSONResponse({"error": "question too long (max 500 characters)"}, status_code=400)
        await run_in_threadpool(build)
        trace: Trace = request.state.trace
        k = clamp_k(body.get("k"))
        if (picked := pick_model(body)) is None:
            return JSONResponse({"error": "unknown model; GET /models lists the choices"},
                                status_code=400)
        llm, _, model_id = picked
        if getattr(llm, "offline_stub", False):
            return await degraded_retrieval(question, k)
        use_agent = cfg.agent_enabled and (bool(body.get("agent")) or
                                           (cfg.agent_auto and wants_agent(question)))
        setting = {"k": k, "agent": use_agent, "language": body.get("language"), "model": model_id,
                   "fingerprint": state["fingerprint"], "retrieval": cfg.retrieval.to_dict(),
                   "min_score": cfg.min_score}
        key = cache_key(question, **setting)
        if (hit := answers.get(key)) is not None:
            metrics.inc("cache_hits_total")
            return JSONResponse({**hit, "cached": True})
        similar, para = await run_in_threadpool(semantic_hit, question, cache_key("", **setting))
        if similar is not None:
            return JSONResponse(similar)
        breaker_mode = breaker.allow()
        if (unavailable := await model_unavailable(question, k, breaker_mode)) is not None:
            return unavailable

        def work():
            if use_agent:
                if llm is state["llm"]:
                    return agent().run(question)
                return LegalAgent(state["pipeline"], state["records"] or [], llm,
                                  AgentConfig(max_steps=cfg.max_steps, per_call_k=cfg.k,
                                              guard=guard(), seed=True)).run(question)
            return answer_question(question, state["pipeline"], llm, k=k,
                                   guard=guard(), language=body.get("language"))

        def guarded():
            """One answer per distinct question at a time (single-flight), inside an
            admission slot, with the outcome reported to the circuit breaker."""
            def run():
                with admission.slot():
                    try:
                        result = work()
                    except LLMError:
                        breaker.failure()
                        raise
                breaker.success()
                return result
            try:
                return flights.do(key, run)
            finally:
                if breaker_mode == "trial":
                    breaker.release_trial()

        t0 = time.perf_counter()
        try:
            with trace.span("answer", agent=use_agent, k=k):
                ans, shared = await run_in_threadpool(guarded)
        except Busy as e:
            metrics.inc("shed_total")
            return await degraded_retrieval(
                question, k, "too many questions are being answered right now; showing "
                "retrieved provisions", e.retry_after_s)
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
        if shared:
            metrics.inc("singleflight_shared_total")
        else:
            if ans.repaired:
                metrics.inc("repairs_total")
            if ans.failures:
                metrics.inc("guardrail_failures_total")
            record_cost(ans)

        answer_id = uuid.uuid4().hex[:10]
        out = serialize(ans, answer_id=answer_id)
        await check_live(ans, out)
        answers.put(key, out)
        remember_paraphrase(para, key, ans)
        remember(answer_id, out, ans, client, use_agent)
        trace.finish(endpoint="ask", refused=ans.refused, agent=use_agent,
                     llm_calls=ans.llm_calls)
        return JSONResponse(out)

    async def ask_stream(request: Request):
        blocked, client = gate(request)
        if blocked is not None:
            return blocked
        if (capped := over_daily_limit()) is not None:
            return capped
        body = await payload(request)
        question = read_question(body)
        if not question:
            return JSONResponse({"error": "question is required"}, status_code=400)
        if len(question) > 500:
            return JSONResponse({"error": "question too long (max 500 characters)"}, status_code=400)
        await run_in_threadpool(build)
        k = clamp_k(body.get("k"))
        if (picked := pick_model(body)) is None:
            return JSONResponse({"error": "unknown model; GET /models lists the choices"},
                                status_code=400)
        llm, stream_llm, model_id = picked
        if getattr(stream_llm, "offline_stub", False):
            return await degraded_retrieval(question, k)

        def sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        headers = {"cache-control": "no-cache", "x-accel-buffering": "no"}
        # Same key as a non-agent /ask, so either endpoint can serve the other's answer.
        setting = {"k": k, "agent": False, "language": body.get("language"), "model": model_id,
                   "fingerprint": state["fingerprint"], "retrieval": cfg.retrieval.to_dict(),
                   "min_score": cfg.min_score}
        key = cache_key(question, **setting)
        if (hit := answers.get(key)) is not None:
            metrics.inc("cache_hits_total")
            cached = {**hit, "cached": True}
            return StreamingResponse(iter([sse("final", cached)]),
                                     media_type="text/event-stream", headers=headers)
        similar, para = await run_in_threadpool(semantic_hit, question, cache_key("", **setting))
        if similar is not None:
            return StreamingResponse(iter([sse("final", similar)]),
                                     media_type="text/event-stream", headers=headers)
        breaker_mode = breaker.allow()
        if (unavailable := await model_unavailable(question, k, breaker_mode)) is not None:
            return unavailable

        def degraded_event(error: str) -> str:
            try:
                hits = state["pipeline"].search(question, k=k)
            except Exception:
                hits = []
            return sse("final", degraded_payload(question, hits, error))

        def events():
            t0 = time.perf_counter()
            first_token = True
            try:
                with admission.slot():
                    for item in answer_question_stream(
                            question, state["pipeline"], stream_llm, k=k, guard=guard(),
                            repair_llm=llm, language=body.get("language")):
                        kind = item["type"]
                        if kind == "token" and first_token:
                            first_token = False
                            metrics.observe("ttft", time.perf_counter() - t0)
                        if kind == "final":
                            ans = item["answer"]
                            breaker.success()
                            metrics.observe("answer", time.perf_counter() - t0, agent="False")
                            metrics.inc("answers_total", agent="False",
                                        outcome="refused" if ans.refused else "answered")
                            record_cost(ans)
                            answer_id = uuid.uuid4().hex[:10]
                            out = serialize(ans, answer_id=answer_id)
                            if cfg.verify_live and not ans.refused:
                                live_statuses(ans, out)
                            answers.put(key, out)
                            remember_paraphrase(para, key, ans)
                            remember(answer_id, out, ans, client, False)
                            yield sse("final", out)
                        else:
                            yield sse(kind, {k2: v for k2, v in item.items() if k2 != "type"})
            except Busy:
                # Lost the race for the last queue place after the check above.
                metrics.inc("shed_total")
                yield degraded_event("too many questions are being answered right now; "
                                     "showing retrieved provisions")
            except LLMError as e:
                # Same degradation as /ask: the model failed, retrieval did not.
                log.warning("answering model failed during stream: %s", e)
                breaker.failure()
                metrics.inc("degraded_total")
                yield degraded_event(f"the answering model is unavailable ({e})")
            except Exception as e:            # a dropped stream must not hang the client
                log.exception("stream failed")
                yield sse("error", {"error": f"{type(e).__name__}: {e}"})
            finally:
                if breaker_mode == "trial":
                    breaker.release_trial()

        return StreamingResponse(events(), media_type="text/event-stream", headers=headers)

    async def feedback(request: Request):
        """Thumbs up/down on an answer. This is tomorrow's evaluation set."""
        blocked, _ = gate(request)          # every row is a disk write: rate limit it
        if blocked is not None:
            return blocked
        body = await payload(request)
        answer_id = str(body.get("id") or "").strip()[:32]
        rating = body.get("rating")
        if rating not in ("up", "down"):
            return JSONResponse({"error": "rating must be 'up' or 'down'"}, status_code=400)
        stored = recent.get(answer_id) or {}
        comment = str(body.get("comment") or "")
        if cfg.redact_pii:
            comment = redact(comment)[0]
        _append_jsonl(cfg.feedback_path, {
            "ts": time.time(), "id": answer_id, "rating": rating,
            "comment": comment[:1000],
            "question": stored.get("question"), "answer": stored.get("answer"),
            "sources": [s.get("chunk_id") for s in stored.get("sources", [])],
            "failures": stored.get("failures"),
        })
        metrics.inc("feedback_total", rating=rating)
        return JSONResponse({"ok": True})

    async def permalink(request: Request):
        # A shared link opened in a browser gets the page, which then fetches the
        # stored answer as JSON from this same URL.
        # The page asks with ?format=json: a browser may otherwise answer its fetch
        # from the cached page, whatever Accept header the fetch sends.
        accept = request.headers.get("accept", "")
        vary = {"vary": "accept"}
        stored = recent.get(request.path_params["answer_id"])
        if (request.query_params.get("format") != "json"
                and "text/html" in accept and "application/json" not in accept):
            # The page with this answer's question in the title and the link preview,
            # so a link pasted into Messenger or WhatsApp says what it is about.
            return HTMLResponse(share_page(stored), headers=vary)
        if not stored:
            return JSONResponse({"error": "not found or expired"}, status_code=404, headers=vary)
        return JSONResponse(stored, headers=vary)

    async def index_page(request: Request):
        return FileResponse(STATIC / "index.html")

    routes: list[Route | Mount] = [
        Route("/", index_page),
        Route("/health", health),
        Route("/livez", livez),
        Route("/readyz", readyz),
        Route("/stats", stats),
        Route("/models", models),
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
        Middleware(RequestContext, metrics=metrics, headers=security_headers(cfg.frame_ancestors),
                   max_body_bytes=cfg.max_body_bytes),
        Middleware(CORSMiddleware, allow_origins=cfg.cors_origins, allow_methods=["*"],
                   allow_headers=["*"]),
    ]
    def preload() -> None:
        """Warm the index and model in the background at startup, so the first
        question is not the one that pays for loading them."""
        try:
            build()
            from rag.llm import warm_up

            if warm_up(cfg.provider):
                log.info("answering model loaded")
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
    app.state.admission, app.state.breaker, app.state.flights = admission, breaker, flights
    return app


app = None  # built on demand by `uvicorn service.app:get_app --factory`


def get_app() -> Starlette:
    from service.logs import configure
    from service.tracing import configure_otel

    configure(os.environ.get("LOG_LEVEL", "INFO"), os.environ.get("LOG_FORMAT", "text"))
    if configure_otel():
        log.info("exporting traces to %s", os.environ["BDRAG_OTEL_ENDPOINT"])
    return create_app()
