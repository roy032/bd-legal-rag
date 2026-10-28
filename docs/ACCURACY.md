# How accurate is it?

<!-- Written by `bdrag scorecard render` from src/service/static/scorecard.json; edit that file's notes or add a result with `bdrag scorecard add`, not this page. -->

Every number here comes from a command in this repository, run on a fixed set of 96 questions (86 answerable, 10 that the law text cannot answer) that a person wrote with the governing sections marked. Each one says when it was measured, with which model and on what machine, and links the file with every question's result. Where something has not been measured yet, the page says so.

Corpus: Acts published on the Laws of Bangladesh website (bdlaws.minlaw.gov.bd), 43,966 searchable passages; no court decisions, rules or SROs yet. Scorecard updated 2026-10-28. The same page is served by the app at `/accuracy`, and the numbers as JSON at `/static/scorecard.json`.

## Finding the right law · সঠিক আইন খুঁজে পাওয়া

For each question in the evaluation set a person wrote down the section(s) of the Act that answer it. These numbers say how often the search puts those sections in front of the answering model.

Measured 2026-10-18 on 96 questions from `data/eval/eval.jsonl`; dense bge-m3 retrieval as served before the topic table, k=10, on the laptop's full index. Every question's result: [results/published/retrieval-2026-10-18-served.json](../results/published/retrieval-2026-10-18-served.json).

| | | Result (95% interval) |
|---|---|---|
| Right section among the first 5 found — share of answerable questions with a gold section in the top 5 | সঠিক ধারা প্রথম ৫টির মধ্যে | 90.7% (84%–96%) |
| How high the right section ranks (MRR) — 1 = always first, 0.5 = on average second | সঠিক ধারা কত ওপরে আসে (MRR) | 0.779 (0.70–0.85) |
| … for questions in Bangla | … বাংলায় করা প্রশ্নে | 89.2% (80%–97%) |
| … for questions in English | … ইংরেজিতে করা প্রশ্নে | 90.9% (82%–98%) |

The topic table, served since 19 October, raised this to **93.6%** in the right-section-in-top-5 and **0.804** MRR on the same questions ([report](../results/topics-full-index-2026-10-19.md), no interval computed). Re-running the command below records it here with its interval.

Re-run:

```
bdrag eval --mode dense --synonyms --expand-refs --transliterate --boost-in-force --resolve-refs --topics --max-parts-per-section 2 -k 10 --label scorecard
bdrag scorecard add retrieval results/scorecard.json
```

## Answers and citations · উত্তর ও উদ্ধৃতি

The whole service answering the same questions: whether it declines exactly the questions the law text cannot answer, and whether every [n] it writes points at a real excerpt that says what the answer claims.

Measured 2026-09-30 on 96 questions from `data/eval/eval.jsonl`; answers by qwen2.5:14b through Ollama, judged by llama3.1:8b, on a Kaggle T4 GPU; dense retrieval without the topic table, k=5. Every question's result: [results/published/e2e-2026-09-30-qwen25-14b.json](../results/published/e2e-2026-09-30-qwen25-14b.json).

| | | Result (95% interval) |
|---|---|---|
| Declines exactly when it should — answers the answerable, declines the unanswerable | ঠিক যখন উচিত তখনই উত্তর দিতে অস্বীকার | 90.6% (84%–96%) |
| Citations point at a real excerpt — no [n] that names a section it was not given | উদ্ধৃতি সত্যিকারের অংশ নির্দেশ করে | 100% |
| Cited sections that are the right ones — share of cited sections that are gold sections | উদ্ধৃত ধারার মধ্যে সঠিক ধারা | 71.5% (62%–80%) |
| Answer cites a right section — share of answerable questions whose answer cites a gold section | উত্তরে সঠিক ধারা উদ্ধৃত | 76.7% (69%–85%) |
| Agrees with the reference answer (judge model) — graded by a separate local model; indicative only | রেফারেন্স উত্তরের সঙ্গে মেলে (বিচারক মডেল) | 70.9% (64%–77%) |
| Says only what the excerpts say (judge model) — graded by a separate local model; strict and noisy | শুধু উদ্ধৃত অংশে যা আছে তা-ই বলে (বিচারক মডেল) | 40.6% (31%–51%) |

citation support was added after this run, so it has no number yet.

Re-run:

```
bdrag e2e --mode dense --synonyms --expand-refs --transliterate --boost-in-force --resolve-refs --topics --max-parts-per-section 2 --provider ollama --llm-model gemma4:e4b --judge-provider ollama --judge-model llama3.1:8b --label scorecard-e2e
bdrag scorecard add answers results/scorecard-e2e.json
```

## Attacks: input checks · আক্রমণ পরীক্ষা: প্রশ্ন যাচাই

Prompt injection, attempts to read the hidden instructions, quoting-tag breakouts and personal data (phone, NID, card numbers), plus ordinary legal questions that look like attacks. A harmless question that is wrongly flagged counts as a failure too. CI runs this on every change.

Measured 2026-10-28 on 52 questions; static checks, no model; CI runs them on every change. Every question's result: [results/published/redteam-2026-10-28-redteam.json](../results/published/redteam-2026-10-28-redteam.json).

| | | Result (95% interval) |
|---|---|---|
| Probes passed | পাস করা পরীক্ষা | 52/52 |

By attack: benign 14/14, injection 19/19, leak 6/6, pii 11/11, tag_breakout 2/2.

Re-run:

```
bdrag redteam --json-out results/redteam.json
bdrag scorecard add redteam results/redteam.json
```

## Attacks: what the model said · আক্রমণ পরীক্ষা: মডেলের উত্তর

The same attacks sent through the real answering model: the answer must not repeat the hidden instructions, the personal data it was sent, or what the attacker asked it to say.

**Not measured yet.** To measure it:

```
bdrag redteam --provider ollama --llm-model gemma4:e4b --json-out results/redteam-llm.json
bdrag scorecard add redteam_llm results/redteam-llm.json
```

## A lawyer's grades · আইনজীবীর মূল্যায়ন

Someone qualified in Bangladeshi law reads a balanced sample of answers and grades each against a fixed rubric (docs/review/RUBRIC.md): right law, right sections, accurate, safe to act on, clear. The launch bar is no unsafe answer and at least 85% fully accurate, over at least 30 answers.

**Not measured yet.** To measure it:

```
bdrag e2e --mode dense --synonyms --expand-refs --transliterate --boost-in-force --resolve-refs --topics --max-parts-per-section 2 --label review --no-judge --provider ollama --llm-model gemma4:e4b
bdrag review sheet results/review.answers.json --n 50 --out review/
bdrag review score review/grades.csv --out docs/reports/lawyer-review.md --json results/lawyer-review.json
bdrag scorecard add lawyer results/lawyer-review.json --setup "graded by ..."
```

## Known weak spots

- **The answer numbers are from qwen2.5:14b on a GPU, not from gemma4:e4b**, the free model the service now uses on a laptop. Re-running them with gemma4:e4b is the next measurement.
- **No lawyer has graded the answers yet.** Until one has, the retrieval and citation numbers say the service finds and cites the right law; they do not say its answers are legally sound.
- Questions that need several sections at once are the weakest kind: all their right sections are in the top 5 for about two in three, and there are only 6 such questions, so that figure is rough.
- The two judge-model rows are graded by an 8-billion-parameter local model. They are indicative only; the citation and refusal rows are checked by code and are the ones to trust.
- The evaluation set is 96 questions. A 95% interval of about ±7 points is the honest precision at that size, so a difference smaller than that is noise.
- Only Acts are covered. A question that turns on a court decision, a rule or an SRO cannot be answered correctly yet; `bdrag gaps` lists the questions visitors asked that the service could not answer.

## How to check these numbers yourself

Every command on this page runs on a laptop with free, local models (Ollama with `gemma4:e4b`) and no API key. Build the index once (`bdrag ingest` and `bdrag index`, see the README), run the block's command, then `bdrag scorecard add <block> <result file>`: that updates this page, docs/ACCURACY.md and the README together, and copies the per-question results to `results/published/`. CI runs `bdrag scorecard check`, which fails if the pages are stale or the red-team block no longer matches what the checks give today.
