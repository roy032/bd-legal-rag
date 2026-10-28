"""`bdrag doctor` — is this machine ready to answer questions?

Prints one line per check, ✅ / ⚠️ / ❌, with the fix next to each failure, so
"why does ask.py fail?" has a one-command answer instead of a back-and-forth:

    ✅ index: data/index — 43,966 chunks, BAAI/bge-m3 (dim 1024)
    ❌ ollama: model 'gemma4:e4b' not pulled  ->  ollama pull gemma4:e4b

Exit status is 1 when a required check fails. Nothing is downloaded and no
secret is printed; network calls are limited to the local Ollama server.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"
ICON = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}

# Which environment variable holds the key for each hosted provider. Includes the
# free OpenAI-compatible presets, so the check stays right once they are installed.
PROVIDER_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "hf": "HF_TOKEN",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""

    def line(self) -> str:
        tail = f"  ->  {self.fix}" if self.fix and self.status != OK else ""
        return f"{ICON[self.status]} {self.name}: {self.detail}{tail}"


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def check_python() -> Check:
    v = sys.version_info
    ok = v >= (3, 10)
    return Check("python", OK if ok else FAIL, f"{v.major}.{v.minor}.{v.micro}", "install Python 3.10+")


def check_packages(need_embedder: bool = True) -> list[Check]:
    out = []
    core = [m for m in ("numpy", "requests", "bs4") if not _has(m)]
    out.append(Check("core packages", FAIL if core else OK,
                     f"missing {', '.join(core)}" if core else "numpy, requests, bs4",
                     'pip install -e "."'))
    out.append(Check("embedder", OK if _has("sentence_transformers") else (FAIL if need_embedder else WARN),
                     "sentence-transformers" if _has("sentence_transformers")
                     else "sentence-transformers not installed (needed for the bge-m3 index)",
                     'pip install -e ".[embed]"'))
    serve = [m for m in ("starlette", "uvicorn") if not _has(m)]
    out.append(Check("web service", WARN if serve else OK,
                     f"missing {', '.join(serve)} (only for `bdrag serve`)" if serve else "starlette, uvicorn",
                     'pip install -e ".[serve]"'))
    return out


def check_index(index_dir: str | Path) -> Check:
    path = Path(index_dir)
    info_path = path / "index.json"
    if not info_path.exists():
        bm25 = path / "bm25.json"
        if bm25.exists() or (path / "bm25.json.gz").exists():
            return Check("index", WARN, f"{path} has only a BM25 index (no dense vectors)",
                         "python scripts/build_index.py --bm25")
        return Check("index", FAIL, f"no index at {path}",
                     "copy data/index from a machine that built it, or run "
                     "python scripts/build_index.py --bm25")
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return Check("index", FAIL, f"{info_path} unreadable: {e}", "rebuild the index")
    if not (path / "vectors.npy").exists():
        return Check("index", FAIL, f"{path}/vectors.npy missing", "rebuild or re-copy data/index")
    return Check("index", OK, f"{path} — {info.get('count', 0):,} chunks, "
                              f"{info.get('embedder') or '?'} (dim {info.get('dim', '?')})")


# Parliament amends acts every session; past this an index likely quotes repealed text.
INDEX_MAX_AGE_DAYS = 45


def check_index_age(index_dir: str | Path, max_days: float | None = None,
                    now: float | None = None) -> Check | None:
    import time

    from .pipeline import index_built_at

    built = index_built_at(index_dir)
    if built is None:
        return None
    if max_days is None:
        max_days = float(os.environ.get("BDRAG_INDEX_MAX_AGE_DAYS") or INDEX_MAX_AGE_DAYS)
    days = ((now if now is not None else time.time()) - built) / 86400
    stamp = time.strftime("%Y-%m-%d", time.gmtime(built))
    return Check("index age", WARN if days > max_days else OK,
                 f"built {stamp}, {days:.0f} days ago"
                 + (f" (older than {max_days:.0f})" if days > max_days else ""),
                 "re-ingest the acts amended since then: bdrag ingest, then bdrag index --bm25")


def _hf_cache_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("HF_HUB_CACHE"):
        dirs.append(Path(os.environ["HF_HUB_CACHE"]))
    if os.environ.get("HF_HOME"):
        dirs.append(Path(os.environ["HF_HOME"]) / "hub")
    dirs.append(Path.home() / ".cache" / "huggingface" / "hub")
    return dirs


def check_model_cache(model: str) -> Check:
    if "/" not in model:
        return Check("embedding model", OK, f"{model} (local path or built-in)")
    folder = "models--" + model.replace("/", "--")
    for d in _hf_cache_dirs():
        if (d / folder).exists():
            return Check("embedding model", OK, f"{model} cached in {d}")
    return Check("embedding model", WARN, f"{model} not in the Hugging Face cache; "
                 "the first question downloads it (~2.3 GB for bge-m3)",
                 f'python -c "from sentence_transformers import SentenceTransformer as S; S(\'{model}\')"')


def check_llm(env: dict[str, str] | None = None, get=None) -> list[Check]:
    env = dict(os.environ if env is None else env)
    provider = (env.get("RAG_LLM") or "").lower()
    model = env.get("RAG_MODEL", "")
    if not provider or provider == "echo":
        return [Check("answering model", WARN, "RAG_LLM not set: retrieval works, answers do not",
                      "set RAG_LLM=ollama and RAG_MODEL=gemma4:e4b (free, local)")]
    if provider == "ollama":
        return [_check_ollama(env, model or "qwen2.5:7b", get)]
    if provider == "compat":
        base = env.get("RAG_LLM_BASE_URL") or "http://127.0.0.1:8080/v1"
        return [Check("answering model", OK if model else FAIL,
                      f"compat at {base}, model {model or '(unset)'}", "set RAG_MODEL")]
    key = PROVIDER_KEYS.get(provider)
    if key is None:
        return [Check("answering model", FAIL, f"unknown RAG_LLM={provider}",
                      f"use one of: ollama, compat, {', '.join(PROVIDER_KEYS)}")]
    has_key = bool(env.get(key) or env.get("RAG_LLM_API_KEY"))
    return [Check("answering model", OK if has_key else FAIL,
                  f"{provider}, model {model or '(provider default)'}, "
                  f"{key} {'set' if has_key else 'missing'}",
                  f"set {key} (never commit it)")]


def _check_ollama(env: dict[str, str], model: str, get=None) -> Check:
    from .llm import DEFAULT_OLLAMA_HOST

    host = (env.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/").replace("://0.0.0.0", "://127.0.0.1")
    if not host.startswith("http"):
        host = "http://" + host
    if get is None:
        import requests
        get = requests.get
    try:
        r = get(f"{host}/api/tags", timeout=3)
        names = {m.get("name", "") for m in r.json().get("models", [])}
    except Exception as e:
        return Check("answering model", FAIL, f"Ollama not reachable at {host} ({type(e).__name__})",
                     "start Ollama (the desktop app, or `ollama serve`)")
    wanted = {model, f"{model}:latest"}
    if names & wanted:
        return Check("answering model", OK, f"ollama at {host}, {model} pulled")
    return Check("answering model", FAIL, f"ollama at {host} has no model '{model}'",
                 f"ollama pull {model}")


def check_privacy(env: dict[str, str] | None = None) -> Check:
    """Whether a question would leave this machine with the current settings."""
    from service.privacy import report

    env = dict(os.environ if env is None else env)
    specs = [m.strip() for m in env.get("BDRAG_MODELS", "").split(",") if m.strip()]
    specs = specs or [f"{env.get('RAG_LLM') or 'echo'}:{env.get('RAG_MODEL', '')}"]
    verify = env.get("BDRAG_VERIFY_LIVE", "").strip().lower() in ("1", "true", "yes", "on")
    r = report(specs, verify, env)
    if not r["outbound"]:
        return Check("privacy", OK, "questions stay on this machine (no outside service is configured)")
    where = "; ".join(f"{o['where']} gets {o['sends']}" for o in r["outbound"])
    if r["private"]:
        return Check("privacy", OK, f"questions stay on this machine ({where})")
    return Check("privacy", WARN, f"questions leave this machine: {where}",
                 "for a fully local setup use RAG_LLM=ollama with Ollama on 127.0.0.1")


def check_ocr(lang: str = "ben+eng") -> Check:
    if not (_has("pytesseract") and (_has("pymupdf") or _has("fitz"))):
        return Check("pdf / ocr", WARN, "not installed (only for scripts/ingest_pdf.py)",
                     'pip install -e ".[pdf]"')
    exe = shutil.which("tesseract") or next(
        (p for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",) if Path(p).exists()), None)
    if not exe:
        return Check("pdf / ocr", WARN, "PyMuPDF ok, Tesseract binary not found (text-layer PDFs only)",
                     "install Tesseract with the Bengali language pack")
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = exe
        have = set(pytesseract.get_languages(config=""))
    except Exception as e:
        return Check("pdf / ocr", WARN, f"Tesseract at {exe} did not run ({e})", "reinstall Tesseract")
    missing = sorted(set(lang.split("+")) - have)
    if missing:
        return Check("pdf / ocr", WARN, f"Tesseract lacks {missing}",
                     "add the Bengali language data (tesseract-ocr-ben / tick Bengali in the installer)")
    return Check("pdf / ocr", OK, f"Tesseract {lang} at {exe}")


def _index_embedder(index_dir: str | Path) -> str:
    try:
        return json.loads((Path(index_dir) / "index.json").read_text(encoding="utf-8")).get("embedder") or ""
    except (OSError, ValueError):
        return ""


def run(index_dir: str | None = None, model: str | None = None) -> list[Check]:
    index_dir = index_dir or os.environ.get("BDRAG_INDEX", "data/index")
    # The model that matters is the one the index was built with.
    model = model or _index_embedder(index_dir) or os.environ.get("BDRAG_MODEL", "BAAI/bge-m3")
    hashing = model.startswith("hashing")
    checks = [check_python(), *check_packages(need_embedder=not hashing), check_index(index_dir)]
    if (age := check_index_age(index_dir)) is not None:
        checks.append(age)
    if not hashing:
        checks.append(check_model_cache(model))
    return [*checks, *check_llm(), check_privacy(), check_ocr()]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="bdrag doctor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", help="index directory (default: $BDRAG_INDEX or data/index)")
    ap.add_argument("--model", help="embedding model (default: $BDRAG_MODEL or BAAI/bge-m3)")
    args = ap.parse_args(argv)
    checks = run(args.index, args.model)
    # A plain Windows console (cp1252/cp437) cannot print the emoji or a dash:
    # use ASCII marks there and replace anything else it cannot show.
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf" not in enc:
        ICON.update({OK: "[ok]  ", WARN: "[warn]", FAIL: "[FAIL]"})
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    for c in checks:
        print(c.line())
    failed = [c for c in checks if c.status == FAIL]
    print("\nready." if not failed else f"\n{len(failed)} check(s) failed; fix those first.")
    return 1 if failed else 0
