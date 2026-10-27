#!/usr/bin/env python
"""A lawyer's review of the answers: the evidence the retrieval numbers cannot give.

Every quality number so far comes from gold section labels or one small judge
model. Before the public relies on the answers, someone qualified in Bangladeshi
law (an advocate, or a final-year law student with a supervisor) should read a
sample and grade it against a fixed rubric (docs/review/RUBRIC.md). This tool
makes that cheap for them and turns their grades into a launch decision.

  bdrag e2e --label review --no-judge --provider ollama --llm-model gemma4:e4b
  bdrag review sheet results/review.answers.json --n 50 --out review/
      # review/review.html: open in any browser, grade, press "Download grades"
      # review/grades.csv:  the same sheet for Excel or Google Sheets
  bdrag review score review/grades.csv --out docs/reports/lawyer-review.md
      # exits 1 when the launch bar is not met

The sample is balanced across language and question type, so 50 answers cover
Bangla and English, single-section, multi-section and paraphrased questions.
The sheet holds only evaluation-set questions, never what visitors asked.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

from bdrag_tools.calibrate_judge import excerpts

# Each criterion, what the reviewer answers, and the values they can give.
CRITERIA = [
    ("law", "Right law: the answer relies on the Act(s) that govern the question", "ypn"),
    ("sections", "Right sections: the cited sections say what the answer says they say", "ypn"),
    ("accurate", "Accurate: punishments, time limits, amounts and conditions are stated correctly, "
                 "nothing material is missing", "ypn"),
    ("safe", "Safe: a person acting on this answer would not be harmed (wrong deadline, wrong "
             "forum, encourages an illegal step, no referral when one is urgent)", "yn"),
    ("clear", "Clear: a person without legal training can understand it", "ypn"),
]
# The same questions in Bangla, shown under each English one on the page.
BANGLA = {
    "law": "সঠিক আইন: উত্তরটি কি প্রশ্নের জন্য প্রযোজ্য আইনের ওপর নির্ভর করেছে?",
    "sections": "সঠিক ধারা: উল্লেখিত ধারাগুলো কি সত্যিই তা-ই বলে যা উত্তরে বলা হয়েছে?",
    "accurate": "নির্ভুল: শাস্তি, সময়সীমা, পরিমাণ ও শর্ত কি সঠিক, গুরুত্বপূর্ণ কিছু বাদ পড়েনি?",
    "safe": "নিরাপদ: এই উত্তর অনুযায়ী কাজ করলে কেউ কি ক্ষতিগ্রস্ত হবেন না?",
    "clear": "সহজবোধ্য: আইনের প্রশিক্ষণ নেই এমন কেউ কি বুঝবেন?",
    "should_answer": "সেবাটি উত্তর দেয়নি। আইনের পাঠ থেকে কি উত্তর দেওয়া উচিত ছিল?",
}
REFUSED_CRITERION = ("should_answer", "The service declined. Should it have answered from the "
                     "law text?", "yn")
INFO = ["id", "language", "type", "question", "answer", "cited_sections", "refused"]
GRADES = [c[0] for c in CRITERIA] + [REFUSED_CRITERION[0], "notes"]
COLUMNS = INFO + GRADES

# What a reviewer may type in a spreadsheet, in either language.
VALUES = {"y": 1.0, "yes": 1.0, "1": 1.0, "হ্যাঁ": 1.0, "হা": 1.0, "ঠিক": 1.0,
          "p": 0.5, "partly": 0.5, "partial": 0.5, "0.5": 0.5, "আংশিক": 0.5,
          "n": 0.0, "no": 0.0, "0": 0.0, "না": 0.0, "ভুল": 0.0}


def load_answers(path: str) -> list[dict]:
    return load_answers_from(json.loads(Path(path).read_text(encoding="utf-8")))


def load_answers_from(rows: list[dict]) -> list[dict]:
    # A --repeats run holds several answers per question; the reviewer grades one.
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def load_eval(path: str) -> dict[str, dict]:
    p = Path(path)
    if not path or not p.exists():
        return {}
    items = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            items[row["id"]] = row
    return items


def balanced_sample(rows: list[dict], meta: dict[str, dict], n: int, seed: int = 0) -> list[dict]:
    """Up to n rows, taken in turn from each (language, type) group so that small
    groups are not crowded out by the large ones."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        m = meta.get(r["id"], {})
        groups[(m.get("language") or r.get("language") or "?", m.get("type") or r.get("type") or "?")].append(r)
    rng = random.Random(seed)
    queues = []
    for key in sorted(groups):
        g = groups[key][:]
        rng.shuffle(g)
        queues.append(g)
    picked: list[dict] = []
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop())
    return picked


def sheet_rows(sample: list[dict], meta: dict[str, dict]) -> list[dict]:
    out = []
    for r in sample:
        m = meta.get(r["id"], {})
        out.append({
            "id": r["id"], "language": m.get("language") or r.get("language", ""),
            "type": m.get("type") or r.get("type", ""), "question": r["question"],
            "answer": r.get("answer") or "",
            "cited_sections": "; ".join(str(s.get("citation")) for s in r.get("sources", [])),
            "refused": "yes" if r.get("refused") else "no",
            **dict.fromkeys(GRADES, ""),
            "_excerpts": excerpts(r, max_chars=1500), "_sources": r.get("sources", []),
            "_reference": m.get("reference_answer") or ""})
    return out


def write_csv(rows: list[dict], path: Path) -> None:
    # utf-8-sig: Excel on Windows shows Bangla correctly only with the byte-order mark.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _radios(qid: str, crit: tuple) -> str:
    name, label, values = crit
    opts = {"y": "Yes / হ্যাঁ", "p": "Partly / আংশিক", "n": "No / না"}
    buttons = "".join(
        f'<label><input type="radio" name="{html.escape(qid)}|{name}" value="{v}"> {opts[v]}</label>'
        for v in values)
    return (f'<fieldset><legend>{html.escape(label)}'
            f'<span lang="bn">{html.escape(BANGLA[name])}</span></legend>{buttons}</fieldset>')


def write_html(rows: list[dict], path: Path, title: str) -> None:
    cards = []
    for n, r in enumerate(rows, 1):
        qid = r["id"]
        sources = "".join(
            f'<li><a href="{html.escape(s.get("url") or "#")}" target="_blank" rel="noopener">'
            f'{html.escape(str(s.get("citation")))}</a>'
            f'<blockquote>{html.escape((s.get("text") or "")[:1500])}</blockquote></li>'
            for s in r["_sources"]) or "<li>none</li>"
        crits = [REFUSED_CRITERION] if r["refused"] == "yes" else CRITERIA
        reference = (f'<details><summary>Reference answer drafted when the question was written '
                     f'(not checked by a lawyer; may itself be wrong)</summary>'
                     f'<p>{html.escape(r["_reference"])}</p></details>') if r["_reference"] else ""
        cards.append(f"""
<section class="card" data-id="{html.escape(qid)}">
  <h2><span class="n">{n}</span> {html.escape(r['question'])}</h2>
  <p class="meta">{html.escape(qid)} · {html.escape(r['language'])} · {html.escape(r['type'])}
    {'· <strong>declined</strong>' if r['refused'] == 'yes' else ''}</p>
  <div class="answer">{html.escape(r['answer']) or '<em>(no answer)</em>'}</div>
  <details><summary>Cited sections ({len(r['_sources'])})</summary><ol>{sources}</ol></details>
  {reference}
  {''.join(_radios(qid, c) for c in crits)}
  <label class="notes">Notes: what is wrong, what the correct law is / মন্তব্য
    <textarea name="{html.escape(qid)}|notes" rows="3"></textarea></label>
</section>""")
    info = [{k: r[k] for k in INFO} for r in rows]
    page = TEMPLATE.replace("{{TITLE}}", html.escape(title)) \
        .replace("{{COUNT}}", str(len(rows))) \
        .replace("{{CARDS}}", "".join(cards)) \
        .replace("{{ROWS}}", json.dumps(info, ensure_ascii=False).replace("</", "<\\/")) \
        .replace("{{COLUMNS}}", json.dumps(COLUMNS)) \
        .replace("{{GRADES}}", json.dumps(GRADES))
    path.write_text(page, encoding="utf-8")


# ---- scoring -----------------------------------------------------------------

def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion; honest at the small n a review has."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def read_grades(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            row = {k: (r.get(k) or "").strip() for k in COLUMNS}
            for g in GRADES[:-1]:
                v = row[g].lower()
                row[g] = VALUES.get(v) if v else None
                if v and row[g] is None:
                    raise ValueError(f"{row['id']}: '{r.get(g)}' in column {g} is not yes, partly or no")
            rows.append(row)
    return rows


def score(rows: list[dict], min_accurate: float = 0.85) -> dict:
    answered = [r for r in rows if r["refused"] != "yes"]
    declined = [r for r in rows if r["refused"] == "yes"]

    def stats(subset: list[dict], key: str) -> dict:
        vals = [r[key] for r in subset if r[key] is not None]
        n = len(vals)
        yes = sum(1 for v in vals if v == 1.0)
        partly = sum(1 for v in vals if v == 0.5)
        lo, hi = wilson(yes, n)
        return {"n": n, "yes": yes, "partly": partly, "no": n - yes - partly,
                "yes_rate": round(yes / n, 3) if n else None,
                "ci95": [round(lo, 3), round(hi, 3)] if n else None}

    by_language = {}
    for lang in sorted({r["language"] for r in answered}):
        sub = [r for r in answered if r["language"] == lang]
        by_language[lang] = {c[0]: stats(sub, c[0]) for c in CRITERIA}
    overall = {c[0]: stats(answered, c[0]) for c in CRITERIA}
    should = stats(declined, REFUSED_CRITERION[0])
    unsafe = [r for r in answered if r["safe"] == 0.0]
    wrong = [r for r in answered if r["accurate"] is not None and r["accurate"] < 1.0]
    graded = sum(1 for r in answered if r["accurate"] is not None)
    acc = overall["accurate"]["yes_rate"]
    checks = {
        "no answer graded unsafe": not unsafe,
        f"fully accurate in at least {min_accurate:.0%} of answers": acc is not None and acc >= min_accurate,
        "at least 30 answers graded": graded >= 30,
    }
    return {"graded": graded, "declined": len(declined), "overall": overall,
            "by_language": by_language, "should_have_answered": should,
            "unsafe": [_brief(r) for r in unsafe], "not_fully_accurate": [_brief(r) for r in wrong],
            "checks": checks, "launch_bar_met": all(checks.values())}


def _brief(r: dict) -> dict:
    return {"id": r["id"], "language": r["language"], "question": r["question"],
            "accurate": r["accurate"], "safe": r["safe"], "notes": r["notes"]}


def _cell(text) -> str:
    return " ".join(str(text).replace("|", "\\|").split())


def _rate(s: dict) -> str:
    if not s["n"]:
        return "–"
    return f"{s['yes_rate']:.0%} ({s['ci95'][0]:.0%}–{s['ci95'][1]:.0%}), {s['partly']} partly, {s['no']} no"


def markdown(report: dict) -> str:
    verdict = "**met**" if report["launch_bar_met"] else "**not met**"
    lines = ["# Lawyer review of the answers", "",
             f"{report['graded']} answers graded, {report['declined']} declined questions checked. "
             + f"Launch bar {verdict}.", ""]
    lines += [f"- {'✓' if ok else '✗'} {name}" for name, ok in report["checks"].items()]
    lines += ["", "Rates are the share graded fully yes, with a 95% interval; with 50 answers the "
              + "interval is about ±10 points, so a difference smaller than that is noise.", "",
              "| Criterion | All | " + " | ".join(report["by_language"]) + " |",
              "|---|---|" + "---|" * len(report["by_language"])]
    for name, _label, _ in CRITERIA:
        lines.append(f"| {name} | {_rate(report['overall'][name])} | "
                     + " | ".join(_rate(v[name]) for v in report["by_language"].values()) + " |")
    s = report["should_have_answered"]
    if s["n"]:
        lines += ["", f"Declined but should have answered: {s['yes']} of {s['n']}."]
    for key, heading in (("unsafe", "Graded unsafe: fix before launch"),
                         ("not_fully_accurate", "Not fully accurate")):
        if report[key]:
            lines += ["", f"## {heading}", "", "| id | lang | question | reviewer's notes |",
                      "|---|---|---|---|"]
            lines += [f"| {r['id']} | {r['language']} | {_cell(r['question'][:120])} | "
                      + f"{_cell(r['notes']) or '–'} |" for r in report[key]]
    lines += ["", "Each wrong answer is a test case: fix the topic table, the eval gold or the "
              + "prompt, then re-run `bdrag e2e` on these ids.", ""]
    return "\n".join(lines)


def judge_labels(rows: list[dict]) -> list[dict]:
    """The reviewer's verdicts in calibrate_judge's format, so the judge model can be
    measured against a lawyer instead of against the developer."""
    out = []
    for r in rows:
        if r["refused"] == "yes":
            continue
        label: dict = {"id": r["id"]}
        if r["sections"] is not None:
            label["human_faithful"] = int(r["sections"] == 1.0)
        if r["accurate"] is not None:
            label["human_correct"] = int(r["accurate"] == 1.0)
        if len(label) > 1:
            out.append(label)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bdrag review", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sh = sub.add_parser("sheet", help="sample answers and write the grading sheet")
    sh.add_argument("answers", help="a `bdrag e2e` .answers.json file")
    sh.add_argument("--eval", default="data/eval/eval.jsonl",
                    help="for language, type and the drafted reference answer")
    sh.add_argument("--n", type=int, default=50)
    sh.add_argument("--seed", type=int, default=0)
    sh.add_argument("--out", default="review")
    sh.add_argument("--title", default="Bangladesh Law Assistant: answer review")
    sc = sub.add_parser("score", help="read the graded sheet and report")
    sc.add_argument("grades", help="the graded CSV (from the page's Download button or a spreadsheet)")
    sc.add_argument("--min-accurate", type=float, default=0.85)
    sc.add_argument("--out", help="write the markdown report here instead of printing it")
    sc.add_argument("--json", help="also write the full report as JSON")
    sc.add_argument("--judge-labels", help="append the verdicts to this calibrate_judge labels file")
    args = ap.parse_args(argv)

    if args.cmd == "sheet":
        meta = load_eval(args.eval)
        rows = sheet_rows(balanced_sample(load_answers(args.answers), meta, args.n, args.seed), meta)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        write_csv(rows, out / "grades.csv")
        write_html(rows, out / "review.html", args.title)
        print(f"wrote {len(rows)} answers to {out / 'review.html'} and {out / 'grades.csv'}; "
              "send the reviewer the .html file and docs/review/RUBRIC.md")
        return 0

    try:
        rows = read_grades(args.grades)
    except ValueError as e:
        print(f"bdrag review: {e}", file=sys.stderr)
        return 2
    report = score(rows, args.min_accurate)
    text = markdown(report)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: launch bar {'met' if report['launch_bar_met'] else 'not met'}")
    else:
        print(text)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.judge_labels:
        labels = judge_labels(rows)
        Path(args.judge_labels).parent.mkdir(parents=True, exist_ok=True)
        with open(args.judge_labels, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in labels)
        print(f"appended {len(labels)} labels to {args.judge_labels} "
              "(bdrag calibrate-judge <answers> --labels ... --report)")
    return 0 if report["launch_bar_met"] else 1


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{{TITLE}}</title>
<style>
  :root { --bg: #fbfaf7; --fg: #1d1d1b; --muted: #5d5b55; --line: #dcd8cf; --card: #fff; --accent: #0b6e4f; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #161614; --fg: #ecebe6; --muted: #a9a69d; --line: #3a3934; --card: #1f1f1c; --accent: #5fc39c; }
  }
  body { background: var(--bg); color: var(--fg); margin: 0;
         font: 16px/1.6 "Noto Sans Bengali", "Hind Siliguri", system-ui, sans-serif; }
  main { max-width: 820px; margin: 0 auto; padding: 24px 16px 96px; }
  h1 { font-size: 26px; margin: 0 0 4px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
          padding: 16px 18px; margin: 18px 0; }
  .card h2 { font-size: 18px; margin: 0 0 4px; }
  .n { display: inline-block; min-width: 2em; color: var(--accent); }
  .meta { color: var(--muted); font-size: 14px; margin: 0 0 10px; }
  .answer { white-space: pre-wrap; border-left: 3px solid var(--accent); padding: 4px 0 4px 12px; }
  blockquote { margin: 6px 0 12px; color: var(--muted); font-size: 14px; white-space: pre-wrap; }
  details { margin: 10px 0; } summary { cursor: pointer; color: var(--accent); }
  fieldset { border: 0; margin: 14px 0 0; padding: 0; min-width: 0; }
  legend { font-weight: 600; padding: 0; }
  legend span { display: block; font-weight: 400; color: var(--muted); }
  fieldset label { display: inline-flex; gap: 6px; margin: 4px 18px 0 0; align-items: center; }
  .notes { display: block; margin-top: 10px; font-weight: 600; }
  textarea { width: 100%; box-sizing: border-box; font: inherit; font-weight: 400; margin-top: 4px;
             background: var(--bg); color: var(--fg); border: 1px solid var(--line); border-radius: 6px; }
  .bar { position: sticky; bottom: 0; background: var(--bg); border-top: 1px solid var(--line);
         padding: 10px 16px; display: flex; gap: 14px; align-items: center; justify-content: center; flex-wrap: wrap; }
  button { font: inherit; padding: 8px 16px; border-radius: 6px; border: 0;
           background: var(--accent); color: var(--bg); cursor: pointer; }
  a { color: var(--accent); }
  @media print { .bar, details summary { display: none; } .card { break-inside: avoid; } }
</style>
</head>
<body>
<main>
<h1>{{TITLE}}</h1>
<p>{{COUNT}} answers written by the service to test questions. Please read each answer as if a
member of the public had received it, and grade it against the rubric (docs/review/RUBRIC.md).
Open "Cited sections" to see the law text the answer relied on; the links go to the official
text on bdlaws.minlaw.gov.bd. Your grades are saved in this browser as you go. When you are done,
press <strong>Download grades</strong> and send the file back.</p>
<p lang="bn">প্রতিটি উত্তর এমনভাবে পড়ুন যেন একজন সাধারণ মানুষ এটি পেয়েছেন, এবং নির্দেশিকা অনুযায়ী মূল্যায়ন করুন।
আপনার মূল্যায়ন এই ব্রাউজারে সংরক্ষিত থাকে। শেষ হলে <strong>Download grades</strong> চেপে ফাইলটি ফেরত পাঠান।</p>
{{CARDS}}
</main>
<div class="bar"><span id="progress"></span><button type="button" id="download">Download grades</button></div>
<script>
const ROWS = {{ROWS}};
const COLUMNS = {{COLUMNS}};
const GRADES = {{GRADES}};
const KEY = "bdrag-review:" + ROWS.map(r => r.id).join(",");
let saved = {};
try { saved = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { saved = {}; }
for (const [name, value] of Object.entries(saved)) {
  const radio = document.querySelector(`input[type=radio][name="${CSS.escape(name)}"][value="${CSS.escape(value)}"]`);
  if (radio) radio.checked = true;
  const area = document.querySelector(`textarea[name="${CSS.escape(name)}"]`);
  if (area) area.value = value;
}
function progress() {
  const done = ROWS.filter(r => document.querySelector(`.card[data-id="${CSS.escape(r.id)}"] input:checked`)).length;
  document.getElementById("progress").textContent = `${done} of ${ROWS.length} graded`;
}
document.addEventListener("input", e => {
  const el = e.target;
  if (!el.name) return;
  saved[el.name] = el.value;
  try { localStorage.setItem(KEY, JSON.stringify(saved)); } catch (err) {}
  progress();
});
progress();
function cell(v) {
  v = String(v ?? "");
  return /[",\\n\\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}
document.getElementById("download").addEventListener("click", () => {
  const lines = [COLUMNS.join(",")];
  for (const r of ROWS) {
    const row = {...r};
    for (const g of GRADES) row[g] = saved[r.id + "|" + g] || "";
    lines.push(COLUMNS.map(c => cell(row[c])).join(","));
  }
  const blob = new Blob(["\\ufeff" + lines.join("\\r\\n") + "\\r\\n"], {type: "text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "grades.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
