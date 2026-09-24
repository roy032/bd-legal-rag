"""Thin LLM wrapper so the rest of the code never imports a vendor SDK.

Pick with RAG_LLM=anthropic|openai|ollama|echo and RAG_MODEL=<model id>.
'echo' is an offline stub used by the tests.
"""
from __future__ import annotations

import os
import random
import time
from collections.abc import Callable, Iterator

LLM = Callable[[str, str], str]           # (system, user_prompt) -> text
StreamLLM = Callable[[str, str], "Iterator[str]"]  # (system, user_prompt) -> text chunks


DEFAULT_TIMEOUT_S = float(os.environ.get("RAG_LLM_TIMEOUT", "60"))
DEFAULT_RETRIES = int(os.environ.get("RAG_LLM_RETRIES", "2"))


class LLMError(RuntimeError):
    """Raised after retries are exhausted, so callers can degrade gracefully."""


def with_retries(fn: LLM, retries: int = DEFAULT_RETRIES, base_delay: float = 0.5) -> LLM:
    """Retry transient provider failures with exponential backoff and jitter.

    Jitter matters: without it, every stalled request in a burst retries at the
    same instant and the provider sees the same spike again.
    """
    def call(system: str, prompt: str) -> str:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return fn(system, prompt)
            except Exception as e:                       # provider SDKs raise their own types
                last = e
                if attempt == retries or not _retryable(e):
                    break
                time.sleep(base_delay * 2 ** attempt * (0.5 + random.random()))
        raise LLMError(f"LLM call failed after {retries + 1} attempt(s): {last}") from last

    return call


def _retryable(e: Exception) -> bool:
    text = f"{type(e).__name__}: {e}".lower()
    return any(s in text for s in ("timeout", "timed out", "rate", "429", "500", "502",
                                   "503", "504", "overloaded", "connection"))


def anthropic_llm(model: str | None = None, max_tokens: int = 1024,
                  timeout_s: float = DEFAULT_TIMEOUT_S) -> LLM:
    import anthropic  # pip install anthropic

    client = anthropic.Anthropic(timeout=timeout_s)  # reads ANTHROPIC_API_KEY
    model = model or os.environ.get("RAG_MODEL", "claude-sonnet-4-5")

    def call(system: str, prompt: str) -> str:
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content
                   if getattr(b, "type", "") == "text")

    return call


def openai_llm(model: str | None = None, max_tokens: int = 1024,
               timeout_s: float = DEFAULT_TIMEOUT_S) -> LLM:
    from openai import OpenAI  # pip install openai

    client = OpenAI(timeout=timeout_s)
    model = model or os.environ.get("RAG_MODEL", "gpt-4o-mini")

    def call(system: str, prompt: str) -> str:
        r = client.chat.completions.create(
            model=model, temperature=0, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return r.choices[0].message.content or ""

    return call


def ollama_llm(model: str | None = None, host: str = "http://localhost:11434",
               timeout_s: float = DEFAULT_TIMEOUT_S) -> LLM:
    import requests

    host = os.environ.get("OLLAMA_HOST", host).rstrip("/")
    model = model or os.environ.get("RAG_MODEL", "qwen2.5:7b")

    def call(system: str, prompt: str) -> str:
        r = requests.post(f"{host}/api/generate", timeout=timeout_s, json={
            "model": model, "system": system, "prompt": prompt,
            "stream": False, "options": {"temperature": 0, "num_predict": 512}})
        r.raise_for_status()
        return r.json().get("response", "")

    return call


def echo_llm() -> LLM:
    def call(system: str, prompt: str) -> str:
        return "[offline stub] no model configured — set RAG_LLM and an API key."
    call.offline_stub = True  # type: ignore[attr-defined]
    return call


def get_llm(provider: str | None = None, model: str | None = None,
            retries: int = DEFAULT_RETRIES) -> LLM:
    provider = (provider or os.environ.get("RAG_LLM", "echo")).lower()
    builders = {
        "anthropic": lambda: anthropic_llm(model),
        "openai": lambda: openai_llm(model),
        "ollama": lambda: ollama_llm(model),
        "echo": echo_llm,
    }
    if provider not in builders:
        raise ValueError(f"unknown provider '{provider}'; available: {', '.join(builders)}")
    base = builders[provider]()
    return base if provider == "echo" else with_retries(base, retries=retries)


# ------------------------------------------------------------------- routing
# Most questions do not need your most expensive model. Routing by a cheap
# signal (question shape + how confident retrieval is) is the easiest real cost
# saving in a RAG system, and it is measurable: run the ablation with routing on
# and off and compare correctness against spend.

def routed_llm(cheap: LLM, strong: LLM, should_escalate: Callable[[str, float | None], bool] | None = None) -> LLM:
    """Send easy questions to the cheap model, hard ones to the strong one."""
    def default_rule(question: str, top_score: float | None) -> bool:
        long_question = len(question.split()) > 25
        comparative = any(w in question.lower() for w in
                          ("difference", "compare", "vs", "পার্থক্য", "তুলনা", "কেন", "why"))
        weak_support = top_score is not None and top_score < 0.35
        return long_question or comparative or weak_support

    rule = should_escalate or default_rule

    def call(system: str, prompt: str) -> str:
        question = prompt.split("Question:")[-1][:400]
        return (strong if rule(question, None) else cheap)(system, prompt)

    return call


# ------------------------------------------------------------------ streaming
# Token streaming is a product decision, not a nicety: a grounded legal answer
# takes several seconds, and a user staring at a blank box assumes it is broken.

def anthropic_stream(model: str | None = None, max_tokens: int = 1024) -> StreamLLM:
    import anthropic

    client = anthropic.Anthropic()
    model = model or os.environ.get("RAG_MODEL", "claude-sonnet-4-5")

    def call(system: str, prompt: str) -> Iterator[str]:
        with client.messages.stream(model=model, max_tokens=max_tokens, system=system,
                                    messages=[{"role": "user", "content": prompt}]) as stream:
            yield from stream.text_stream

    return call


def openai_stream(model: str | None = None, max_tokens: int = 1024) -> StreamLLM:
    from openai import OpenAI

    client = OpenAI()
    model = model or os.environ.get("RAG_MODEL", "gpt-4o-mini")

    def call(system: str, prompt: str) -> Iterator[str]:
        stream = client.chat.completions.create(
            model=model, temperature=0, max_tokens=max_tokens, stream=True,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        for chunk in stream:
            piece = chunk.choices[0].delta.content
            if piece:
                yield piece

    return call


def ollama_stream(model: str | None = None, host: str = "http://localhost:11434") -> StreamLLM:
    import json as _json

    import requests

    host = os.environ.get("OLLAMA_HOST", host).rstrip("/")
    model = model or os.environ.get("RAG_MODEL", "qwen2.5:7b")

    def call(system: str, prompt: str) -> Iterator[str]:
        with requests.post(f"{host}/api/generate", stream=True, timeout=300,
                           json={"model": model, "system": system, "prompt": prompt,
                           "stream": True,
                           "options": {"temperature": 0, "num_predict": 512}}) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                piece = _json.loads(line).get("response")
                if piece:
                    yield piece

    return call


def echo_stream() -> StreamLLM:
    def call(system: str, prompt: str) -> Iterator[str]:
        for word in echo_llm()(system, prompt).split():
            yield word + " "

    call.offline_stub = True  # type: ignore[attr-defined]
    return call


def get_stream_llm(provider: str | None = None, model: str | None = None) -> StreamLLM:
    """Streaming counterpart of get_llm. Falls back to one chunk if a provider
    has no streaming implementation, so callers never need to branch."""
    provider = (provider or os.environ.get("RAG_LLM", "echo")).lower()
    builders = {"anthropic": lambda: anthropic_stream(model), "openai": lambda: openai_stream(model),
                "ollama": lambda: ollama_stream(model), "echo": echo_stream}
    if provider in builders:
        return builders[provider]()
    plain = get_llm(provider, model)
    return lambda system, prompt: iter([plain(system, prompt)])
