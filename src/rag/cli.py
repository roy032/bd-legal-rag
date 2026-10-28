"""`bdrag` — one command in front of every tool.

    bdrag ingest --act-ids 1037          -> bdrag_tools.ingest
    bdrag index --bm25                   -> bdrag_tools.build_index
    bdrag ask "ধারা ৩০২ কী বলে?"          -> bdrag_tools.ask
    bdrag eval / ablate / failures / calibrate / tune / e2e / gate / ...
    bdrag serve [--port 8000]            -> uvicorn service.app:get_app
    bdrag start                          -> private laptop mode: local Ollama, 127.0.0.1, browser
    bdrag doctor                         -> checks index, models, LLM, OCR (rag/doctor.py)

The tools are part of the installed package, so this works from any directory;
`python scripts/<name>.py` still works from a checkout without installing.
"""
from __future__ import annotations

import importlib
import sys

COMMANDS = {
    "ingest": "ingest",
    "index": "build_index",
    "ask": "ask",
    "eval": "eval_retrieval",
    "e2e": "eval_e2e",
    "ablate": "ablate",
    "failures": "failure_report",
    "calibrate": "calibrate_guard",
    "calibrate-judge": "calibrate_judge",
    "gate": "ci_eval_gate",
    "compare": "compare_runs",
    "contextualize": "contextualize",
    "power": "power_analysis",
    "tune": "tune",
    "sweep": "sweep_chunking",
    "template": "make_eval_template",
    "loadtest": "loadtest",
    "pdf": "ingest_pdf",
    "sync": "sync_index",
    "coverage": "coverage",
    "feedback-to-eval": "feedback_to_eval",
    "measure-upgrades": "measure_upgrades",
    "topics": "topics",
    "redteam": "redteam",
    "semcache": "semcache",
    "backup": "backup",
    "gaps": "gaps",
    "probe": "probe",
    "review": "review",
    "sources": "sources",
    "scorecard": "scorecard",
    "start": "start",
}
SCRIPTS = COMMANDS          # old name, kept for anything that imported it


def usage() -> str:
    names = ", ".join([*COMMANDS, "serve", "doctor"])
    return f"usage: bdrag <command> [args]\ncommands: {names}\n`bdrag <command> --help` for details."


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(usage())
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "doctor":
        from .doctor import main as doctor

        raise SystemExit(doctor(rest))
    if cmd == "serve":
        import uvicorn  # optional extra: pip install -e ".[serve]"

        port = int(rest[rest.index("--port") + 1]) if "--port" in rest else 8000
        host = rest[rest.index("--host") + 1] if "--host" in rest else "0.0.0.0"
        uvicorn.run("service.app:get_app", factory=True, host=host, port=port)
        return
    if cmd not in COMMANDS:
        raise SystemExit(f"bdrag: unknown command '{cmd}'\n{usage()}")
    module = importlib.import_module(f"bdrag_tools.{COMMANDS[cmd]}")
    sys.argv = [f"bdrag {cmd}", *rest]
    # A tool that returns a status (backup --verify, semcache) must fail the shell too.
    raise SystemExit(module.main())


if __name__ == "__main__":
    main()
