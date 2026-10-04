#!/usr/bin/env python
"""Finish the project in one command: get the index from Kaggle, evaluate, write the results.

    .venv\\Scripts\\python scripts\\finish.py                 # everything that is not done yet
    .venv\\Scripts\\python scripts\\finish.py --e2e none      # skip the Ollama answer evaluation
    .venv\\Scripts\\python scripts\\finish.py --from-kernel notebooka2b47ca30b

Steps (each is skipped when its output already exists; delete the output to redo it):
  1. index     download the bge-m3 + BM25 index built on Kaggle (waits for a running
               build, or starts one from the bdrag-bundle dataset) into data/index
  2. ablation  every retrieval component on/off, paired tests  -> results/ablation.md
  3. tuning    fusion weights on data/eval/tune.jsonl           -> results/tuning.json
  4. failures  why the misses miss                              -> results/failures.json
  5. select    choose the served configuration on the tuning split, then score it
               once on the test set                              -> results/selected.json, final.json
     guard     abstention threshold for that configuration       -> results/guard.txt
  6. e2e       answers with an Ollama model, judged by a second model, on a Kaggle T4
               (--e2e local: on this machine's Ollama instead)   -> results/e2e-*.json
  7. report    results/RESULTS.md and the README "Results" section
  8. checks    tests + ruff, then a local git commit (pushing stays your decision)
Everything is logged to results/finish.log.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kagglerun as kr  # noqa: E402

PY = sys.executable
RESULTS = ROOT / "results"
INDEX = ROOT / "data" / "index"
CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
LOG = RESULTS / "finish.log"
ANSWER_MODEL, JUDGE_MODEL = "qwen2.5:7b", "llama3.1:8b"


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    RESULTS.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(args: list[str], out: Path | None = None, check: bool = True) -> str:
    log("$ " + " ".join(str(a) for a in args))
    # children print Bangla; a Windows console pipe defaults to cp1252 and would crash them
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    p = subprocess.run([str(a) for a in args], cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    text = (p.stdout or "") + (p.stderr or "")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text[-3000:], flush=True)
    if out is not None:
        out.write_text(text, encoding="utf-8")
    if check and p.returncode != 0:
        sys.exit(f"step failed: {' '.join(str(a) for a in args[:3])} — see {LOG}")
    return text


def n_chunks() -> int:
    with CHUNKS.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def index_ok() -> bool:
    info = INDEX / "index.json"
    if not info.exists() or not (INDEX / "vectors.npy").exists():
        return False
    meta = json.loads(info.read_text(encoding="utf-8"))
    return "bge-m3" in str(meta.get("embedder", "")) and int(meta.get("count", -1)) == n_chunks()


def install_index(src: Path) -> None:
    """Move a downloaded index (folder or bdrag_index.zip) into data/index."""
    zips = list(src.rglob("bdrag_index.zip"))
    if zips:
        kr.unzip(zips[0], src / "_unzipped")
    cands = [p.parent for p in src.rglob("vectors.npy")]
    if not cands:
        sys.exit(f"no vectors.npy in the Kaggle output ({src}); open the kernel's log on kaggle.com")
    new = cands[0]
    if INDEX.exists():
        backup = INDEX.with_name(f"index_old_{time.strftime('%Y%m%d_%H%M')}")
        INDEX.rename(backup)
        log(f"previous index kept at {backup}")
    shutil.copytree(new, INDEX)
    log(f"index installed: {sorted(p.name for p in INDEX.iterdir())}")


def step_index(args) -> None:
    if index_ok():
        log("index: already in place")
        return
    user = kr.username()
    ref, state = None, "unknown"
    # the notebook started by hand, then the one this script starts: use whichever succeeded
    for slug in [s for s in (args.from_kernel, "bdrag-build-index") if s]:
        r = f"{user}/{slug}"
        st = kr.status(r)
        log(f"index: kernel {r} is {st}")
        if st in ("running", "queued"):
            st = kr.wait_kernel(r)
        if st == "complete":
            ref, state = r, st
            break
    if state != "complete":
        folder = ROOT / "kaggle" / "kernels" / "build_index"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "kaggle" / "build_index_cell.py", folder / "build_index_cell.py")
        ref = kr.push_kernel(folder, "bdrag-build-index", "build_index_cell.py", [f"{user}/bdrag-bundle"])
        state = kr.wait_kernel(ref)
        if state != "complete":
            sys.exit(f"index build on Kaggle ended with '{state}': open kaggle.com/code/{ref} for the log")
    dl = ROOT / "data" / "_kaggle_index"
    shutil.rmtree(dl, ignore_errors=True)
    kr.download_output(ref, dl)
    install_index(dl)
    shutil.rmtree(dl, ignore_errors=True)
    if not index_ok():
        sys.exit("the downloaded index does not match data/processed/chunks.jsonl (different chunk count)")


# Query-side features every candidate uses; they only change which sections are looked up.
EXTRAS = ["--expand-refs", "--synonyms", "--transliterate", "--resolve-refs", "--boost-in-force",
          "--max-parts-per-section", "2"]
SELECTED = RESULTS / "selected.json"


def candidates() -> dict[str, list[str]]:
    """Fast configurations to choose between (the cross-encoder is too slow on a CPU to serve)."""
    out = {"dense": ["--mode", "dense", *EXTRAS],
           "hybrid-routed": ["--mode", "hybrid", "--route", *EXTRAS]}
    tun = RESULTS / "tuning.json"
    if tun.exists():
        best = json.loads(tun.read_text(encoding="utf-8"))["grid"][0]
        out["hybrid-tuned"] = ["--mode", "hybrid", "--dense-weight", str(best["dense_weight"]),
                               "--bm25-weight", str(best["bm25_weight"]), "--rrf-k", str(best["rrf_k"]),
                               "--candidates", str(best["candidates"]), *EXTRAS]
    return out


def recall5(path: Path) -> float:
    return float(json.loads(path.read_text(encoding="utf-8"))["overall"]["recall@5"]["mean"])


def step_select() -> list[str]:
    """Choose the served configuration on the tuning split, then measure it once on the test set."""
    if SELECTED.exists():
        sel = json.loads(SELECTED.read_text(encoding="utf-8"))
        log(f"select: already chose '{sel['name']}'")
        return sel["args"]
    cands, scores = candidates(), {}
    for name, extra in cands.items():
        out = RESULTS / "select" / f"{name}.json"
        if not out.exists():
            sh([PY, "scripts/eval_retrieval.py", "--eval", "data/eval/tune.jsonl", "--index", str(INDEX),
                "--label", name, "--results", "results/select", *extra])
        scores[name] = recall5(out)
    # ties go to the simpler configuration (dict order: dense first)
    name = max(scores, key=lambda n: (round(scores[n], 4), -list(cands).index(n)))
    log(f"select: tuning-split recall@5 {scores} -> '{name}'")
    if not (RESULTS / "final.json").exists():
        sh([PY, "scripts/eval_retrieval.py", "--eval", "data/eval/eval.jsonl", "--index", str(INDEX),
            "--label", "final", *cands[name]])
    SELECTED.write_text(json.dumps({"name": name, "args": cands[name], "tune_recall@5": scores,
                                    "test_recall@5": recall5(RESULTS / "final.json")}, indent=1),
                        encoding="utf-8")
    return cands[name]


def step_retrieval() -> None:
    RESULTS.mkdir(exist_ok=True)
    if not (RESULTS / "ablation.md").exists():
        sh([PY, "scripts/ablate.py", "--eval", "data/eval/eval.jsonl", "--index", str(INDEX),
            "--out", "results/ablation.md"])
    if not (RESULTS / "tuning.json").exists():
        sh([PY, "scripts/tune.py", "--eval", "data/eval/tune.jsonl", "--index", str(INDEX),
            "--out", "results/tuning.json"])


def step_failures(sel: list[str], e2e_label: str | None) -> None:
    """Why the served configuration's misses miss (and, with answers, where generation loses)."""
    f = RESULTS / "failures.json"
    answers = RESULTS / f"{e2e_label}.answers.json" if e2e_label else None
    extra = ["--answers", str(answers)] if answers and answers.exists() else []
    chosen = RESULTS / f"{e2e_label}.select.json" if e2e_label else None
    if extra and chosen and chosen.exists():        # same k as the answers were generated with
        extra += json.loads(chosen.read_text(encoding="utf-8"))["chosen"]["extra"]
    key = {"config": sel, "answers": e2e_label if extra else False}
    if f.exists():
        old = json.loads(f.read_text(encoding="utf-8"))
        if {"config": old.get("config"), "answers": old.get("answers", False)} == key:
            return
    sh([PY, "scripts/failure_report.py", "--eval", "data/eval/eval.jsonl", "--index", str(INDEX),
        "--out", "results/failures.json", *extra, *sel])
    report = json.loads(f.read_text(encoding="utf-8"))
    f.write_text(json.dumps({**key, **report}, ensure_ascii=False, indent=2), encoding="utf-8")


STAGES = {"retrieval_miss": "no gold section among the top 50 candidates",
          "ranking_miss": "a gold section in the top 50, but not among the excerpts the model saw",
          "citation_miss": "the gold section was retrieved but the answer cited another",
          "answer_miss": "retrieved and cited, but the answer was judged wrong",
          "not_in_corpus": "the gold act is missing from the scrape"}


def failures_block() -> str | None:
    f = RESULTS / "failures.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text(encoding="utf-8"))
    counts = r["counts"]
    total = sum(counts.values())
    lines = [f"Served configuration, {total} test questions: **{counts.get('ok', 0)} fully correct**"
             + ("" if r.get("answers") else " at the retrieval stage") + ".", "",
             "| Where it failed | Questions | Meaning |", "|---|---|---|"]
    for stage, meaning in STAGES.items():
        if counts.get(stage):
            lines.append(f"| {stage.replace('_', ' ')} | {counts[stage]} | {meaning} |")
    lines += ["", "By question type (failures / total):", ""]
    for t, c in sorted(r.get("by_type", {}).items()):
        n = sum(c.values())
        lines.append(f"- {t}: {n - c.get('ok', 0)} / {n}")
    lines += ["", "The misses, verbatim:", ""]
    for row in r.get("failures", []):
        lines.append(f"- `{row['stage']}` ({row['type']}, {row['language']}) {row['question']}")
    return "\n".join(lines)


def step_guard(sel: list[str]) -> None:
    """Abstention threshold for the selected configuration (scores differ between dense and fused)."""
    g = RESULTS / "guard.txt"
    tag = "# config: " + " ".join(sel)
    if g.exists() and g.read_text(encoding="utf-8").startswith(tag):
        return
    text = sh([PY, "scripts/calibrate_guard.py", "--eval", "data/eval/eval.jsonl", "--index", str(INDEX), *sel])
    g.write_text(tag + "\n" + text, encoding="utf-8")


def ollama_probe(model: str) -> tuple[bool, str]:
    """One tiny generation: proves the server has the model under exactly this name."""
    import urllib.error
    import urllib.request

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    if not host.startswith("http"):
        host = "http://" + host
    body = json.dumps({"model": model, "prompt": "Say OK.", "stream": False,
                       "options": {"num_predict": 2}}).encode()
    req = urllib.request.Request(f"{host}/api/generate", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status == 200, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}"
    except OSError as e:
        return False, f"{type(e).__name__}: {e}"


E2E_LABEL = "e2e-" + ANSWER_MODEL.replace(":", "-").replace(".", "")


def fetch_e2e(ref: str, label: str) -> bool:
    dl = RESULTS / "_kaggle_e2e"
    shutil.rmtree(dl, ignore_errors=True)
    kr.download_output(ref, dl)
    for f in dl.rglob(f"{label}*"):
        shutil.copy(f, RESULTS / f.name)
    shutil.rmtree(dl, ignore_errors=True)
    return (RESULTS / f"{label}.json").exists()


def kaggle_e2e(sel: list[str], slug: str, label: str, head: str) -> str | None:
    """Run kaggle/e2e_cell.py as the Kaggle kernel `slug` (prefixed with `head`) and fetch `label`."""
    if (RESULTS / f"{label}.json").exists():
        return label
    user = kr.username()
    ref = f"{user}/{slug}"
    state = kr.status(ref)
    log(f"e2e: Kaggle kernel {ref} is {state}")
    if state == "complete" and fetch_e2e(ref, label):     # a finished run from earlier
        return label
    if state not in ("running", "queued"):
        sh([PY, "scripts/make_kaggle_bundle.py"])
        kr.publish_dataset(ROOT / "kaggle_upload", f"{user}/bdrag-bundle", "bdrag-bundle",
                           "code + chunks from finish.py")
        folder = ROOT / "kaggle" / "kernels" / slug
        folder.mkdir(parents=True, exist_ok=True)
        head = f"E2E_ARGS = {json.dumps(sel)}\nLABEL = {json.dumps(label)}\n" + head
        (folder / "e2e_cell.py").write_text(head + (ROOT / "kaggle" / "e2e_cell.py").read_text(encoding="utf-8"),
                                            encoding="utf-8")
        kr.push_kernel(folder, slug, "e2e_cell.py", [f"{user}/bdrag-bundle"],
                       kernels=[f"{user}/bdrag-build-index"])
    state = kr.wait_kernel(ref)
    log(f"e2e: Kaggle kernel {state}")
    fetch_e2e(ref, label)
    if not (RESULTS / f"{label}.json").exists():
        log(f"e2e: no results from Kaggle; open kaggle.com/code/{ref} for the log")
        return None
    return label


def step_e2e_kaggle(sel: list[str]) -> str | None:
    """Answers + judge on a free Kaggle T4 with Ollama (a 7B model on a laptop CPU needs minutes per answer)."""
    return kaggle_e2e(sel, "bdrag-e2e", E2E_LABEL, f"MODELS = {json.dumps([ANSWER_MODEL, JUDGE_MODEL])}\n")


# A larger answering model on the same retrieval, for comparison. Both models were fixed in advance
# (nothing is tuned on the test set); the 14B model needs a GPU to be practical.
FINAL_LABEL = "e2e-final"
BIG_MODEL = "qwen2.5:14b"


def step_e2e_big(sel: list[str]) -> str | None:
    head = f"MODELS = {json.dumps([BIG_MODEL, JUDGE_MODEL])}\n"
    return kaggle_e2e(sel, "bdrag-e2e-select", FINAL_LABEL, head)


def step_e2e(args, sel: list[str]) -> str | None:
    if args.e2e == "none":
        return None
    if args.e2e == "kaggle":
        base = step_e2e_kaggle(sel)
        return step_e2e_big(sel) or base
    os.environ.setdefault("RAG_LLM_TIMEOUT", "900")      # CPU answers are slow
    if not shutil.which("ollama"):
        log("e2e: Ollama is not installed — skipped (install from ollama.com, then re-run)")
        return None
    listing = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    log("ollama list:\n" + listing.strip())
    for m in (ANSWER_MODEL, JUDGE_MODEL):
        ok, why = ollama_probe(m)
        if not ok:
            log(f"e2e: {m} does not answer ({why}); pulling it (several GB, once)")
            subprocess.run(["ollama", "pull", m], check=False)
            ok, why = ollama_probe(m)
        if not ok:
            log(f"e2e: skipped, {m} still does not answer: {why}")
            return None
    label = E2E_LABEL
    if not (RESULTS / f"{label}.json").exists():
        sh([PY, "scripts/eval_e2e.py", "--eval", "data/eval/eval.jsonl", "--index", str(INDEX),
            "--provider", "ollama", "--llm-model", ANSWER_MODEL,
            "--judge-provider", "ollama", "--judge-model", JUDGE_MODEL, "--label", label, *sel],
           out=RESULTS / f"{label}.txt", check=False)
        if not (RESULTS / f"{label}.json").exists():
            log(f"e2e: failed, see results/{label}.txt; the retrieval results are still reported")
            return None
    return label


GEN_ROWS = [("correctness", "Correct (judge vs. reference answer)"),
            ("faithfulness", "Faithful to the cited excerpts (judge)"),
            ("gold_cited", "Cites a gold section"),
            ("citation_validity", "Citations point at retrieved excerpts"),
            ("refusal_correct", "Refuses exactly when it should")]


def headline() -> str | None:
    """The key numbers for the top of the README."""
    final = RESULTS / "final.json"
    if not final.exists():
        return None
    r = json.loads(final.read_text(encoding="utf-8"))["overall"]["recall@5"]
    rows = ["| Measured on the full corpus (86 test questions) | |", "|---|---|",
            f"| Right section in the top 5 (retrieval) | {r['mean']:.2f} [{r['lo']:.2f}–{r['hi']:.2f}] |"]
    gens = {lab: json.loads((RESULTS / f"{lab}.json").read_text(encoding="utf-8")).get("generation", {})
            for lab in (E2E_LABEL, FINAL_LABEL) if (RESULTS / f"{lab}.json").exists()}
    names = {E2E_LABEL: ANSWER_MODEL, FINAL_LABEL: BIG_MODEL}
    for key, desc in (("citation_validity", "Citations that point at a retrieved excerpt"),
                      ("refusal_correct", "Refuses exactly when the corpus has no answer"),
                      ("correctness", "Answer judged correct against the reference")):
        for lab, g in gens.items():
            if key in g:
                rows.append(f"| {desc} ({names[lab]}) | {g[key]['mean']:.2f} [{g[key]['lo']:.2f}–{g[key]['hi']:.2f}] |")
    return "\n".join([*rows, "", "95% bootstrap intervals; details in [Results](#results)."])


def e2e_section() -> list[str]:
    runs = [(lab, RESULTS / f"{lab}.json") for lab in (E2E_LABEL, FINAL_LABEL)]
    runs = [(lab, json.loads(p.read_text(encoding="utf-8"))) for lab, p in runs if p.exists()]
    if not runs:
        return []
    names = {E2E_LABEL: ANSWER_MODEL, FINAL_LABEL: BIG_MODEL}
    out = [f"### End to end (answers by a local Ollama model, judged by {JUDGE_MODEL}, on a Kaggle T4)", "",
           "Same retrieval, same five excerpts per question, two answering models fixed in advance.", "",
           "| | " + " | ".join(names.get(lab, lab) for lab, _ in runs) + " |",
           "|---|" + "---|" * len(runs)]
    for key, desc in GEN_ROWS:
        cells = []
        for _, r in runs:
            m = r.get("generation", {}).get(key)
            cells.append(f"{m['mean']:.3f} [{m['lo']:.2f}–{m['hi']:.2f}]" if m else "—")
        out.append(f"| {desc} | " + " | ".join(cells) + " |")
    out += ["", "The judge is itself an 8B model: its scores are indicative, and the deterministic rows "
            "(citations, refusals) are the ones to trust most.", ""]
    return out


def step_report(e2e_label: str | None) -> None:
    with open(ROOT / "data" / "eval" / "eval.jsonl", encoding="utf-8") as f:
        n_q = sum(1 for line in f if line.strip())
    parts = ["## Results", "",
             f"Measured on the full corpus ({n_chunks():,} chunks) with the {n_q}-question evaluation set "
             "in `data/eval/eval.jsonl`; 95% bootstrap intervals, paired tests against the dense baseline. "
             "Regenerate everything with `python scripts/finish.py`.", ""]
    abl = RESULTS / "ablation.md"
    if abl.exists():
        parts += ["### Retrieval ablation", "", abl.read_text(encoding="utf-8").strip(), ""]
    if SELECTED.exists():
        sel = json.loads(SELECTED.read_text(encoding="utf-8"))
        final = json.loads((RESULTS / "final.json").read_text(encoding="utf-8"))["overall"]
        cells = " | ".join(f"{final[m]['mean']:.3f} [{final[m]['lo']:.2f}–{final[m]['hi']:.2f}]"
                           for m in ("recall@5", "recall@10", "mrr"))
        parts += ["### Served configuration", "",
                  "Chosen on the tuning split (recall@5: "
                  + ", ".join(f"{k} {v:.3f}" for k, v in sel["tune_recall@5"].items())
                  + f"), then measured once on the test set: **{sel['name']}**.", "",
                  "| recall@5 | recall@10 | MRR |", "|---|---|---|", f"| {cells} |", "",
                  "`" + " ".join(sel["args"]) + "`", ""]
    tun = RESULTS / "tuning.json"
    if tun.exists():
        t = json.loads(tun.read_text(encoding="utf-8"))
        best = t["grid"][0] if t.get("grid") else {}
        parts += ["### Fusion weights (tuned on the separate 24-question tuning split)", "",
                  "```json", json.dumps(best, ensure_ascii=False, indent=1), "```", ""]
    g = RESULTS / "guard.txt"
    if g.exists():
        lines = g.read_text(encoding="utf-8").splitlines()
        table = [ln for ln in lines if re.match(r"\s*(min_score|[0-9.]+\s+[0-9.]+)", ln)]
        if table:
            parts += ["### Abstention threshold (`calibrate_guard.py`, served configuration)", "",
                      "```", *table, "```", "",
                      "No threshold fits both goals: refusing most unanswerable questions also refuses "
                      "a large share of answerable ones, because the top dense score of an off-topic "
                      "question is often as high as that of a hard real one. The service therefore ships "
                      "without a score threshold (`BDRAG_MIN_SCORE` unset) and relies on the answer "
                      "prompt, which tells the model to refuse when the excerpts do not answer, and on the citation checks.", ""]
    parts += e2e_section()
    body = "\n".join(parts).rstrip() + "\n"
    (RESULTS / "RESULTS.md").write_text(body, encoding="utf-8")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    m = re.search(r"^## Results\n.*?(?=^## )", text, re.S | re.M)
    if m:
        text = text[:m.start()] + body + "\n" + text[m.end():]
        log("README results section updated")
    hl = headline()
    if hl:
        text = re.sub(r"(<!-- auto:headline -->\n).*?(<!-- /auto:headline -->)",
                      lambda mm: mm.group(1) + hl + "\n" + mm.group(2), text, flags=re.S)
    fb = failures_block()
    if fb:
        text = re.sub(r"(<!-- auto:failures -->\n).*?(<!-- /auto:failures -->)",
                      lambda mm: mm.group(1) + fb + "\n" + mm.group(2), text, flags=re.S)
    readme.write_text(text, encoding="utf-8")


def step_checks() -> None:
    sh([PY, "-m", "unittest", "discover", "-s", "tests", "-q"])
    sh([PY, "-m", "ruff", "check", "src", "scripts", "tests"], check=False)
    subprocess.run(["git", "add", "-A"], cwd=ROOT)
    subprocess.run(["git", "commit", "-m", "Full-corpus index and evaluation results"], cwd=ROOT)
    log("committed locally. Review README.md, then publish with:  git push")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-kernel", default="notebooka2b47ca30b",
                    help="Kaggle notebook whose output holds the index (empty: build a new one)")
    ap.add_argument("--e2e", choices=["kaggle", "local", "none"], default="kaggle",
                    help="where to run the Ollama answer evaluation (kaggle: free T4, about an hour)")
    ap.add_argument("--no-commit", action="store_true")
    args = ap.parse_args()
    log("=== finish.py started ===")
    step_index(args)
    step_retrieval()
    sel = step_select()
    step_guard(sel)
    label = step_e2e(args, sel)
    step_failures(sel, label)
    step_report(label)
    if not args.no_commit:
        step_checks()
    log("=== done ===")


if __name__ == "__main__":
    main()
