"""Where a visitor's question can go, worked out from the running configuration.

The page, `/about` and `bdrag doctor` say "your question never leaves this computer"
only when this module finds nothing that would send it elsewhere, so the claim
cannot drift from what the service actually does. An endpoint counts as local only
when its host is a loopback address; "compat" pointed at a remote server, or
OLLAMA_HOST on another machine, is reported as outside like any hosted provider.

Not counted: downloading the embedding and answering models and the law text at
setup. Those requests carry no question; `bdrag-start` (the Windows launcher) also
sets HF_HUB_OFFLINE so the embedding model is not even checked for updates.
"""
from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit

# Hosted providers with no OpenAI-compatible preset in rag.llm.COMPAT_HOSTS.
HOSTED = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}


def host_of(url: str) -> str:
    url = (url or "").strip()
    if "://" not in url:
        url = "http://" + url
    return (urlsplit(url).hostname or "").lower()


def is_loopback(url: str) -> bool:
    """True for localhost, 127.0.0.0/8 and ::1. 0.0.0.0 is how Ollama spells "this machine"."""
    host = host_of(url)
    if host in ("localhost", "0.0.0.0"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def model_endpoint(provider: str, env: Mapping[str, str] | None = None) -> str | None:
    """The URL a provider's requests go to; None for "echo", which calls nothing."""
    from rag.llm import COMPAT_HOSTS, DEFAULT_OLLAMA_HOST

    env = os.environ if env is None else env
    provider = (provider or "echo").lower()
    if provider == "echo":
        return None
    if provider == "ollama":
        return env.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST
    if provider in COMPAT_HOSTS:
        return env.get("RAG_LLM_BASE_URL") or COMPAT_HOSTS[provider][0]
    return "https://" + HOSTED.get(provider, f"{provider} (unknown provider)")


def model_is_local(provider: str, env: Mapping[str, str] | None = None) -> bool:
    url = model_endpoint(provider, env)
    return url is None or is_loopback(url)


def outbound(model_specs: list[str], verify_live: bool = False,
             env: Mapping[str, str] | None = None) -> list[dict]:
    """Every place the running service sends something, and what it sends.

    `carries_question` marks the ones that see what a visitor typed; the others
    send only timings or section numbers.
    """
    env = os.environ if env is None else env
    out: list[dict] = []
    seen: set[str] = set()
    for spec in model_specs:
        provider = spec.partition(":")[0].strip().lower()
        url = model_endpoint(provider, env)
        if url is None or is_loopback(url) or url in seen:
            continue
        seen.add(url)
        out.append({"what": f"answering model ({provider})", "where": host_of(url) or url,
                    "sends": "the question and the matching sections of the law",
                    "carries_question": True})
    redis = (env.get("REDIS_URL") or "").strip()
    if redis and not is_loopback(redis):
        out.append({"what": "shared cache (REDIS_URL)", "where": host_of(redis),
                    "sends": "cached answers, including the question, and rate-limit counters",
                    "carries_question": True})
    otel = (env.get("BDRAG_OTEL_ENDPOINT") or "").strip()
    if otel and not is_loopback(otel):
        out.append({"what": "tracing (BDRAG_OTEL_ENDPOINT)", "where": host_of(otel),
                    "sends": "timings of each stage; no question text",
                    "carries_question": False})
    if verify_live:
        out.append({"what": "live citation check (BDRAG_VERIFY_LIVE)", "where": "bdlaws.minlaw.gov.bd",
                    "sends": "the section pages an answer cites; no question text",
                    "carries_question": False})
    return out


def report(model_specs: list[str], verify_live: bool = False,
           env: Mapping[str, str] | None = None) -> dict:
    """{"private": no outside party sees a question, "outbound": [...]}."""
    sends = outbound(model_specs, verify_live, env)
    return {"private": not any(o["carries_question"] for o in sends), "outbound": sends}
