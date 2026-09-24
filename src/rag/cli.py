"""`bdrag` — one command in front of the scripts.

    bdrag ingest --act-ids 1037          -> scripts/ingest.py
    bdrag index --bm25                   -> scripts/build_index.py
    bdrag ask "ধারা ৩০২ কী বলে?"          -> scripts/ask.py
    bdrag eval / ablate / failures / calibrate / tune / e2e
    bdrag serve [--port 8000]            -> uvicorn service.app:get_app

The scripts stay the source of truth (they run without installing anything);
this wrapper exists so an installed checkout has a single, discoverable entry
point. It needs the repository checkout, because the scripts are not packaged.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

SCRIPTS = {
    "ingest": "ingest.py",
    "index": "build_index.py",
    "ask": "ask.py",
    "eval": "eval_retrieval.py",
    "e2e": "eval_e2e.py",
    "ablate": "ablate.py",
    "failures": "failure_report.py",
    "calibrate": "calibrate_guard.py",
    "tune": "tune.py",
    "sweep": "sweep_chunking.py",
    "template": "make_eval_template.py",
    "loadtest": "loadtest.py",
}


def _scripts_dir() -> Path:
    for base in (Path.cwd(), Path(__file__).resolve().parents[2]):
        if (base / "scripts" / "ingest.py").exists():
            return base / "scripts"
    raise SystemExit("bdrag: run this from the bd-legal-rag checkout (scripts/ not found)")


def usage() -> str:
    names = ", ".join([*SCRIPTS, "serve"])
    return f"usage: bdrag <command> [args]\ncommands: {names}\n`bdrag <command> --help` for details."


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "serve":
        import uvicorn  # optional extra: pip install -e ".[serve]"

        port = int(rest[rest.index("--port") + 1]) if "--port" in rest else 8000
        uvicorn.run("service.app:get_app", factory=True, host="0.0.0.0", port=port)
        return
    if cmd not in SCRIPTS:
        raise SystemExit(f"bdrag: unknown command '{cmd}'\n{usage()}")
    path = _scripts_dir() / SCRIPTS[cmd]
    sys.argv = [str(path), *rest]
    runpy.run_path(str(path), run_name="__main__")


if __name__ == "__main__":
    main()
