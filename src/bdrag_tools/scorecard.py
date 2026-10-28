#!/usr/bin/env python
"""The published accuracy scorecard (evalkit/scorecard.py): add a result, render, check.

  bdrag scorecard add retrieval results/scorecard.json
  bdrag scorecard add answers results/scorecard-e2e.json
  bdrag scorecard add redteam results/redteam.json
  bdrag scorecard add redteam_llm results/redteam-llm.json
  bdrag scorecard add lawyer results/lawyer-review.json --setup "graded by an advocate, ..."
      # each one replaces that block in src/service/static/scorecard.json and re-renders
  bdrag scorecard render     # docs/ACCURACY.md and the README block, from scorecard.json
  bdrag scorecard check      # CI: exits 1 when either is out of date, or the red-team
                             # block no longer matches what `bdrag redteam` gives today

A result file outside the repository is copied to results/published/ (kept in git),
so the per-question rows behind a published number stay where anyone can read them.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from evalkit import scorecard as sc

# At the top, not in check(): the scripts/ shim falls back to src/ only when this
# module's own import fails (scripts/ingest.py otherwise shadows the ingest package).
from evalkit.redteam import load_set, static_failures, summarize


def render(card: dict) -> list[str]:
    """Write the Markdown page and the README block; return the files that changed."""
    changed = []
    for path, text in ((sc.MARKDOWN, sc.markdown(card)),
                       (sc.README, sc.with_readme_block(sc.README.read_text(encoding="utf-8"), card))):
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path.relative_to(sc.ROOT)))
    return changed


def published(path: Path, kind: str) -> str:
    """The result file's path in the repository, copying it to results/published/ if needed."""
    path = path.resolve()
    keep = sc.ROOT / "results" / "published"
    try:
        rel = path.relative_to(sc.ROOT)
    except ValueError:
        rel = None
    # results/*.json is git-ignored; a published number needs its rows in git.
    if rel is None or (rel.parts[0] == "results" and len(rel.parts) == 2):
        keep.mkdir(parents=True, exist_ok=True)
        target = keep / f"{kind}-{date.today().isoformat()}-{path.name}"
        shutil.copyfile(path, target)
        rel = target.relative_to(sc.ROOT)
    return rel.as_posix()


def check(card: dict) -> list[str]:
    problems = []
    if not sc.MARKDOWN.exists() or sc.MARKDOWN.read_text(encoding="utf-8") != sc.markdown(card):
        problems.append("docs/ACCURACY.md is out of date: run `bdrag scorecard render`")
    readme = sc.README.read_text(encoding="utf-8")
    try:
        if sc.with_readme_block(readme, card) != readme:
            problems.append("the README scorecard block is out of date: run `bdrag scorecard render`")
    except ValueError as e:
        problems.append(str(e))
    block = card["blocks"].get("redteam")
    if block:
        items = load_set(sc.ROOT / "data" / "eval" / "redteam.jsonl")
        today = summarize([{"id": it.id, "attack": it.attack, "failures": static_failures(it)}
                           for it in items])
        if (today["passed"], today["n"]) != (block["metrics"]["passed"]["value"],
                                             block["metrics"]["passed"]["n"]):
            problems.append(f"red team gives {today['passed']}/{today['n']} today but the scorecard "
                            f"says {block['metrics']['passed']['value']}/{block['metrics']['passed']['n']}: "
                            "re-run `bdrag redteam --json-out results/redteam.json` and add it")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag scorecard", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--card", default=str(sc.SCORECARD))
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="put a result file's numbers in the scorecard")
    add.add_argument("kind", choices=list(sc.KINDS))
    add.add_argument("result", help="the JSON the matching command wrote")
    add.add_argument("--setup", help="replaces the setup line read from the file, e.g. "
                                     "'answers by gemma4:e4b on a laptop CPU'")
    add.add_argument("--date", help="when it was measured (default: the file's timestamp or today)")
    add.add_argument("--short", help="a few words for the README table, e.g. 'gemma4:e4b, laptop CPU'")
    add.add_argument("--note", help="one sentence shown under the block")
    sub.add_parser("render", help="write docs/ACCURACY.md and the README block")
    sub.add_parser("check", help="exit 1 when the published pages are stale")
    args = ap.parse_args(argv)

    card = sc.load(args.card)
    if args.cmd == "add":
        path = Path(args.result)
        data = json.loads(path.read_text(encoding="utf-8"))
        try:
            block = sc.from_result(args.kind, data, published(path, args.kind), when=args.date)
        except ValueError as e:
            print(f"bdrag scorecard: {e}", file=sys.stderr)
            return 2
        if args.setup:
            block["setup"] = args.setup
        if args.short:
            block["short"] = args.short
        if args.note:
            block["note"] = args.note
        card["blocks"][args.kind] = block
        card["updated"] = date.today().isoformat()
        sc.save(card, args.card)
        print(f"{args.kind}: " + ", ".join(f"{k} {sc._num(k, m)}" for k, m in block["metrics"].items()))
        args.cmd = "render"
    if args.cmd == "render":
        changed = render(card)
        print("wrote " + ", ".join(changed) if changed else "already up to date")
        return 0
    problems = check(card)
    for p in problems:
        print(f"bdrag scorecard: {p}", file=sys.stderr)
    if not problems:
        print("scorecard pages are up to date")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
