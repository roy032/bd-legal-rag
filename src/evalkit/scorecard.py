"""The published accuracy scorecard: what was measured, on what, and how to re-run it.

One file, src/service/static/scorecard.json, holds the numbers. The service shows it
at /accuracy (and serves the file itself at /static/scorecard.json), `bdrag scorecard
render` writes docs/ACCURACY.md and the block between the scorecard markers in the
README from it, and CI fails when either is stale. A number gets in only through
`bdrag scorecard add <kind> <result file>`, so every published figure is the output of
a command anyone can re-run, with its date, its setup and the file it came from.

Five kinds of evidence, each its own block:

  retrieval   `bdrag eval` result: is the governing section among what is found
  answers     `bdrag e2e` result: refusals, citations, and the judge's grades
  redteam     `bdrag redteam --json-out` with the static layer only (CI runs it)
  redteam_llm the same with a real answering model: what the model actually said
  lawyer      `bdrag review score --json`: a qualified person's grades

A block that has not been measured is published as "not measured yet" with the
command that would fill it, never left out: what is missing is part of the proof.
"""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

# Next to the service's static files, so it ships in the package and the Docker image;
# the two pages it renders are only written from a checkout.
SCORECARD = Path(__file__).resolve().parents[1] / "service" / "static" / "scorecard.json"
ROOT = Path(__file__).resolve().parents[2]
MARKDOWN = ROOT / "docs" / "ACCURACY.md"
README = ROOT / "README.md"
START, END = "<!-- scorecard:start -->", "<!-- scorecard:end -->"
REPO = "https://github.com/roy032/bd-legal-rag/blob/main/"

# The retrieval flags the service runs with (service/app.py), for the commands below.
SERVED = ("--mode dense --synonyms --expand-refs --transliterate --boost-in-force --resolve-refs "
          "--topics --max-parts-per-section 2")

# kind -> heading (en, bn), what it answers, the command that fills it
KINDS = {
    "retrieval": (
        "Finding the right law", "সঠিক আইন খুঁজে পাওয়া",
        "For each question in the evaluation set a person wrote down the section(s) of the Act "
        "that answer it. These numbers say how often the search puts those sections in front of "
        "the answering model.",
        f"bdrag eval {SERVED} -k 10 --label scorecard\n"
        "bdrag scorecard add retrieval results/scorecard.json"),
    "answers": (
        "Answers and citations", "উত্তর ও উদ্ধৃতি",
        "The whole service answering the same questions: whether it declines exactly the "
        "questions the law text cannot answer, and whether every [n] it writes points at a real "
        "excerpt that says what the answer claims.",
        f"bdrag e2e {SERVED} --provider ollama --llm-model gemma4:e4b "
        "--judge-provider ollama --judge-model llama3.1:8b --label scorecard-e2e\n"
        "bdrag scorecard add answers results/scorecard-e2e.json"),
    "redteam": (
        "Attacks: input checks", "আক্রমণ পরীক্ষা: প্রশ্ন যাচাই",
        "Prompt injection, attempts to read the hidden instructions, quoting-tag breakouts and "
        "personal data (phone, NID, card numbers), plus ordinary legal questions that look like "
        "attacks. A harmless question that is wrongly flagged counts as a failure too. CI runs "
        "this on every change.",
        "bdrag redteam --json-out results/redteam.json\n"
        "bdrag scorecard add redteam results/redteam.json"),
    "redteam_llm": (
        "Attacks: what the model said", "আক্রমণ পরীক্ষা: মডেলের উত্তর",
        "The same attacks sent through the real answering model: the answer must not repeat the "
        "hidden instructions, the personal data it was sent, or what the attacker asked it to say.",
        "bdrag redteam --provider ollama --llm-model gemma4:e4b --json-out results/redteam-llm.json\n"
        "bdrag scorecard add redteam_llm results/redteam-llm.json"),
    "lawyer": (
        "A lawyer's grades", "আইনজীবীর মূল্যায়ন",
        "Someone qualified in Bangladeshi law reads a balanced sample of answers and grades each "
        "against a fixed rubric (docs/review/RUBRIC.md): right law, right sections, accurate, "
        "safe to act on, clear. The launch bar is no unsafe answer and at least 85% fully "
        "accurate, over at least 30 answers.",
        f"bdrag e2e {SERVED} --label review --no-judge --provider ollama --llm-model gemma4:e4b\n"
        "bdrag review sheet results/review.answers.json --n 50 --out review/\n"
        "bdrag review score review/grades.csv --out docs/reports/lawyer-review.md "
        "--json results/lawyer-review.json\n"
        "bdrag scorecard add lawyer results/lawyer-review.json --setup \"graded by ...\""),
}

# metric key -> (en label, bn label, what it means, kind of number)
METRICS = {
    "recall@5": ("Right section among the first 5 found", "সঠিক ধারা প্রথম ৫টির মধ্যে",
                 "share of answerable questions with a gold section in the top 5", "rate"),
    "recall@5 bn": ("… for questions in Bangla", "… বাংলায় করা প্রশ্নে", "", "rate"),
    "recall@5 en": ("… for questions in English", "… ইংরেজিতে করা প্রশ্নে", "", "rate"),
    "mrr": ("How high the right section ranks (MRR)", "সঠিক ধারা কত ওপরে আসে (MRR)",
            "1 = always first, 0.5 = on average second", "score"),
    "refusal_correct": ("Declines exactly when it should", "ঠিক যখন উচিত তখনই উত্তর দিতে অস্বীকার",
                        "answers the answerable, declines the unanswerable", "rate"),
    "citation_validity": ("Citations point at a real excerpt", "উদ্ধৃতি সত্যিকারের অংশ নির্দেশ করে",
                          "no [n] that names a section it was not given", "rate"),
    "citation_precision": ("Cited sections that are the right ones", "উদ্ধৃত ধারার মধ্যে সঠিক ধারা",
                           "share of cited sections that are gold sections", "rate"),
    "citation_support": ("Cited excerpt supports the claim", "উদ্ধৃত অংশ দাবিকে সমর্থন করে",
                         "cited excerpt is gold or entails the sentence citing it", "rate"),
    "gold_cited": ("Answer cites a right section", "উত্তরে সঠিক ধারা উদ্ধৃত",
                   "share of answerable questions whose answer cites a gold section", "rate"),
    "correctness": ("Agrees with the reference answer (judge model)",
                    "রেফারেন্স উত্তরের সঙ্গে মেলে (বিচারক মডেল)",
                    "graded by a separate local model; indicative only", "rate"),
    "faithfulness": ("Says only what the excerpts say (judge model)",
                     "শুধু উদ্ধৃত অংশে যা আছে তা-ই বলে (বিচারক মডেল)",
                     "graded by a separate local model; strict and noisy", "rate"),
    "passed": ("Probes passed", "পাস করা পরীক্ষা", "", "count"),
    "accurate": ("Fully accurate", "সম্পূর্ণ নির্ভুল", "graded yes, not partly", "rate"),
    "law": ("Relies on the right law", "সঠিক আইনের ওপর নির্ভর", "", "rate"),
    "sections": ("Cited sections say what it says", "উল্লেখিত ধারা সত্যিই তা-ই বলে", "", "rate"),
    "safe": ("Safe to act on", "অনুসরণ করা নিরাপদ", "", "rate"),
    "clear": ("Clear to a non-lawyer", "সাধারণ মানুষের কাছে সহজবোধ্য", "", "rate"),
}


def load(path: str | Path = SCORECARD) -> dict:
    card = json.loads(Path(path).read_text(encoding="utf-8"))
    for kind in KINDS:
        card.setdefault("blocks", {}).setdefault(kind, None)
    return card


def save(card: dict, path: str | Path = SCORECARD) -> None:
    Path(path).write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _stat(s: dict | None) -> dict | None:
    if not s or not s.get("n"):
        return None
    return {"value": round(s["mean"], 3), "ci95": [round(s["lo"], 3), round(s["hi"], 3)],
            "n": s["n"]}


def _setup(cfg: dict, extra: str | None) -> str:
    parts = []
    model = cfg.get("answer_model") or (cfg.get("answer_llm") if cfg.get("answer_llm") not in
                                        (None, "env") else None)
    if model:
        parts.append(f"answers by {model}")
    if cfg.get("judge_llm") not in (None, "none"):
        parts.append(f"judged by {cfg.get('judge_model') or cfg['judge_llm']}")
    parts.append(f"{cfg.get('mode', 'dense')} retrieval" + (" with the topic table"
                                                          if cfg.get("topics") else ""))
    if cfg.get("rerank") not in (None, "none"):
        parts.append(f"{cfg['rerank']} reranker")
    parts.append(f"k={cfg.get('k', 5)}")
    if extra:
        parts.append(extra)
    return ", ".join(parts)


def from_result(kind: str, data: dict, source: str, setup: str | None = None,
                when: str | None = None) -> dict:
    """One block of the scorecard from a result file of the matching command."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind '{kind}': one of {', '.join(KINDS)}")
    block: dict = {"source": source, "metrics": {}}
    if kind in ("retrieval", "answers"):
        if "overall" not in data:
            raise ValueError(f"{source} is not a `bdrag eval` / `bdrag e2e` result file")
        cfg = data.get("config", {})
        block["date"] = when or data.get("timestamp", "")[:10]
        block["setup"] = _setup(cfg, setup)
        block["questions"] = data.get("dataset", {}).get("n")
        block["eval_set"] = cfg.get("eval", "data/eval/eval.jsonl")
        if kind == "retrieval":
            block["metrics"]["recall@5"] = _stat(data["overall"].get("recall@5"))
            block["metrics"]["mrr"] = _stat(data["overall"].get("mrr"))
            for lang in ("bn", "en"):
                block["metrics"][f"recall@5 {lang}"] = _stat(
                    data.get("by_language", {}).get(lang, {}).get("recall@5"))
        else:
            gen = data.get("generation")
            if not gen:
                raise ValueError(f"{source} has no generation scores: run `bdrag e2e`, not `bdrag eval`")
            for key in ("refusal_correct", "citation_validity", "citation_precision",
                        "citation_support", "gold_cited", "correctness", "faithfulness"):
                block["metrics"][key] = _stat(gen.get(key))
    elif kind in ("redteam", "redteam_llm"):
        summary = data.get("summary")
        if not summary:
            raise ValueError(f"{source} is not a `bdrag redteam --json-out` file")
        answered = [r for r in data.get("results", []) if r.get("answer") is not None]
        if kind == "redteam_llm" and not answered:
            raise ValueError(f"{source} has no model answers: run it with --provider")
        block["date"] = when or date.today().isoformat()
        block["setup"] = setup or ("static checks, no model" if kind == "redteam"
                                   else "answers by the model given to --provider")
        block["questions"] = summary["n"]
        block["metrics"]["passed"] = {"value": summary["passed"], "n": summary["n"]}
        block["by_attack"] = summary["by_attack"]
    else:
        if "checks" not in data:
            raise ValueError(f"{source} is not a `bdrag review score --json` file")
        block["date"] = when or date.today().isoformat()
        block["setup"] = setup or "graded by a reviewer qualified in Bangladeshi law"
        block["questions"] = data["graded"]
        for key in ("accurate", "law", "sections", "safe", "clear"):
            s = data["overall"].get(key) or {}
            block["metrics"][key] = ({"value": s["yes_rate"], "ci95": s["ci95"], "n": s["n"]}
                                     if s.get("n") else None)
        block["unsafe"] = len(data.get("unsafe", []))
        block["checks"] = data["checks"]
        block["launch_bar_met"] = data["launch_bar_met"]
    block["metrics"] = {k: v for k, v in block["metrics"].items() if v is not None}
    return block


def _num(key: str, m: dict) -> str:
    if METRICS.get(key, ("", "", "", "rate"))[3] == "count":
        return f"{m['value']}/{m['n']}"
    if METRICS[key][3] == "rate":
        text = f"{m['value']:.1%}".replace(".0%", "%")
        if m.get("ci95") and m["ci95"][0] != m["ci95"][1]:
            text += f" ({m['ci95'][0]:.0%}–{m['ci95'][1]:.0%})"
        return text
    text = f"{m['value']:.3f}"
    if m.get("ci95"):
        text += f" ({m['ci95'][0]:.2f}–{m['ci95'][1]:.2f})"
    return text


def headline(card: dict) -> list[tuple[str, str, str]]:
    """(label, number, where it was measured) for the README table."""
    rows = []
    picks = [("retrieval", "recall@5"), ("retrieval", "mrr"), ("answers", "refusal_correct"),
             ("answers", "citation_validity"), ("answers", "citation_precision"),
             ("answers", "citation_support"), ("redteam", "passed"), ("redteam_llm", "passed"),
             ("lawyer", "accurate")]
    pending = set()
    for kind, key in picks:
        b = card["blocks"].get(kind)
        label = METRICS[key][0] if key != "passed" else KINDS[kind][0]
        if kind == "lawyer":
            label = "Fully accurate, graded by a lawyer"
        if b and key in b["metrics"]:
            rows.append((label, _num(key, b["metrics"][key]),
                         f"{b['date']}, {b.get('short') or b['setup']}"))
        elif not b and kind not in pending:
            # One row for a block nobody has measured, not one per metric it would hold.
            pending.add(kind)
            rows.append((KINDS[kind][0] if kind != "lawyer" else label, "not measured yet",
                         "[how to measure it](docs/ACCURACY.md)"))
    return rows


def markdown(card: dict) -> str:
    out = ["# How accurate is it?", "",
           "<!-- Written by `bdrag scorecard render` from src/service/static/scorecard.json; "
           "edit that file's notes or add a result with `bdrag scorecard add`, not this page. -->",
           "", card["intro"], "",
           f"Corpus: {card['corpus']}. Scorecard updated {card['updated']}. The same page is "
           "served by the app at `/accuracy`, and the numbers as JSON at `/static/scorecard.json`.",
           ""]
    for kind, (heading, bn, what, cmd) in KINDS.items():
        b = card["blocks"].get(kind)
        out += [f"## {heading} · {bn}", "", what, ""]
        if not b:
            out += ["**Not measured yet.** To measure it:", "", "```", cmd, "```", ""]
            continue
        out += [f"Measured {b['date']} on {b.get('questions', '?')} questions"
                + (f" from `{b['eval_set']}`" if b.get("eval_set") else "")
                + f"; {b['setup']}. Every question's result: [{b['source']}](../{b['source']}).", "",
                "| | | Result (95% interval) |", "|---|---|---|"]
        for key, m in b["metrics"].items():
            en, bnl, note, _ = METRICS[key]
            out.append(f"| {en}{' — ' + note if note else ''} | {bnl} | {_num(key, m)} |")
        if b.get("by_attack"):
            out += ["", "By attack: " + ", ".join(f"{k} {v}" for k, v in b["by_attack"].items()) + "."]
        if kind == "lawyer":
            out += ["", f"Launch bar {'**met**' if b['launch_bar_met'] else '**not met**'}: "
                    + "; ".join(f"{'✓' if ok else '✗'} {name}" for name, ok in b["checks"].items())
                    + f". Answers graded unsafe: {b['unsafe']}."]
        if b.get("note"):
            out += ["", b["note"]]
        out += ["", "Re-run:", "", "```", cmd, "```", ""]
    out += ["## Known weak spots", ""] + [f"- {c}" for c in card["caveats"]] + [""]
    out += ["## How to check these numbers yourself", "", card["reproduce"], ""]
    return "\n".join(out)


def readme_block(card: dict) -> str:
    rows = ["| Measure | Result | Measured |", "|---|---|---|"]
    rows += [f"| {a} | {b} | {c} |" for a, b, c in headline(card)]
    return "\n".join([START, "", *rows, "",
                      "Every number, its 95% interval, the command that produced it and the gaps: "
                      "[docs/ACCURACY.md](docs/ACCURACY.md) (the app shows it at `/accuracy`).",
                      "", END])


def with_readme_block(text: str, card: dict) -> str:
    if START not in text or END not in text:
        raise ValueError(f"README.md has no {START} … {END} block")
    head, rest = text.split(START, 1)
    return head + readme_block(card) + rest.split(END, 1)[1]


def _md_inline(text: str) -> str:
    """The few Markdown marks the notes use (`code`, **bold**), as safe HTML."""
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # [text](../path) in a note is relative to docs/; on the page it goes to GitHub.
    return re.sub(r"\[([^\]]+)\]\((?:\.\./)?([^)\s]+)\)",
                  lambda m: f'<a href="{REPO}{m.group(2)}">{m.group(1)}</a>', text)


def html_page(card: dict) -> str:
    """The /accuracy page: the same content as docs/ACCURACY.md, in the app's style."""
    e = html.escape
    parts = []
    for kind, (heading, bn, what, cmd) in KINDS.items():
        b = card["blocks"].get(kind)
        parts.append(f'<section aria-labelledby="h-{kind}"><h2 id="h-{kind}">{e(heading)} '
                     f'<span lang="bn">· {e(bn)}</span></h2><p>{_md_inline(what)}</p>')
        if not b:
            parts.append('<p class="pending"><strong>Not measured yet</strong> '
                         '<span lang="bn">· এখনও মাপা হয়নি</span></p>'
                         f'<details><summary>How to measure it</summary><pre>{e(cmd)}</pre></details>'
                         "</section>")
            continue
        parts.append(f'<p class="meta">Measured {e(b["date"])} on {e(str(b.get("questions", "?")))} '
                     f'questions; {e(b["setup"])}. <a href="{e(REPO + b["source"])}">Every question\'s '
                     'result</a>.</p><table><thead><tr><th scope="col">Measure</th>'
                     '<th scope="col">Result (95% interval)</th></tr></thead><tbody>')
        for key, m in b["metrics"].items():
            en, bnl, note, _ = METRICS[key]
            parts.append(f'<tr><td>{e(en)}<br><span lang="bn">{e(bnl)}</span>'
                         + (f'<br><small>{e(note)}</small>' if note else "")
                         + f'</td><td class="num">{e(_num(key, m))}</td></tr>')
        parts.append("</tbody></table>")
        if b.get("by_attack"):
            parts.append("<p class=\"meta\">By attack: " + e(", ".join(
                f"{k} {v}" for k, v in b["by_attack"].items())) + ".</p>")
        if kind == "lawyer":
            parts.append(f'<p>Launch bar <strong>{"met" if b["launch_bar_met"] else "not met"}'
                         f'</strong>. Answers graded unsafe: {b["unsafe"]}.</p>')
        if b.get("note"):
            parts.append(f"<p>{_md_inline(b['note'])}</p>")
        parts.append(f'<details><summary>Re-run it</summary><pre>{e(cmd)}</pre></details></section>')
    caveats = "".join(f"<li>{_md_inline(c)}</li>" for c in card["caveats"])
    glance = "".join(
        f'<tr><td>{e(label)}</td><td class="num">{e(num)}</td>'
        f'<td>{e(where) if num != "not measured yet" else "see below"}</td></tr>'
        for label, num, where in headline(card))
    return PAGE.format(intro=_md_inline(card["intro"]), intro_bn=e(card["intro_bn"]),
                       corpus=e(card["corpus"]), updated=e(card["updated"]),
                       blocks="".join(parts), caveats=caveats, glance=glance,
                       reproduce=_md_inline(card["reproduce"]))


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>How accurate is it? · Bangladesh Law Assistant</title>
<meta name="description" content="Measured accuracy of the Bangladesh Law Assistant: retrieval, refusals, citations, attacks and a lawyer's grades, with the commands to re-run every number.">
<meta name="theme-color" content="#0b4f3a">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/static/app.css">
<script>
  try {{
    const t = localStorage.getItem("bdrag-theme"); if (t) document.documentElement.dataset.theme = t;
  }} catch (e) {{}}
</script>
<style>
  .legal {{ max-width: 820px; margin: 0 auto; padding: 32px 16px 64px; line-height: 1.6; }}
  .legal h1 {{ font-size: clamp(24px, 3vw, 32px); margin: 0 0 6px; }}
  .legal h2 {{ font-size: 20px; margin: 36px 0 8px; }}
  .legal .meta, .legal .updated {{ color: var(--muted); font-size: 14px; }}
  .legal nav {{ display: flex; gap: 8px 18px; flex-wrap: wrap; margin: 0 0 8px; font-size: 15px; }}
  .legal table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 15px; }}
  .legal th, .legal td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line);
    vertical-align: top; }}
  .legal td.num {{ white-space: nowrap; font-variant-numeric: tabular-nums; font-weight: 600; }}
  .legal small {{ color: var(--muted); }}
  .legal .pending {{ padding: 10px 12px; border: 1px dashed var(--line); border-radius: 8px; }}
  .legal pre {{ white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; padding: 10px;
    border: 1px solid var(--line); border-radius: 8px; }}
  .legal li {{ margin: 6px 0; }}
  .legal [lang=bn] {{ letter-spacing: 0; }}
</style>
</head>
<body>
<main class="legal">
  <nav aria-label="Page links"><a href="/">← Bangladesh Law Assistant</a> <a href="/privacy">Privacy and terms</a></nav>
  <h1>How accurate is it? <span lang="bn">· এটি কতটা নির্ভুল?</span></h1>
  <p class="updated">Updated {updated} · Corpus: {corpus}</p>
  <p>{intro}</p>
  <p lang="bn">{intro_bn}</p>
  <section aria-labelledby="h-glance"><h2 id="h-glance">At a glance <span lang="bn">· এক নজরে</span></h2>
  <table><thead><tr><th scope="col">Measure</th><th scope="col">Result</th><th scope="col">Measured</th></tr></thead>
  <tbody>{glance}</tbody></table></section>
  {blocks}
  <section aria-labelledby="h-gaps"><h2 id="h-gaps">Known weak spots <span lang="bn">· জানা দুর্বলতা</span></h2>
  <ul>{caveats}</ul></section>
  <section aria-labelledby="h-repro"><h2 id="h-repro">Check it yourself <span lang="bn">· নিজে যাচাই করুন</span></h2>
  <p>{reproduce}</p></section>
</main>
</body>
</html>
"""
