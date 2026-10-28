#!/usr/bin/env python
"""`bdrag start` — the assistant on your own computer, with nothing leaving it.

  bdrag start                       # gemma4:e4b in Ollama, http://127.0.0.1:8000, opens the browser
  bdrag start --model qwen3.5:4b --port 8080 --no-browser

What it fixes, so a laptop setup cannot drift into sending questions elsewhere:

  - answers come from Ollama on 127.0.0.1 (RAG_LLM=ollama, OLLAMA_HOST=127.0.0.1);
  - settings that would send something off the machine are dropped for this run:
    BDRAG_MODELS, RAG_LLM_BASE_URL, REDIS_URL, BDRAG_OTEL_ENDPOINT, BDRAG_VERIFY_LIVE;
  - the service listens on 127.0.0.1 only, so other computers on the network
    (a café's Wi-Fi, say) cannot reach it;
  - once the embedding model is downloaded, HF_HUB_OFFLINE=1 stops even the
    update check to Hugging Face (`--online` keeps it).

Before serving it runs the `bdrag doctor` checks that matter (index, answering
model, privacy) and stops with the fix if one fails. If Ollama is installed but
not running, it starts `ollama serve`.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Mapping
from pathlib import Path

from rag import doctor

LOCAL_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma4:e4b"
# Each of these can send a question, or something about it, to another machine.
OUTSIDE_SETTINGS = ("BDRAG_MODELS", "RAG_LLM_BASE_URL", "REDIS_URL", "BDRAG_OTEL_ENDPOINT",
                    "BDRAG_VERIFY_LIVE")


def private_env(env: Mapping[str, str], model: str, offline: bool) -> dict[str, str]:
    """The environment for a run where no question leaves this computer."""
    out = {k: v for k, v in env.items() if k not in OUTSIDE_SETTINGS}
    out.update({"RAG_LLM": "ollama", "RAG_MODEL": model, "OLLAMA_HOST": LOCAL_OLLAMA,
                "PYTHONUTF8": "1"})
    out.setdefault("OLLAMA_KEEP_ALIVE", "30m")      # keep the model loaded between questions
    # A laptop CPU reads a prompt at tens of tokens a second, so every extra model
    # call and every excerpt character is seconds the visitor waits. Each of these
    # can still be set in the environment to override it.
    out.setdefault("RAG_LLM_TIMEOUT", "300")        # reading 5 Bangla excerpts can pass 120 s
    out.setdefault("RAG_EXCERPT_CHARS", "1000")
    out.setdefault("BDRAG_AGENT_AUTO", "false")     # the agent makes up to 5 model calls
    out.setdefault("BDRAG_REWRITE", "none")         # two extra calls when it fires
    if offline:
        out.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
    return out


def _ollama_up(timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_OLLAMA}/api/version", timeout=timeout):
            return True
    except OSError:
        return False


def ensure_ollama(wait_s: float = 30) -> bool:
    """Ollama answering on 127.0.0.1; starts `ollama serve` when installed but not running."""
    if _ollama_up():
        return True
    exe = shutil.which("ollama") or next(
        (p for p in (Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",)
         if p.is_file()), None)
    if not exe:
        return False
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen([str(exe), "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}, creationflags=flags)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _ollama_up():
            return True
        time.sleep(1)
    return False


def _embedder_of(index_dir: str) -> str:
    try:
        return json.loads((Path(index_dir) / "index.json").read_text(encoding="utf-8")).get("embedder") or ""
    except (OSError, ValueError):
        return ""


def open_when_ready(url: str, timeout_s: float = 600) -> None:
    """Open the browser once the index and models are loaded, not on a page that hangs."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/readyz", timeout=5):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag start", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("RAG_MODEL") or DEFAULT_MODEL,
                    help=f"Ollama model that writes the answers (default {DEFAULT_MODEL})")
    ap.add_argument("--index", default=os.environ.get("BDRAG_INDEX", "data/index"))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--online", action="store_true",
                    help="let the embedding library check Hugging Face for model updates")
    args = ap.parse_args(argv)

    embedder = _embedder_of(args.index) or "BAAI/bge-m3"
    cached = embedder.startswith("hashing") or doctor.check_model_cache(embedder).status == doctor.OK
    env = private_env(os.environ, args.model, offline=cached and not args.online)
    env["BDRAG_INDEX"] = args.index
    os.environ.clear()
    os.environ.update(env)
    if hasattr(sys.stdout, "reconfigure"):           # a Windows console without UTF-8
        sys.stdout.reconfigure(errors="replace")
    if not ensure_ollama():
        print("❌ Ollama is not running on this computer  ->  install it from https://ollama.com "
              "(or `winget install Ollama.Ollama`) and run this again")
        return 1
    checks = [doctor.check_index(args.index), *doctor.check_llm(), doctor.check_privacy()]
    for c in checks:
        print(c.line())
    if any(c.status == doctor.FAIL for c in checks):
        print("\nFix the line marked ❌ and run `bdrag start` again.")
        return 1
    url = f"http://127.0.0.1:{args.port}"
    print(f"\nStarting on {url} (this computer only). Loading the index and models takes a minute;"
          "\nthe browser opens when it is ready. Close this window to stop.\n")
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    import uvicorn  # the serve extra: pip install -e ".[serve,embed]"

    uvicorn.run("service.app:get_app", factory=True, host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
