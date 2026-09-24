# ADR 0006 — Starlette for the service, and blocking work in a threadpool

**Status:** accepted · **Date:** 2026-09

## Context
The service needs JSON endpoints, SSE streaming and static files. FastAPI is the
default choice and brings pydantic and generated docs. The retrieval and model
calls in this codebase are synchronous and CPU- or network-bound.

## Decision
Build on Starlette (which FastAPI itself is built on) and run every blocking
call through `run_in_threadpool`. Components are injected into `create_app`, so
the whole service is testable with a fake model and a four-document corpus.

## Consequences
- One dependency, no code generation, and the event loop is never blocked.
- No automatic OpenAPI docs or request validation models; validation is explicit.
- Porting to FastAPI later is mechanical: the handlers and payloads map one to one.
